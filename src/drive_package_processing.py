"""Package processing utilities.

This module provides package extraction and processing functionality,
separating archive handling logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import gzip
import os
import unicodedata
import zipfile
from shutil import copyfileobj

import magic

from src import configure_icloudpy_logging, get_logger

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def process_package(local_file: str, flatten: bool = False) -> str | None:
    """Process and extract a downloaded package file.

    This function handles different archive types (ZIP, gzip) and extracts them
    to the appropriate location. It also handles Unicode normalization for
    cross-platform compatibility.

    Args:
        local_file: Path to the downloaded package file
        flatten: When True, skip unpacking entirely and keep the package
            on disk as a single binary file (the gzip / zip bytes). Useful
            for backup-style deployments (NAS / cold storage) where bundle-
            directory semantics aren't needed and single-file storage is
            preferred for simpler dedup, restoration, and inode footprint.
            Opt-in via ``drive.flatten_packages: true`` in config.yaml.

    Returns:
        Path to the processed file/directory. The local file path is also
        returned when the mime type is not a recognised archive (the
        bytes are preserved on disk as a single-file bundle — Apple's
        iWork formats ``.key``/``.pages``/``.numbers``, JMG ``.jmb``,
        etc. report as ``application/octet-stream`` and don't need
        unpacking to be usable by their target application). Returns
        ``None`` only on hard processing errors that leave the file in
        an unusable state.
    """
    archive_file = local_file
    magic_object = magic.Magic(mime=True)
    file_mime_type = magic_object.from_file(filename=local_file)

    if flatten:
        # The downloaded bytes are already at local_file; nothing to do.
        # The dedup story for the next-sync cycle relies on the file_exists
        # comparator either matching size+mtime (zip case) or the operator
        # accepting a re-download (octet-stream case — see PR 11 follow-up).
        LOGGER.info(
            f"flatten_packages enabled — keeping {local_file} as single-file bundle"
            f" ({file_mime_type}); skipping unpack.",
        )
        return local_file

    if file_mime_type == "application/zip":
        return _process_zip_package(local_file, archive_file)
    elif file_mime_type == "application/gzip":
        return _process_gzip_package(local_file, archive_file)
    else:
        # NOT an error — many iCloud Drive "package" downloads are flat
        # binary bundles (Apple iWork .key/.pages/.numbers,
        # third-party .jmb, etc) that report as application/octet-stream
        # but don't need to be unpacked to be usable by their target
        # application. The bytes are already on disk at ``local_file``;
        # treat that as the canonical local representation.
        LOGGER.info(
            f"Package format not recognised for unpacking ({file_mime_type}); "
            f"keeping as single-file bundle: {local_file}",
        )
        return local_file


def _zip_entries_self_prefixed(zf: zipfile.ZipFile, bundle_basename: str) -> bool:
    """Heuristic: True when every non-empty entry in the zip is rooted
    at ``<bundle_basename>/`` (with or without a leading ``../``).

    Distinguishes three zip layouts we see from iCloud Drive in the wild:

    1. **Self-prefixed** — e.g. a GarageBand ``Project.band`` whose zip
       contains entries like ``Project.band/Alternatives/000/...``.
       Extracting into the parent directory reconstructs the bundle
       correctly.

    2. **Self-prefixed with traversal** — gzip-wrapped bundles whose
       inner ZIP has entries like ``../<basename>/...``. The ``..``
       resolves to the parent of the extract target, so the end-state
       is identical to case 1 when we extract into the parent dir.

    3. **Bare-rooted** — e.g. a Numbers ``Untitled.numbers`` whose zip
       contains generic entries like ``Data/Document.iwa``,
       ``Metadata/buildVersion.plist`` etc. Two iWork files in the
       same folder will both extract ``Data/...`` into the parent dir,
       clobbering each other and raising ``FileExistsError``.

    For case 3 we need to extract into a bundle-named subdirectory of
    its own so siblings don't collide. Cases 1 and 2 keep the legacy
    "extract into parent" behaviour.
    """
    names = [n for n in zf.namelist() if n and n != bundle_basename + "/"]
    if not names:
        return False
    prefix = bundle_basename + "/"
    traversal_prefix = "../" + prefix
    return all(n.startswith((prefix, traversal_prefix)) for n in names)


def _process_zip_package(local_file: str, archive_file: str) -> str:
    """Process a ZIP package file.

    Args:
        local_file: Original file path
        archive_file: Archive file path

    Returns:
        Path to the processed file
    """
    archive_file += ".zip"
    os.rename(local_file, archive_file)
    parent_dir = os.path.dirname(archive_file)
    bundle_basename = os.path.basename(local_file)

    with zipfile.ZipFile(archive_file) as zf:
        if _zip_entries_self_prefixed(zf, bundle_basename):
            # Entries are already namespaced under the bundle name; the
            # parent dir is the right place to extract them.
            extract_dir = parent_dir
        else:
            # Entries are bare paths (Data/Document.iwa, etc). Extract
            # into the bundle directory itself so siblings in the same
            # parent folder don't collide on shared internal names.
            extract_dir = local_file
            os.makedirs(extract_dir, exist_ok=True)
        LOGGER.info(f"Unpacking {archive_file} to {extract_dir}")
        zf.extractall(path=extract_dir)

    # Handle Unicode normalization for cross-platform compatibility
    normalized_path = unicodedata.normalize("NFD", local_file)
    if normalized_path != local_file and os.path.exists(local_file):
        os.rename(local_file, normalized_path)
        local_file = normalized_path

    os.remove(archive_file)
    LOGGER.info(f"Successfully unpacked the package {archive_file}.")
    return local_file


def _process_gzip_package(local_file: str, archive_file: str) -> str | None:
    """Process a gzip package file.

    Args:
        local_file: Original file path
        archive_file: Archive file path

    Returns:
        Path to the processed file, or None if processing failed
    """
    archive_file += ".gz"
    os.rename(local_file, archive_file)
    LOGGER.info(f"Unpacking {archive_file} to {os.path.dirname(local_file)}")

    with gzip.GzipFile(filename=archive_file, mode="rb") as gz_file:
        with open(file=local_file, mode="wb") as package_file:
            copyfileobj(gz_file, package_file)

    os.remove(archive_file)

    # Recursively process the extracted file (might be another archive)
    return process_package(local_file=local_file)
