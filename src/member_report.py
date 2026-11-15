"""What a member's first backup would do, worked out without writing anything.

A member who arrives with a tree another tool already saved (``photos.adopt``)
gets this report before their first download: how many photos are already
on disk under this app's names, how many under the old tool's names, how
many would download (by year, so "the photos since the old tool stopped"
is visible at a glance), and how many files in the tree no photo claims:
with ``remove_obsolete`` on, exactly the files the first pass deletes,
counted the way the cleanup counts them. The household page shows it
with a button that starts the real backup.

Strictly read-only: paths are computed, never created; the tree is listed,
never changed; nothing is downloaded.
"""

import os
import time
from collections import Counter
from typing import Any

from src import config_parser, get_logger
from src.photo_adopt import Adopter, expected_path
from src.photo_download_manager import _size_present

LOGGER = get_logger()

_SAMPLES = 3


def library_folder(member: dict) -> str:
    """The member's library folder, the one cleanup walks; never created."""
    photos_base = os.path.join(
        config_parser.get_root_destination_path(config=member),
        config_parser.get_photos_destination_path(config=member),
    )
    mapping = config_parser.get_photos_library_destinations(config=member)
    return os.path.normpath(os.path.join(photos_base, mapping.get("PrimarySync", "")))


def library_base(member: dict) -> str:
    """The folder a member's dated folders hang off, computed without writing."""
    folder = library_folder(member)
    all_folder = config_parser.get_photos_all_folder(config=member)
    return os.path.normpath(os.path.join(folder, all_folder) if all_folder else folder)


def _note(samples: dict, kind: str, path: str, base: str) -> None:
    bucket = samples.setdefault(kind, [])
    if len(bucket) < _SAMPLES:
        bucket.append(os.path.relpath(path, base))


def _unclaimed(root: str, claimed: set[str], marker: str) -> tuple[int, int, list[str]]:
    """Files under ``root`` no photo claims, files in all, and a few names.

    Counted the way ``remove_obsolete_files`` counts: every file but the
    mount marker, matched on the exact path. These are the files cleanup
    would delete.
    """
    present, count, samples = 0, 0, []
    for folder, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(folder, name)
            present += 1
            if path in claimed or name == marker:
                continue
            count += 1
            if len(samples) < _SAMPLES:
                samples.append(os.path.relpath(path, root))
    return count, present, samples


def build(photos, member: dict) -> dict[str, Any]:
    """Walk the member's personal library once and classify every file.

    ``photos`` is the member's ``api.photos``. Returns a JSON-ready dict.
    """
    from src.sync_photos import apply_naming_settings

    started = time.time()
    filters = apply_naming_settings(member)
    file_sizes = filters.get("file_sizes") or ["original"]
    folder_format = config_parser.get_photos_folder_format(config=member)
    base = library_base(member)
    adopter = Adopter(config_parser.get_photos_adopt(config=member) or "icloudpd")
    claimed: set[str] = set()
    counts: Counter = Counter()
    missing_by_year: Counter = Counter()
    samples: dict[str, list[str]] = {}
    assets = 0
    stopped = None
    try:
        for photo in photos.libraries["PrimarySync"].all:
            assets += 1
            for file_size in file_sizes:
                if not _size_present(photo, file_size, photo.versions):
                    continue
                try:
                    path = expected_path(photo, file_size, base, folder_format)
                    size = int(photo.versions[file_size]["size"])
                except AttributeError, KeyError, TypeError, ValueError:
                    # The sync itself skips such a photo with a warning.
                    counts["unreadable"] += 1
                    continue
                if os.path.isfile(path) and os.path.getsize(path) == size and path not in claimed:
                    counts["on_disk"] += 1
                    claimed.add(path)
                    continue
                found = adopter.find(photo, file_size, base, folder_format, claimed=claimed)
                if found is not None:
                    counts["old_name"] += 1
                    claimed.add(found)
                    _note(samples, "old_name", found, base)
                    continue
                counts["download"] += 1
                missing_by_year[str(photo.created.year)] += 1
                _note(samples, "download", path, base)
    except Exception as e:  # noqa: BLE001 - a partial report says so instead of vanishing
        stopped = str(e)
        LOGGER.warning(f"Member report: the walk stopped early: {e!s}")

    marker = config_parser.get_mount_marker_filename(config=member)
    # Cleanup walks the library's whole folder, which is ``base`` itself
    # unless an ``all`` folder sits in between.
    root = library_folder(member)
    unclaimed, present, unclaimed_samples = _unclaimed(root, claimed, marker) if os.path.isdir(root) else (0, 0, [])
    deletes = config_parser.get_photos_remove_obsolete(config=member)
    limit = config_parser.get_photos_obsolete_delete_limit_percent(config=member)
    report = {
        "at": time.time(),
        "seconds": round(time.time() - started),
        "folder": os.path.basename(base) or base,
        "assets": assets,
        "on_disk": counts["on_disk"],
        "old_name": counts["old_name"],
        "download": counts["download"],
        "download_by_year": dict(sorted(missing_by_year.items())),
        "unreadable": counts["unreadable"],
        "unclaimed": unclaimed,
        "deletes": deletes,
        # Cleanup refuses, and deletes nothing, when this share is over
        # the limit: the page says so rather than promising deletions.
        "over_limit": bool(deletes and limit > 0 and present and 100 * unclaimed / present > limit),
        "limit": limit,
        "samples": {**samples, "unclaimed": unclaimed_samples},
    }
    if stopped:
        report["stopped"] = stopped
    LOGGER.info(
        f"Member report: {assets} photos; {report['on_disk']} files already in place, "
        f"{report['old_name']} under the old names, {report['download']} to download, "
        f"{unclaimed} unclaimed files in the folder{' (cleanup deletes them)' if deletes else ''}",
    )
    return report
