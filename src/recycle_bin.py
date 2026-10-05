"""Recycle bin for obsolete-file cleanup.

When ``app.recycle_bin.enabled`` is set, files and folders that obsolete-file
cleanup would delete are moved to ``<app.root>/Recently Deleted/<service>/
<YYYY-MM-DD>/<path relative to the service destination>`` instead, and kept
for ``app.recycle_bin.retention_days`` (or forever when that is unset).

The bin only changes *how* cleanup removes something, never *what* it
removes: with ``remove_obsolete`` off, nothing is cleaned up and nothing
reaches the bin.
"""

import datetime
import os
import shutil
from pathlib import Path

from src import get_logger

LOGGER = get_logger()

BIN_DIRECTORY_NAME = "Recently Deleted"


class RecycleBin:
    """Where one service's cleanup puts what it removes."""

    def __init__(
        self,
        root: str,
        service: str,
        retention_days: int | None = None,
        today: datetime.date | None = None,
    ):
        """Create the bin for ``service`` under ``root``.

        Args:
            root: ``app.root``, the parent of every service destination
            service: ``drive`` or ``photos``; each gets its own folder
            retention_days: Days to keep a day's folder; None keeps forever
            today: Override for tests
        """
        self.path = os.path.abspath(os.path.join(root, BIN_DIRECTORY_NAME, service))
        self.retention_days = retention_days
        self.today = today or datetime.date.today()

    def contains(self, path: str) -> bool:
        """True if ``path`` is the bin or inside it.

        A destination can be ``app.root`` itself, so cleanup walks would
        otherwise find the bin and treat everything in it as obsolete.
        """
        absolute = os.path.abspath(path)
        top = os.path.dirname(self.path)
        return absolute == top or absolute.startswith(top + os.sep)

    def discard(self, path: str, destination_path: str) -> str:
        """Move ``path`` into today's folder, keeping its place in the tree.

        Args:
            path: File or folder that cleanup would delete
            destination_path: The service destination ``path`` lives under

        Returns:
            Where it was moved to
        """
        relative = os.path.relpath(
            os.path.abspath(path), os.path.abspath(destination_path),
        )
        target = os.path.join(self.path, self.today.isoformat(), relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        # The same path can be removed twice in a day (re-downloaded, then
        # dropped again); keep both rather than overwrite the first.
        candidate, n = target, 2
        while os.path.lexists(candidate):
            candidate = f"{target} ({n})"
            n += 1
        shutil.move(path, candidate)
        return candidate

    def purge(self) -> int:
        """Delete day folders older than the retention period.

        Returns:
            Number of day folders deleted
        """
        if self.retention_days is None or not os.path.isdir(self.path):
            return 0
        cutoff = self.today - datetime.timedelta(days=self.retention_days)
        purged = 0
        for day in sorted(Path(self.path).iterdir()):
            try:
                day_date = datetime.date.fromisoformat(day.name)
            except ValueError:
                continue  # not a folder the bin made; leave it alone
            if day.is_dir() and day_date < cutoff:
                LOGGER.info(
                    f"Recycle bin: deleting {day}, older than {self.retention_days} days ...",
                )
                shutil.rmtree(day)
                purged += 1
        return purged


def from_config(config: dict | None, service: str) -> RecycleBin | None:
    """The bin for ``service`` if ``app.recycle_bin.enabled``, else None."""
    from src import config_parser

    if not config or not config_parser.get_recycle_bin_enabled(config=config):
        return None
    return RecycleBin(
        root=config_parser.get_root_destination_path(config=config),
        service=service,
        retention_days=config_parser.get_recycle_bin_retention_days(config=config),
    )
