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

    if flatten:
        # The downloaded bytes are already at local_file; nothing to do.
        # Skip libmagic entirely -- flatten mode doesn't care what the
        # bytes are, and libmagic can fail on truncated or unusual
        # downloads where we still want to keep the bytes on disk.
        LOGGER.info(
            f"flatten_packages enabled -- keeping {local_file} as "
            f"single-file bundle; skipping unpack.",
        )
        return local_file

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


def _zip_entries_self_prefixed(zf: zipfile.ZipFile, bundle_basename: str) -> str | None:
    """Heuristic classifier for the three zip layouts iCloud Drive serves.

    Returns one of:
      - ``"self"``   — every entry starts with ``<bundle_basename>/``;
                       extract into parent_dir, safety boundary is
                       parent_dir.
      - ``"traversal"`` — every entry starts with ``../<bundle_basename>/``
                       (gzip-wrapped bundles do this). The traversal
                       resolves UP one level, so extracting into
                       parent_dir lands files in *grandparent_dir*.
                       Safety boundary must be grandparent_dir too.
      - ``None``     — bare-rooted (or empty); extract into a bundle-
                       named subdir to avoid sibling collisions.

    Differentiating ``self`` vs ``traversal`` matters for the zip-slip
    safety check: ``traversal`` is a benign-but-escape-the-extract-dir
    pattern, so the safety boundary needs to be set to the dir the
    ``..`` lands in, not the dir we passed to ``extractall``.

    The three layouts in the wild:

    1. **self** — e.g. a GarageBand ``Project.band`` whose zip contains
       entries like ``Project.band/Alternatives/000/...``. Extracting
       into the parent dir reconstructs the bundle correctly.

    2. **traversal** — gzip-wrapped bundles whose inner ZIP has
       entries like ``../<basename>/...``. The ``..`` resolves to
       the parent of the extract target, so when we extract into the
       parent dir the files end up in the grandparent. End-state is
       analogous to ``self`` but one level up.

    3. **None (bare-rooted)** — e.g. a Numbers ``Untitled.numbers``
       whose zip contains generic entries like ``Data/Document.iwa``,
       ``Metadata/buildVersion.plist``. Two iWork files in the same
       folder both extract ``Data/...`` and clobber each other; for
       this case we extract into a bundle-named subdir.
    """
    names = [n for n in zf.namelist() if n and n != bundle_basename + "/"]
    if not names:
        return None
    prefix = bundle_basename + "/"
    traversal_prefix = "../" + prefix
    if all(n.startswith(prefix) for n in names):
        return "self"
    if all(n.startswith((prefix, traversal_prefix)) for n in names):
        return "traversal"
    return None


def _safe_extractall(zf: zipfile.ZipFile, extract_dir: str, safety_boundary: str) -> None:
    """Path-validating wrapper around ``ZipFile.extractall``.

    Defends against Zip Slip (CWE-22): a malicious zip can embed entries
    with absolute paths (``/etc/passwd``) or ``..`` traversal segments
    that resolve outside the intended extract directory. iCloud Drive
    package bytes are untrusted network input -- if Apple's CloudKit
    were ever compromised, or an attacker-controlled iCloud account
    shared a poisoned package with the user, ``extractall`` would
    happily write anywhere on the filesystem.

    For each entry, resolves the final target path with ``os.path.realpath``
    and verifies it stays under ``safety_boundary`` (the directory we're
    extracting into, OR -- in the self-prefixed-with-``../`` case -- the
    parent dir whose nesting structure the zip relies on). Entries that
    escape are skipped with a WARNING.

    Args:
        zf: Open ZipFile.
        extract_dir: Path passed to ``extractall``.
        safety_boundary: Absolute directory the extracted tree must
            remain under. For self-prefixed bundles this is the parent
            of the bundle; for bare-rooted bundles this equals
            ``extract_dir``.
    """
    boundary_abs = os.path.realpath(safety_boundary)
    safe_members = []
    for member in zf.infolist():
        target = os.path.realpath(os.path.join(extract_dir, member.filename))
        # The boundary check uses ``commonpath`` so we don't get tricked
        # by prefixes like ``/var/data2/`` matching ``/var/data`` via
        # naive ``startswith``.
        try:
            common = os.path.commonpath([boundary_abs, target])
        except ValueError:  # pragma: no cover -- Windows-only (different drives)
            common = ""
        if common != boundary_abs:
            LOGGER.warning(
                f"Zip Slip blocked: refused to extract {member.filename!r} "
                f"-> {target!r} (outside safety boundary {boundary_abs!r})",
            )
            continue
        safe_members.append(member)
    # Pass the filtered member list to extractall so vetoed entries are
    # never touched.
    zf.extractall(path=extract_dir, members=safe_members)


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
        layout = _zip_entries_self_prefixed(zf, bundle_basename)
        if layout == "self":
            # Entries are ``<bundle>/...``; extract into parent_dir and
            # the bundle dir takes shape at ``<parent_dir>/<bundle>/``.
            extract_dir = parent_dir
            safety_boundary = parent_dir
        elif layout == "traversal":
            # Entries are ``../<bundle>/...``. Extracting into parent_dir
            # makes the ``..`` resolve to grandparent_dir, so files land
            # at ``<grandparent_dir>/<bundle>/...``. The safety boundary
            # must include grandparent_dir for the legitimate traversal
            # to be allowed -- otherwise the zip-slip guard rejects every
            # entry. Real bundles in the wild (gzip-wrapped GarageBand
            # exports etc.) use this layout.
            extract_dir = parent_dir
            safety_boundary = os.path.dirname(parent_dir) or parent_dir
        else:
            # Bare-rooted: entries are ``Data/Document.iwa`` etc.
            # Extract into a bundle-named subdir so siblings don't
            # collide on shared internal names.
            extract_dir = local_file
            os.makedirs(extract_dir, exist_ok=True)
            safety_boundary = extract_dir
        LOGGER.info(f"Unpacking {archive_file} to {extract_dir}")
        _safe_extractall(zf, extract_dir, safety_boundary)

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
