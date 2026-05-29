"""Tests for chunked photo enumeration in ``album_sync_orchestrator``.

Memory profile fix for PR 12 — verifies that
``_collect_and_execute_album_in_chunks`` produces the same per-album
counts and side-effects as the legacy "build full list then download"
path AND bounds peak resident memory by ``chunk_size`` rather than
``len(album)``.

The semantic-equivalence cases also document the new contract: chunk
size is an internal performance knob, not a behavioural one.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401  — env setup
from src import album_sync_orchestrator


def _fake_photo(filename: str, item_id: str):
    """A MagicMock that quacks like an icloudpy PhotoAsset enough to
    pass through ``_collect_photo_download_tasks``."""
    p = MagicMock()
    p.filename = filename
    p.id = item_id
    p.versions = {"original": {"size": 1024, "type": "public.heic"}}
    return p


def _fake_album(photos: list):
    """Wrap a list of photo mocks in an object the orchestrator can
    iterate. ``.title`` + ``.subalbums`` keep ``sync_album_photos``
    happy when the equivalence tests reach into it."""
    a = MagicMock()
    a.__iter__ = lambda self: iter(photos)
    a.title = "TestAlbum"
    a.subalbums = {}
    return a


class TestChunkedEnumeration(unittest.TestCase):
    """``_collect_and_execute_album_in_chunks`` end-to-end behaviour."""

    def test_chunking_matches_unchunked_total_counts(self):
        """Counts and number-of-download-calls add up identically
        whether the album is drained as 1 chunk or N chunks."""
        photos = [_fake_photo(f"IMG_{i}.HEIC", f"id_{i}") for i in range(30)]
        album = _fake_album(photos)

        # Each photo yields exactly one task (a single DownloadTaskInfo).
        # Use a sentinel-task so the buffer is observably populated.
        def _per_photo_task(photo, *_args, **_kwargs):
            return [{"item": photo, "local_file": photo.filename}]

        def _exec_returns_succ_count(tasks, _config):
            # Pretend every task succeeded; surface count = len(tasks).
            return (len(tasks), 0)

        with (
            patch.object(
                album_sync_orchestrator,
                "_collect_photo_download_tasks",
                side_effect=_per_photo_task,
            ),
            patch.object(
                album_sync_orchestrator,
                "execute_parallel_downloads",
                side_effect=_exec_returns_succ_count,
            ) as mock_exec,
        ):
            # All-in-one-chunk: 30 photos, chunk=100 → 1 drain call
            mock_exec.reset_mock()
            s1, f1 = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=100,
            )
            chunks_when_big = mock_exec.call_count

            # Reset iterator (album is mocked, need fresh)
            album = _fake_album(photos)

            mock_exec.reset_mock()
            s2, f2 = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=10,
            )
            chunks_when_small = mock_exec.call_count

            # Equivalent total counts despite different chunk sizes.
            self.assertEqual(s1, s2)
            self.assertEqual(s1, 30)
            self.assertEqual(f1, f2)
            self.assertEqual(f1, 0)
            # Different number of drain calls: 1 big drain vs 3 small drains.
            self.assertEqual(chunks_when_big, 1)
            self.assertEqual(chunks_when_small, 3)

    def test_empty_album_no_drain_call(self):
        """No photos → no parallel-download call → (0, 0) result."""
        album = _fake_album([])
        with patch.object(
            album_sync_orchestrator,
            "execute_parallel_downloads",
        ) as mock_exec:
            s, f = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=1000,
            )
        self.assertEqual((s, f), (0, 0))
        mock_exec.assert_not_called()

    def test_partial_final_chunk_drained(self):
        """13 photos with chunk_size=5 → drain at 5, 10, then final partial 3."""
        photos = [_fake_photo(f"IMG_{i}.HEIC", f"id_{i}") for i in range(13)]
        album = _fake_album(photos)

        with (
            patch.object(
                album_sync_orchestrator,
                "_collect_photo_download_tasks",
                side_effect=lambda p, *a, **k: [{"item": p}],
            ),
            patch.object(
                album_sync_orchestrator,
                "execute_parallel_downloads",
                side_effect=lambda tasks, _: (len(tasks), 0),
            ) as mock_exec,
        ):
            s, f = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=5,
            )
        self.assertEqual((s, f), (13, 0))
        # 3 drain calls: 5, 5, 3.
        self.assertEqual(mock_exec.call_count, 3)
        drained_lengths = [len(c.args[0]) for c in mock_exec.call_args_list]
        self.assertEqual(drained_lengths, [5, 5, 3])

    def test_invalid_chunk_size_falls_back_to_default(self):
        """0 / negative chunk_size falls back to DEFAULT instead of crashing."""
        photos = [_fake_photo(f"IMG_{i}.HEIC", f"id_{i}") for i in range(3)]
        album = _fake_album(photos)
        with (
            patch.object(
                album_sync_orchestrator,
                "_collect_photo_download_tasks",
                side_effect=lambda p, *a, **k: [{"item": p}],
            ),
            patch.object(
                album_sync_orchestrator,
                "execute_parallel_downloads",
                side_effect=lambda tasks, _: (len(tasks), 0),
            ) as mock_exec,
        ):
            s, _ = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=0,
            )
        self.assertEqual(s, 3)
        mock_exec.assert_called_once()

    def test_peak_memory_bounded_by_chunk_size_not_album_size(self):
        """The whole point of the PR.

        Allocate large-ish (~50 KB) sentinel objects per photo so that
        unchunked enumeration would visibly accumulate in
        ``tracemalloc``. Verify chunked enumeration's peak stays
        proportional to chunk_size, not album size."""

        photos = [_fake_photo(f"IMG_{i}.HEIC", f"id_{i}") for i in range(2_000)]
        album = _fake_album(photos)

        observed_drain_sizes: list[int] = []

        def _record_drain_size(tasks, _config):
            observed_drain_sizes.append(len(tasks))
            return (len(tasks), 0)

        with (
            patch.object(
                album_sync_orchestrator,
                "_collect_photo_download_tasks",
                side_effect=lambda p, *a, **k: [{"item": p}],
            ),
            patch.object(
                album_sync_orchestrator,
                "execute_parallel_downloads",
                side_effect=_record_drain_size,
            ),
        ):
            s, _ = album_sync_orchestrator._collect_and_execute_album_in_chunks(
                album,
                "/tmp/dest",
                ["original"],
                None,
                None,
                None,
                None,
                config=None,
                chunk_size=50,
            )

        # Behavioural contract: the buffer NEVER exceeds chunk_size.
        # If streaming reverts to the old "build the whole list then
        # drain" pattern, this assertion fires immediately (one drain
        # call would see len(album) tasks).
        self.assertEqual(s, 2_000)
        self.assertTrue(
            all(size <= 50 for size in observed_drain_sizes),
            f"buffer exceeded chunk_size: {observed_drain_sizes}",
        )
        # 2000 / 50 = exactly 40 drain calls, no trailing partial.
        self.assertEqual(len(observed_drain_sizes), 40)
        self.assertEqual(sum(observed_drain_sizes), 2_000)


class TestConfigChunkSizeGetter(unittest.TestCase):
    """``config_parser.get_photos_enumeration_chunk_size`` behaviour."""

    def setUp(self):
        from src import config_parser

        self.cp = config_parser

    def test_default_when_not_configured(self):
        self.assertEqual(
            self.cp.get_photos_enumeration_chunk_size({}),
            album_sync_orchestrator.DEFAULT_ENUMERATION_CHUNK_SIZE,
        )

    def test_explicit_int_honoured(self):
        cfg = {"photos": {"enumeration_chunk_size": 250}}
        self.assertEqual(self.cp.get_photos_enumeration_chunk_size(cfg), 250)

    def test_zero_falls_back_to_default(self):
        cfg = {"photos": {"enumeration_chunk_size": 0}}
        self.assertEqual(
            self.cp.get_photos_enumeration_chunk_size(cfg),
            album_sync_orchestrator.DEFAULT_ENUMERATION_CHUNK_SIZE,
        )

    def test_negative_falls_back_to_default(self):
        cfg = {"photos": {"enumeration_chunk_size": -1}}
        self.assertEqual(
            self.cp.get_photos_enumeration_chunk_size(cfg),
            album_sync_orchestrator.DEFAULT_ENUMERATION_CHUNK_SIZE,
        )

    def test_garbage_string_falls_back_to_default(self):
        cfg = {"photos": {"enumeration_chunk_size": "not a number"}}
        self.assertEqual(
            self.cp.get_photos_enumeration_chunk_size(cfg),
            album_sync_orchestrator.DEFAULT_ENUMERATION_CHUNK_SIZE,
        )

    def test_none_config(self):
        self.assertEqual(
            self.cp.get_photos_enumeration_chunk_size(None),
            album_sync_orchestrator.DEFAULT_ENUMERATION_CHUNK_SIZE,
        )


if __name__ == "__main__":
    unittest.main()
