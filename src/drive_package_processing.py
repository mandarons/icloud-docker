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


def process_package(local_file: str) -> str | None:
    """Process and extract a downloaded package file.

    This function handles different archive types (ZIP, gzip) and extracts them
    to the appropriate location. It also handles Unicode normalization for
    cross-platform compatibility.

    Args:
        local_file: Path to the downloaded package file

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
    LOGGER.info(f"Unpacking {archive_file} to {os.path.dirname(archive_file)}")
    zipfile.ZipFile(archive_file).extractall(path=os.path.dirname(archive_file))

    # Handle Unicode normalization for cross-platform compatibility
    normalized_path = unicodedata.normalize("NFD", local_file)
    if normalized_path != local_file:
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
