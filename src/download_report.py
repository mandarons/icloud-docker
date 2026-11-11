"""Per-run record of photo transfers that could not be verified.

A failed transfer is still retried on the next sync, but it is now visible:
the asset is recorded once per run with its declared and received byte counts,
and a single summary line closes the run. The report is process-local; the
sync loop is the only writer.
"""

from threading import Lock

from src import get_logger

LOGGER = get_logger()

# Paths named in the summary line before it switches to a count.
_SUMMARY_PATH_LIMIT = 5


class DownloadReport:
    """Unverified transfers for one photo-sync run, keyed by path and variant."""

    def __init__(self) -> None:
        """Initialize an empty report."""
        self._failures: dict[tuple[str, str], dict] = {}
        self._lock = Lock()

    def record(self, failure: dict) -> bool:
        """Record one failure, logging it once per path and version.

        Args:
            failure: Fields describing the failed transfer (``path``,
                ``file_size``, ``asset_id``, ``reason``, ``declared_bytes``,
                ``received_bytes``).

        Returns:
            True when this failure was not already recorded, False otherwise.
        """
        key = (failure["path"], failure["file_size"])
        with self._lock:
            if key in self._failures:
                return False
            self._failures[key] = failure

        LOGGER.error(
            f"Could not verify photo {failure['path']} "
            f"(asset {failure.get('asset_id') or '<unknown>'}, {failure['file_size']}): "
            f"{failure['reason']} - declared {failure.get('declared_bytes')} bytes, "
            f"received {failure.get('received_bytes')} bytes. Will retry on the next sync.",
        )
        return True

    def unverified(self) -> list[dict]:
        """Return a snapshot of the recorded failures."""
        with self._lock:
            return list(self._failures.values())

    def __len__(self) -> int:
        """Return how many distinct transfers are unverified."""
        with self._lock:
            return len(self._failures)


_report = DownloadReport()


def reset_download_report() -> None:
    """Start a fresh report for a new photo-sync run."""
    global _report  # noqa: PLW0603 - one report per process, swapped per run
    _report = DownloadReport()


def get_download_report() -> DownloadReport:
    """Return the report for the current run."""
    return _report


def log_download_summary() -> int:
    """Log the run's unverified count, if any, and return it."""
    failures = _report.unverified()
    if not failures:
        return 0

    paths = ", ".join(failure["path"] for failure in failures[:_SUMMARY_PATH_LIMIT])
    remaining = len(failures) - _SUMMARY_PATH_LIMIT
    suffix = f" (+{remaining} more)" if remaining > 0 else ""
    LOGGER.error(f"{len(failures)} photo(s) could not be verified this run: {paths}{suffix}")
    return len(failures)
