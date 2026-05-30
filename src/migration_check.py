"""Per-file dry-run validation — does mandarons see the right files?

Walks each iCloud photo library AND iCloud Drive and, for a sample
(or all) items, computes the on-disk path mandarons WOULD write to
using the live config (library_destinations, folder_format,
filename_format for photos; mirror-tree for drive) and checks whether
the file is already there with the matching size.

Used by ``--dry-run --check-files`` from ``main.py`` so users
migrating from a different downloader (e.g. boredazfcuk's
icloud_photos_downloader) can confirm the size-based existence check
will actually find their existing files BEFORE mandarons launches a
real sync. Without this check, a single misconfiguration —
filename_format wrong, folder_format missing, library_destinations
mapping a non-existent key, drive destination pointing at the wrong
mount — silently triggers a full re-download of the user's entire
library.

Pure read: no downloads, no keyring writes, no cookie writes.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from src import config_parser, get_logger
from src.photo_path_utils import (
    create_folder_path_if_needed,
    generate_photo_filename_with_metadata,
)

# These two symbols ship in companion PRs (``feat/photos-filename-format-simple``
# and ``feat/photos-library-destinations``). When those land first the
# real functions are used; when this PR is reviewed/merged in isolation
# the no-op fallbacks let the suite import + run, so the migration-check
# at least authenticates and walks the libraries (just without per-
# library subdirectories or simple-filename naming). The dry-run still
# reports something useful: "would mandarons-default paths line up with
# what's on disk?"
try:
    from src.photo_path_utils import set_default_filename_format  # type: ignore[attr-defined]
except (
    ImportError
):  # pragma: no cover — only when feat/photos-filename-format-simple isn't merged

    def set_default_filename_format(_filename_format: str) -> None:
        """No-op fallback — feat/photos-filename-format-simple not merged."""


try:
    from src.sync_photos import _library_destination  # type: ignore[attr-defined]
except (
    ImportError
):  # pragma: no cover — only when feat/photos-library-destinations isn't merged

    def _library_destination(
        base_destination: str,
        library: str,
        library_destinations: dict,
    ) -> str:
        """Fallback that always returns the base destination.

        feat/photos-library-destinations introduces per-library subdir
        mapping; without it, mandarons writes every library to the
        single base destination. The migration-check reports against
        that same path.
        """
        return base_destination


LOGGER = get_logger()


def _check_one_photo(
    photo,
    library_dest: str,
    folder_format: str | None,
) -> tuple[str, str, int, int]:
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
        LOGGER.debug(
            f"check_migration: failed to compute path for {getattr(photo, 'filename', '?')}: {e!s}",
        )
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
            status, path, expected, actual = _check_one_photo(
                photo,
                library_dest,
                folder_format,
            )
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
    # Defensive: feat/photos-library-destinations may not be merged yet.
    # Falls back to an empty mapping (every library writes to the same
    # photos_base) so this PR is independent of PR 3.
    if hasattr(config_parser, "get_photos_library_destinations"):
        mapping = config_parser.get_photos_library_destinations(config=config)
    else:  # pragma: no cover — only when feat/photos-library-destinations isn't merged
        mapping = {}
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
        LOGGER.info(
            f"check_migration: walking library {library_name} (sample={sample or 'all'}) ...",
        )
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


def _check_one_drive_file(item, local_path: str) -> tuple[str, str, int, int]:
    """Compute status for a single Drive file item.

    Returns ``(status, path, expected_size, actual_size)`` where
    ``status`` is one of ``would_skip`` / ``size_mismatch`` /
    ``not_found`` / ``error``.

    Handles BOTH on-disk forms a Drive item can take:
      - regular file (most items, plus packages that mandarons couldn't
        unpack like .key / .jmb — bytes saved flat)
      - directory tree (packages mandarons successfully unpacked, e.g.
        .band GarageBand projects)

    Size comparison matches mandarons' real-sync ``file_exists`` /
    ``package_exists`` semantics: flat-file size for regular files,
    sum of contained file sizes for directory packages.
    """
    try:
        expected = int(item.size) if getattr(item, "size", None) is not None else 0
    except Exception as e:
        LOGGER.debug(
            f"check_migration: drive item bad size for {getattr(item, 'name', '?')}: {e!s}",
        )
        return "error", local_path, 0, 0

    if os.path.isdir(local_path):
        try:
            actual = sum(
                f.stat().st_size for f in Path(local_path).glob("**/*") if f.is_file()
            )
        except OSError:
            return "error", local_path, expected, 0
    elif os.path.isfile(local_path):
        try:
            actual = os.path.getsize(local_path)
        except OSError:
            return "error", local_path, expected, 0
    else:
        return "not_found", local_path, expected, 0

    if actual == expected:
        return "would_skip", local_path, expected, actual
    return "size_mismatch", local_path, expected, actual


def _walk_drive_recursive(
    folder,
    destination_path: str,
    sample: int,
    state: dict,
) -> None:
    """Recursively walk a Drive folder, mutating ``state`` in place.

    ``state`` shape:
        {'checked': int, 'stats': {...}, 'samples': {...}}

    ``sample > 0`` caps the total file count walked (depth-first across
    the tree). ``sample == 0`` walks everything.

    Folders are followed unconditionally; only file items count against
    the sample cap (folders themselves aren't validated against disk).
    """
    if sample > 0 and state["checked"] >= sample:
        return
    try:
        items_index = folder.dir()
    except Exception as e:
        LOGGER.debug(f"check_migration: drive folder dir() failed: {e!s}")
        return
    if not items_index:
        return

    for name in items_index:
        if sample > 0 and state["checked"] >= sample:
            return
        try:
            item = folder[name]
        except Exception as e:
            LOGGER.debug(f"check_migration: drive item access failed for {name}: {e!s}")
            state["stats"]["error"] = state["stats"].get("error", 0) + 1
            continue

        item_type = getattr(item, "type", None)
        if item_type in ("folder", "app_library"):
            try:
                decoded = unquote(getattr(item, "name", name))
            except Exception:
                decoded = name
            sub_dest = unicodedata.normalize(
                "NFC",
                os.path.join(destination_path, decoded),
            )
            _walk_drive_recursive(item, sub_dest, sample, state)
        elif item_type == "file":
            try:
                decoded = unquote(getattr(item, "name", name))
            except Exception:
                decoded = name
            local_path = unicodedata.normalize(
                "NFC",
                os.path.join(destination_path, decoded),
            )
            status, path, expected, actual = _check_one_drive_file(item, local_path)
            state["stats"][status] = state["stats"].get(status, 0) + 1
            state["checked"] += 1
            if status in state["samples"] and len(state["samples"][status]) < 3:
                if status == "size_mismatch":
                    state["samples"][status].append((path, expected, actual))
                else:
                    state["samples"][status].append((path, expected))


def check_drive(drive, drive_destination: str, sample: int) -> dict[str, Any]:
    """Walk iCloud Drive and report per-file dry-run status.

    Args:
        drive: ``api.drive`` (root drive node from icloudpy).
        drive_destination: Local path where mandarons would write Drive
            content (matches what ``sync_drive`` uses).
        sample: ``0`` walks every file; ``N > 0`` walks up to N files
            total (depth-first across the folder tree). A small N gives
            quick sanity feedback; a large N (or 0) gives statistical
            confidence at the cost of pagination time.

    Returns:
        Dict with keys: ``drive_destination``, ``checked``, ``stats``,
        ``samples``. Same shape as ``check_library`` minus the
        library-specific fields.
    """
    state: dict[str, Any] = {
        "checked": 0,
        "stats": {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0},
        "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
    }
    try:
        _walk_drive_recursive(drive, drive_destination, sample, state)
    except Exception as e:
        LOGGER.warning(f"check_migration: drive walk stopped early: {e!s}")
    return {
        "drive_destination": drive_destination,
        "checked": state["checked"],
        "stats": state["stats"],
        "samples": state["samples"],
    }


def check_drive_migration(api, config: dict, sample: int = 0) -> dict[str, Any] | None:
    """Wrapper that resolves drive destination from config then walks.

    Returns None if there's no ``drive:`` section in the config — caller
    treats absence as "drive sync would be skipped at real-sync time."
    """
    if "drive" not in (config or {}):
        return None
    try:
        drive_destination = config_parser.prepare_drive_destination(config=config)
    except Exception as e:
        LOGGER.warning(f"check_migration: drive destination resolution failed: {e!s}")
        return None
    LOGGER.info(f"check_migration: walking iCloud Drive (sample={sample or 'all'}) ...")
    return check_drive(
        drive=api.drive,
        drive_destination=drive_destination,
        sample=sample,
    )
