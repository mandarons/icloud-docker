"""Recognise photos another tool already saved, under that tool's names.

A household member moving over from icloudpd has years of photos on disk
named the way icloudpd names them. Re-downloading them would double the
disk and the wait; renaming them would touch a tree someone else wrote.
So with ``photos.adopt: icloudpd`` a photo that is missing at the path
this app would use is looked for under icloudpd's names, and a file of
exactly the right size counts as already backed up. Nothing is renamed,
moved or written; the file is simply tracked where it is.

icloudpd's names, as found in a real tree:

- ``IMG_1234.HEIC``: the photo's own name, as here.
- ``IMG_1234-2205833.JPG``: a second file with the same name gets its own
  size in bytes as a suffix. Matching on that exact number never confuses
  it with a name that merely ends in digits (``IMG-20200101-WA0001``).
- ``IMG_1234_HEVC.MOV``: the video half of a Live Photo whose still is a
  HEIC. This app would call it ``IMG_1234.MOV``.
- Any case: ``.mov`` where Apple says ``.MOV``.
- Day folders in the old container's local time. ``photos.folder_timezone:
  local`` names new folders the same way; without it this app files by
  UTC and an evening photo sits one day off. The day either side is
  checked either way.

The lookup costs one directory listing per folder per pass, cached, and
a ``stat`` per candidate. It runs only when the expected file is missing.
"""

import contextvars
import os
import threading
from datetime import timedelta

from src.photo_path_utils import (
    _LIVE_VIDEO_SIZES,
    folder_date,
    generate_photo_filename_with_metadata,
    normalize_file_path,
    resolve_folder_path,
)

# The adopter for the pass running on this thread, or None. Set by the
# member sync around one pass; a pass on another thread (the primary's)
# never sees it.
ADOPTER: contextvars.ContextVar[Adopter | None] = contextvars.ContextVar("photo_adopter", default=None)

_ONE_DAY = timedelta(days=1)


class Adopter:
    """Finds a photo under another tool's name; one instance per pass."""

    def __init__(self, source: str = "icloudpd") -> None:
        self.source = source
        self.adopted = 0
        self._listings: dict[str, dict[str, list[str]]] = {}
        self._lock = threading.Lock()

    def _listing(self, folder: str) -> dict[str, list[str]]:
        """Names in ``folder``, keyed by lower case; read once per pass."""
        with self._lock:
            listing = self._listings.get(folder)
            if listing is None:
                listing = {}
                try:
                    names = os.listdir(folder)
                except OSError:
                    names = []
                for name in names:
                    listing.setdefault(name.lower(), []).append(name)
                self._listings[folder] = listing
            return listing

    @staticmethod
    def _candidate_names(basename: str, size: int, file_size: str) -> list[str]:
        stem, ext = os.path.splitext(basename)
        names = [basename, f"{stem}-{size}{ext}"]
        if file_size in _LIVE_VIDEO_SIZES:
            names = [f"{stem}_HEVC{ext}", f"{stem}_HEVC-{size}{ext}", *names]
        return names

    @staticmethod
    def _folders(expected_folder: str, base: str, folder_format: str | None, photo) -> list[str]:
        folders = [expected_folder]
        if folder_format:
            for delta in (-_ONE_DAY, _ONE_DAY):
                try:
                    shifted = os.path.join(base, (folder_date(photo) + delta).strftime(folder_format))
                except AttributeError, TypeError, ValueError, OverflowError:
                    continue
                if shifted not in folders:
                    folders.append(shifted)
        return folders

    def find(self, photo, file_size: str, base: str, folder_format: str | None, claimed=None) -> str | None:
        """The path of an existing file that is this photo version, or None.

        ``base`` is the folder the dated folders hang off; ``claimed`` is a
        container of paths other assets already own, never handed out twice.
        """
        try:
            size = int(photo.versions[file_size]["size"])
            basename = generate_photo_filename_with_metadata(photo, file_size)
            expected_folder = resolve_folder_path(base, folder_format, photo)
        except KeyError, TypeError, ValueError, AttributeError:
            return None
        names = self._candidate_names(basename, size, file_size)
        for folder in self._folders(expected_folder, base, folder_format, photo):
            listing = self._listing(folder)
            for name in names:
                for actual in listing.get(name.lower(), ()):
                    # The name on disk, untouched: the file is tracked where
                    # it is, so the path must be the one that exists.
                    path = os.path.join(folder, actual)
                    if claimed is not None and (path in claimed or normalize_file_path(path) in claimed):
                        continue
                    try:
                        if os.path.getsize(path) == size:
                            return path
                    except OSError:
                        continue
        return None


def expected_path(photo, file_size: str, base: str, folder_format: str | None) -> str:
    """Where this app would put the photo version, computed without writing."""
    folder = resolve_folder_path(base, folder_format, photo)
    return normalize_file_path(os.path.join(folder, generate_photo_filename_with_metadata(photo, file_size)))
