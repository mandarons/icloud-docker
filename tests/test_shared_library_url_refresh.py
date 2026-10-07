"""Downloads queued late in a long walk must still succeed, Shared Library included.

iCloud download URLs expire about 30-40 minutes after the listing that
returned them. Two things made Shared Library downloads fail for good:
the buffer of pending downloads only drained at ``chunk_size``, so on a
mostly backed-up library it filled across the whole walk; and the
expired-URL refresh looked every asset up in the primary library's zone,
because icloudpy gives each asset the photos service, not its library.
"""

import json
import unittest
from unittest.mock import MagicMock, Mock, patch

import tests  # noqa: F401  — env setup
from src import BUFFERED_DOWNLOAD_MAX_AGE_SEC, album_sync_orchestrator
from src.photo_file_utils import _refresh_photo_download_url

PRIMARY = {"zoneName": "PrimarySync"}
SHARED = {
    "zoneName": "SharedSync-0000",
    "ownerRecordName": "_owner",
    "zoneType": "REGULAR_CUSTOM_ZONE",
}


def _photo(record_zone):
    master = {"recordName": "rec-1", "recordType": "CPLMaster"}
    if record_zone is not None:
        master["zoneID"] = record_zone
    service = Mock()
    service._service_endpoint = "https://cv.icloud.com"  # noqa: SLF001
    service.zone_id = PRIMARY
    service.params = {"auth": "token"}
    response = MagicMock()
    response.json.return_value = {
        "records": [
            {
                "recordName": "rec-1",
                "fields": {"resOriginalRes": {"value": {"size": 1}}},
            },
        ],
    }
    service.session.post.return_value = response
    photo = Mock()
    photo._master_record = master  # noqa: SLF001
    photo._service = service  # noqa: SLF001
    return photo, service


class TestRefreshUsesTheRecordsOwnZone(unittest.TestCase):
    def _looked_up_in(self, record_zone):
        photo, service = _photo(record_zone)
        self.assertTrue(_refresh_photo_download_url(photo))
        return json.loads(service.session.post.call_args[1]["data"])["zoneID"]

    def test_a_shared_library_asset_is_looked_up_in_its_own_zone(self):
        self.assertEqual(self._looked_up_in(SHARED), SHARED)

    def test_a_record_without_a_zone_falls_back_to_the_service_zone(self):
        self.assertEqual(self._looked_up_in(None), PRIMARY)

    def test_an_empty_zone_falls_back_to_the_service_zone(self):
        self.assertEqual(self._looked_up_in({}), PRIMARY)

    def test_a_record_without_get_is_reported_not_raised(self):
        """Indexable but not a dict: the refresh must report, never raise."""
        photo, _service = _photo(None)
        photo._master_record = Mock(spec=["__getitem__"])  # noqa: SLF001
        photo._master_record.__getitem__ = Mock(return_value="rec-1")  # noqa: SLF001
        self.assertFalse(_refresh_photo_download_url(photo))


class TestTheBufferDrainsBeforeURLsExpire(unittest.TestCase):
    """The walk is driven with a fake clock that the test advances per photo."""

    def _walk(self, photos, minute_of, needs_download, chunk_size=1000):
        clock = {"now": 0.0}

        def tasks(photo, *_args, **_kwargs):
            clock["now"] = minute_of[photo] * 60.0
            return [{"item": photo}] if photo in needs_download else []

        album = MagicMock()
        album.__iter__ = lambda _self: iter(photos)
        with (
            patch.object(
                album_sync_orchestrator,
                "_collect_photo_download_tasks",
                side_effect=tasks,
            ),
            patch.object(
                album_sync_orchestrator,
                "execute_parallel_downloads",
                side_effect=lambda t, _c: (len(t), 0),
            ) as run,
            patch.object(
                album_sync_orchestrator,
                "_now",
                side_effect=lambda: clock["now"],
            ),
        ):
            result = album_sync_orchestrator._collect_and_execute_album_in_chunks(  # noqa: SLF001
                album,
                "/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=chunk_size,
            )
        return result, [[t["item"] for t in call.args[0]] for call in run.call_args_list]

    def test_a_pending_download_does_not_wait_for_the_walk_to_end(self):
        """One new photo at minute 0, then a long stretch already on disk."""
        p = [Mock(name=f"p{i}") for i in range(4)]
        minutes = {p[0]: 0, p[1]: 5, p[2]: 11, p[3]: 40}

        result, drains = self._walk(p, minutes, needs_download={p[0]})

        self.assertEqual(result, (1, 0))
        # Drained at minute 11, not at the end of the walk (minute 40).
        self.assertEqual(drains, [[p[0]]])
        self.assertGreaterEqual(minutes[p[2]] * 60, BUFFERED_DOWNLOAD_MAX_AGE_SEC)

    def test_the_age_restarts_after_each_drain(self):
        """A later download gets its own ten minutes; batching is kept."""
        p = [Mock(name=f"p{i}") for i in range(6)]
        minutes = {p[0]: 0, p[1]: 11, p[2]: 12, p[3]: 13, p[4]: 22, p[5]: 23}

        _, drains = self._walk(p, minutes, needs_download={p[0], p[2], p[3]})

        # p0 ages out at p1; p2 and p3 then batch together until p4.
        self.assertEqual(drains, [[p[0]], [p[2], p[3]]])

    def test_a_fresh_buffer_waits_for_chunk_size(self):
        p = [Mock(name=f"p{i}") for i in range(3)]
        minutes = dict.fromkeys(p, 0)

        _, drains = self._walk(p, minutes, needs_download=set(p))

        self.assertEqual(drains, [p])  # only the final drain

    def test_the_real_clock_is_monotonic(self):
        first = album_sync_orchestrator._now()  # noqa: SLF001
        self.assertLessEqual(first, album_sync_orchestrator._now())  # noqa: SLF001
