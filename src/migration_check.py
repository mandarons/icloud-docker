"""Per-photo dry-run validation — does mandarons see the right files?

Walks each iCloud photo library and, for a sample (or all) photos,
computes the on-disk path mandarons WOULD write to using the live
config (library_destinations, folder_format, filename_format) and
checks whether the file is already there with the matching size.

Used by ``--dry-run --check-files`` from ``main.py`` so users
migrating from a different downloader (e.g. boredazfcuk's
icloud_photos_downloader) can confirm the size-based existence check
will actually find their existing files BEFORE mandarons launches a
real sync. Without this check, a single misconfiguration —
filename_format wrong, folder_format missing, library_destinations
mapping a non-existent key — silently triggers a full re-download of
the user's entire library.

Pure read: no downloads, no keyring writes, no cookie writes.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
from typing import Any

from src import config_parser, get_logger
from src.photo_path_utils import (
    create_folder_path_if_needed,
    generate_photo_filename_with_metadata,
    set_default_filename_format,
)
from src.sync_photos import _library_destination

LOGGER = get_logger()


def _check_one_photo(photo, library_dest: str, folder_format: str | None) -> tuple[str, str, int, int]:
    """Compute target path + status for a single photo. Returns
    ``(status, path, expected_size, actual_size)`` where ``status`` is
    one of ``would_skip`` / ``size_mismatch`` / ``not_found`` /
    ``error``."""
    try:
        file_size = "original"
        if file_size not in photo.versions:
            return "error", "", 0, 0
        folder_path = create_folder_path_if_needed(library_dest, folder_format, photo)
        filename = generate_photo_filename_with_metadata(photo, file_size)
        target_path = os.path.join(folder_path, filename)
        expected = int(photo.versions[file_size]["size"])
    except Exception as e:
        LOGGER.debug(f"check_migration: failed to compute path for {getattr(photo, 'filename', '?')}: {e!s}")
        return "error", "", 0, 0

    if not os.path.isfile(target_path):
        return "not_found", target_path, expected, 0
    try:
        actual = os.path.getsize(target_path)
    except OSError:
        return "error", target_path, expected, 0
    if actual == expected:
        return "would_skip", target_path, expected, actual
    return "size_mismatch", target_path, expected, actual


def check_library(
    library,
    library_name: str,
    photos_base: str,
    mapping: dict,
    folder_format: str | None,
    sample: int,
) -> dict[str, Any]:
    """Walk a single library and accumulate per-status counters.

    ``sample=0`` walks every photo (slow on large libraries).
    ``sample>0`` walks the first N (newest-first per icloudpy's
    iterator). Pagination cost is proportional to the number of
    photos walked, so a sample of 200 is usually sub-minute; a sample
    of 5000 can take several minutes on a 100K-photo library.

    Note on bias: iCloud's iterator is newest-first, so a small N
    skews toward recent photos and gives you no signal about whether
    older files (which a migration tool would have downloaded years
    ago) will match. Use a sample size proportional to the time
    range you care about validating.
    """
    library_dest = _library_destination(photos_base, library_name, mapping)
    stats = {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0}
    samples = {"would_skip": [], "size_mismatch": [], "not_found": []}

    seen = 0
    checked = 0
    try:
        for photo in library.albums["All Photos"]:
            if sample > 0 and checked >= sample:
                break
            seen += 1
            checked += 1
            status, path, expected, actual = _check_one_photo(photo, library_dest, folder_format)
            stats[status] = stats.get(status, 0) + 1
            if status in samples and len(samples[status]) < 3:
                if status == "size_mismatch":
                    samples[status].append((path, expected, actual))
                else:
                    samples[status].append((path, expected))
    except Exception as e:
        LOGGER.warning(f"check_migration: walk of {library_name} stopped early: {e!s}")

    return {
        "library_dest": library_dest,
        "checked": checked,
        "seen": seen,
        "stats": stats,
        "samples": samples,
    }


def check_migration(api, config: dict, sample: int = 0) -> dict[str, Any]:
    """Walk every photo library and report what a real sync would do.

    Args:
        api: Authenticated ICloudPyService instance.
        config: Live config dict (read_config output).
        sample: Photos per library to check. ``0`` means all (slow on
            large libraries — only use after a small-sample run has
            confirmed the mapping looks right).

    Returns:
        Dict keyed by library name → per-library result dict (see
        ``check_library``).
    """
    photos_base = config_parser.prepare_photos_destination(config=config)
    mapping = config_parser.get_photos_library_destinations(config=config)
    folder_format = config_parser.get_photos_folder_format(config=config)

    # mandarons' sync_photos.sync_photos() normally sets this singleton
    # via set_default_filename_format(). When the user invokes us via
    # --dry-run we never go through that path, so we have to set it
    # ourselves — otherwise every call to
    # generate_photo_filename_with_metadata returns the legacy metadata-
    # style name regardless of the config setting.
    filename_format = (config.get("photos", {}) or {}).get("filename_format")
    if filename_format:
        set_default_filename_format(filename_format)

    results: dict[str, Any] = {}
    for library_name in api.photos.libraries:
        LOGGER.info(f"check_migration: walking library {library_name} (sample={sample or 'all'}) ...")
        library = api.photos.libraries[library_name]
        results[library_name] = check_library(
            library=library,
            library_name=library_name,
            photos_base=photos_base,
            mapping=mapping,
            folder_format=folder_format,
            sample=sample,
        )
    return results
