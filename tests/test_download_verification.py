"""Tests for the download verification policy and per-run failure report.

The fixtures are synthetic: they model the HTTP shapes ``PhotoAsset.download``
returns (a streamed ``requests`` response: ``raw``, ``status_code`` and
``headers``), not a recorded account response.
"""

import os
import tempfile
import unittest
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src import download_report
from src.download_report import (
    DownloadReport,
    get_download_report,
    log_download_summary,
    reset_download_report,
)
from src.photo_download_manager import DownloadTaskInfo, execute_download_task, execute_parallel_downloads
from src.photo_file_utils import (
    _asset_record_id,
    _content_length,
    _note_failure,
    download_photo_from_server,
)


class _Photo:
    """A photo whose every version is ``original`` and whose payload is fixed."""

    def __init__(self, payload: bytes, declared: int | None = None, asset_id: str | None = "asset-1"):
        self.filename = "IMG_0001.JPEG"
        self.id = "master-1"
        self.versions = {"original": {"size": len(payload) if declared is None else declared}}
        self.added_date = datetime(2021, 1, 1, 12, 0, 0, tzinfo=UTC)
        self._asset_record = {"recordName": asset_id} if asset_id else {}
        self._payload = payload

    def download(self, version, timeout=None):
        """Return a streamed success response carrying the payload."""
        return _response(self._payload)


def _response(payload: bytes, *, status: int = 200, headers: dict | None = None):
    if headers is None:
        headers = {}
    return SimpleNamespace(raw=BytesIO(payload), status_code=status, headers=headers)


class TestMismatchedTransferPolicy(unittest.TestCase):
    """A declared-size mismatch is kept only for a complete served response."""

    def test_complete_unencoded_response_is_kept(self):
        photo = _Photo(b"12345678", declared=10)
        with tempfile.TemporaryDirectory() as tmp:
            destination = os.path.join(tmp, "photo.jpeg")
            failure: dict = {}
            with (
                patch("src.photo_file_utils.LOGGER") as logger,
                patch.object(
                    photo, "download",
                    return_value=_response(b"12345678", headers={"Content-Length": "8"}),
                ),
            ):
                self.assertTrue(download_photo_from_server(photo, "original", destination, failure=failure))
            self.assertEqual(os.path.getsize(destination), 8)
            self.assertEqual(failure, {})
            logger.warning.assert_called_once()

    def test_missing_content_length_is_a_failure(self):
        self._assert_rejected(_response(b"12345678"))

    def test_http_error_body_is_a_failure(self):
        self._assert_rejected(_response(b"12345678", status=403, headers={"Content-Length": "8"}))

    def test_content_encoded_body_is_a_failure(self):
        self._assert_rejected(
            _response(b"12345678", headers={"Content-Length": "8", "Content-Encoding": "gzip"}),
        )

    def test_truncated_body_against_content_length_is_a_failure(self):
        self._assert_rejected(_response(b"12345678", headers={"Content-Length": "9"}))

    def _assert_rejected(self, response):
        photo = _Photo(b"12345678", declared=10)
        with tempfile.TemporaryDirectory() as tmp:
            destination = os.path.join(tmp, "photo.jpeg")
            failure: dict = {}
            with patch.object(photo, "download", return_value=response):
                self.assertFalse(download_photo_from_server(photo, "original", destination, failure=failure))
            self.assertFalse(os.path.exists(destination))
            self.assertFalse(os.path.exists(f"{destination}.part"))
            self.assertEqual(failure["reason"], "size_mismatch")
            self.assertEqual(failure["declared_bytes"], 10)
            self.assertEqual(failure["received_bytes"], 8)
            self.assertEqual(failure["asset_id"], "asset-1")

    def test_matching_size_still_succeeds(self):
        photo = _Photo(b"12345678")
        with tempfile.TemporaryDirectory() as tmp:
            destination = os.path.join(tmp, "photo.jpeg")
            failure: dict = {}
            self.assertTrue(download_photo_from_server(photo, "original", destination, failure=failure))
            self.assertEqual(os.path.getsize(destination), 8)
            self.assertEqual(failure, {})

    def test_no_declared_size_is_not_second_guessed(self):
        photo = _Photo(b"12345678", declared=0)
        photo.versions = {"original": {}}
        with tempfile.TemporaryDirectory() as tmp:
            destination = os.path.join(tmp, "photo.jpeg")
            self.assertTrue(download_photo_from_server(photo, "original", destination))


class TestFailureDetails(unittest.TestCase):
    """The failure record carries the asset identity and byte counts."""

    def test_asset_id_prefers_the_asset_record(self):
        self.assertEqual(_asset_record_id(_Photo(b"x")), "asset-1")

    def test_asset_id_falls_back_to_the_master(self):
        photo = _Photo(b"x", asset_id=None)
        photo._asset_record = {}  # noqa: SLF001 - the field icloudpy exposes
        self.assertEqual(_asset_record_id(photo), "master-1")

    def test_asset_id_is_none_when_unreadable(self):
        class Broken:
            @property
            def id(self):
                msg = "recordName"
                raise KeyError(msg)

        self.assertIsNone(_asset_record_id(Broken()))

    def test_note_failure_without_a_record_is_a_no_op(self):
        _note_failure(None, _Photo(b"x"), "original", "/tmp/x", "size_mismatch", 1, 2)

    def test_content_length_ignores_garbage(self):
        self.assertIsNone(_content_length(SimpleNamespace(headers={"Content-Length": "many"})))


class TestDownloadReport(unittest.TestCase):
    """Failures are recorded and logged once per asset per run."""

    def setUp(self):
        reset_download_report()

    def tearDown(self):
        reset_download_report()

    def _failure(self, n: int) -> dict:
        return {
            "path": f"/photos/{n}.jpeg",
            "file_size": "original",
            "asset_id": f"asset-{n}",
            "reason": "size_mismatch",
            "declared_bytes": 10,
            "received_bytes": 8,
        }

    def test_duplicate_is_recorded_and_logged_once(self):
        report = get_download_report()
        with patch.object(download_report.LOGGER, "error") as log:
            self.assertTrue(report.record(self._failure(1)))
            self.assertFalse(report.record(self._failure(1)))
        self.assertEqual(len(report), 1)
        self.assertEqual(log.call_count, 1)
        self.assertIn("asset-1", log.call_args.args[0])

    def test_summary_names_paths_then_counts_the_remainder(self):
        report = get_download_report()
        for n in range(7):
            report.record(self._failure(n))
        with patch.object(download_report.LOGGER, "error") as log:
            self.assertEqual(log_download_summary(), 7)
        message = log.call_args.args[0]
        self.assertIn("/photos/0.jpeg", message)
        self.assertIn("(+2 more)", message)

    def test_summary_is_silent_without_failures(self):
        self.assertEqual(log_download_summary(), 0)

    def test_reset_starts_an_empty_report(self):
        get_download_report().record(self._failure(1))
        reset_download_report()
        self.assertEqual(len(get_download_report()), 0)

    def test_unverified_returns_a_snapshot(self):
        report = DownloadReport()
        report.record(self._failure(1))
        snapshot = report.unverified()
        snapshot.append(self._failure(2))
        self.assertEqual(len(report), 1)


class TestOwnershipAfterVerification(unittest.TestCase):
    """``files`` is granted only after a write (or hardlink) succeeds."""

    def setUp(self):
        reset_download_report()

    def tearDown(self):
        reset_download_report()

    def test_success_claims_the_path(self):
        task = DownloadTaskInfo(_Photo(b"12345678"), "original", "/photos/one.jpeg")
        task.files = set()
        with patch("src.photo_download_manager.download_photo_from_server", return_value=True):
            self.assertTrue(execute_download_task(task))
        self.assertEqual(task.files, {"/photos/one.jpeg"})

    def test_failure_does_not_claim_the_path_and_is_reported(self):
        photo = MagicMock()
        photo.id = "master-1"
        photo._asset_record = {"recordName": "asset-1"}  # noqa: SLF001 - icloudpy's field
        photo.versions = {"original": {"size": 10}}
        photo.download.side_effect = Exception("Gone (410)")  # noqa: EM101
        task = DownloadTaskInfo(photo, "original", "/photos/one.jpeg")
        task.files = set()
        with patch("src.photo_file_utils._refresh_photo_download_url", return_value=False):
            self.assertFalse(execute_download_task(task))
        self.assertEqual(task.files, set())
        self.assertEqual(len(get_download_report()), 1)
        self.assertEqual(get_download_report().unverified()[0]["reason"], "gone_410")

    def test_no_files_set_is_a_no_op(self):
        task = DownloadTaskInfo(_Photo(b"12345678"), "original", "/photos/one.jpeg")
        task.files = None
        with patch("src.photo_download_manager.download_photo_from_server", return_value=True):
            self.assertTrue(execute_download_task(task))

    def test_parallel_execution_grants_ownership_on_success(self):
        from concurrent.futures import Future

        class _InlineExecutor:
            """Run each submitted task immediately, like a one-worker pool."""

            def __init__(self, max_workers=None):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def submit(self, fn, task):
                future = Future()
                future.set_result(fn(task))
                return future

        task = DownloadTaskInfo(_Photo(b"12345678"), "original", "/photos/one.jpeg")
        files: set[str] = set()
        task.files = files
        with (
            patch("src.photo_download_manager.ThreadPoolExecutor", _InlineExecutor),
            patch("src.photo_download_manager.download_photo_from_server", return_value=True),
        ):
            successful, failed = execute_parallel_downloads([task], {"app": {"max_threads": 1}})
        self.assertEqual((successful, failed), (1, 0))
        self.assertEqual(files, {"/photos/one.jpeg"})


if __name__ == "__main__":
    unittest.main()
