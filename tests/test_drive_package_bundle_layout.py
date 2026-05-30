"""Tests for ZIP-package extraction layout + the flatten_packages knob.

Covers the second half of PR 11's package-handling rework:

1. **Self-prefixed zip** (e.g. ``Project.band``'s entries are rooted at
   ``Project.band/...``) extracts into the parent directory — preserves
   the historical mandarons behaviour for genuine directory bundles.

2. **Bare-rooted zip** (e.g. an iWork ``.numbers`` whose entries are
   rooted at ``Data/...`` and ``Metadata/...``) extracts into a
   per-package subdirectory so sibling iWork files in the same parent
   folder don't clobber each other on shared internal names. This is
   the fix for the ``FileExistsError`` Eric saw on a real install.

3. **flatten_packages=True** skips unpacking entirely and keeps the
   package on disk as the downloaded single binary file. Opt-in via
   ``drive.flatten_packages: true`` in config.yaml — backup-style
   deployments prefer single-file storage.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import io
import os
import tempfile
import unittest
import zipfile

import tests  # noqa: F401  — env setup
from src import config_parser, drive_package_processing


def _make_zip(tmpdir: str, name: str, entries: dict[str, bytes]) -> str:
    """Write a zip file at ``tmpdir/name`` containing the given entries.

    ``entries`` is a mapping of zip-internal path → file body bytes.
    Returns the absolute path of the created file.
    """
    path = os.path.join(tmpdir, name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for arcname, body in entries.items():
            zf.writestr(arcname, body)
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


class TestSelfPrefixedZipExtractsIntoParent(unittest.TestCase):
    """A zip whose entries are all rooted at ``<bundle_basename>/`` —
    GarageBand .band, some Logic projects, etc — should extract into
    the parent directory so the resulting on-disk tree IS the bundle."""

    def test_band_style_zip_keeps_bundle_directory_in_parent(self):
        with tempfile.TemporaryDirectory() as base:
            local_file = os.path.join(base, "Project.band")
            _make_zip(
                base,
                "Project.band",  # written directly at local_file
                {
                    "Project.band/projectData": b"x" * 100,
                    "Project.band/Resources/Info.plist": b"<plist/>",
                },
            )
            result = drive_package_processing.process_package(local_file=local_file)
            # process_package returns the bundle path; on disk we expect
            # a directory at that path with the contents.
            self.assertEqual(result, local_file)
            self.assertTrue(os.path.isdir(local_file))
            self.assertTrue(os.path.isfile(os.path.join(local_file, "projectData")))
            self.assertTrue(
                os.path.isfile(os.path.join(local_file, "Resources", "Info.plist")),
            )


class TestBareRootedZipExtractsIntoBundleSubdir(unittest.TestCase):
    """A zip whose entries have bare internal paths — iWork .numbers /
    .pages / .key — should extract INTO the bundle (creating a directory
    of the same name) so sibling bundles in the same parent don't
    collide on shared internal names like ``Data/Document.iwa``."""

    def test_iwork_style_zip_extracts_into_bundle_subdir(self):
        with tempfile.TemporaryDirectory() as base:
            local_file = os.path.join(base, "Untitled.numbers")
            _make_zip(
                base,
                "Untitled.numbers",
                {
                    "Data/Document.iwa": b"document-bytes",
                    "Metadata/buildVersion.plist": b"<plist/>",
                },
            )
            result = drive_package_processing.process_package(local_file=local_file)
            self.assertEqual(result, local_file)
            self.assertTrue(os.path.isdir(local_file))
            self.assertTrue(
                os.path.isfile(os.path.join(local_file, "Data", "Document.iwa")),
            )
            self.assertTrue(
                os.path.isfile(
                    os.path.join(local_file, "Metadata", "buildVersion.plist"),
                ),
            )
            # The bare names did NOT escape into the parent dir.
            self.assertFalse(os.path.exists(os.path.join(base, "Data")))
            self.assertFalse(os.path.exists(os.path.join(base, "Metadata")))

    def test_two_sibling_iwork_zips_dont_collide(self):
        """The headline bug Eric saw on a 0.7.3 install:
        ``Failed to download Untitled 6.numbers: [Errno 17] File exists:
        Untitled.numbers``. Before the fix, the second extract clobbered
        ``Data/`` from the first. After: both bundles land cleanly."""
        with tempfile.TemporaryDirectory() as base:
            first = os.path.join(base, "Untitled.numbers")
            second = os.path.join(base, "Untitled 6.numbers")

            # Both zips share generic internal names — iWork format
            # is the same across all .numbers documents.
            shared_entries = {
                "Data/Document.iwa": b"doc-bytes",
                "Metadata/buildVersion.plist": b"<plist/>",
            }
            _make_zip(base, "Untitled.numbers", shared_entries)
            r1 = drive_package_processing.process_package(local_file=first)
            self.assertEqual(r1, first)

            _make_zip(base, "Untitled 6.numbers", shared_entries)
            r2 = drive_package_processing.process_package(local_file=second)
            self.assertEqual(r2, second)

            # Both bundles exist as independent directories with the same
            # internal structure; neither clobbered the other.
            self.assertTrue(os.path.isfile(os.path.join(first, "Data", "Document.iwa")))
            self.assertTrue(
                os.path.isfile(os.path.join(second, "Data", "Document.iwa")),
            )


class TestFlattenPackagesSkipsUnpack(unittest.TestCase):
    """``drive.flatten_packages: true`` — package downloads stay on
    disk as the downloaded single binary file. Use case: NAS backup,
    cold storage, or any place bundle-directory semantics aren't
    needed and single-file storage simplifies dedup + restore."""

    def test_flatten_true_preserves_zip_as_single_file(self):
        with tempfile.TemporaryDirectory() as base:
            local_file = os.path.join(base, "Untitled.numbers")
            _make_zip(
                base,
                "Untitled.numbers",
                {"Data/Document.iwa": b"doc-bytes"},
            )
            # Snapshot the original bytes so we can compare after.
            original_size = os.path.getsize(local_file)

            result = drive_package_processing.process_package(
                local_file=local_file, flatten=True,
            )
            self.assertEqual(result, local_file)
            self.assertTrue(os.path.isfile(local_file))
            # Bytes are unchanged — no rename, no unpack.
            self.assertEqual(os.path.getsize(local_file), original_size)
            # And nothing got extracted into the parent.
            self.assertFalse(os.path.exists(os.path.join(base, "Data")))

    def test_flatten_true_works_for_octet_stream_too(self):
        """An octet-stream "package" (Apple iWork or JMG that libmagic
        couldn't identify) is already treated as single-file in the
        unflatten path. With flatten=True we shouldn't even bother
        with the mime detect."""
        with tempfile.TemporaryDirectory() as base:
            local_file = os.path.join(base, "Hi I'm Norah.jmb")
            with open(local_file, "wb") as f:
                f.write(b"opaque-bundle-bytes-no-magic")

            result = drive_package_processing.process_package(
                local_file=local_file, flatten=True,
            )
            self.assertEqual(result, local_file)
            self.assertTrue(os.path.isfile(local_file))


class TestFlattenPackagesConfigGetter(unittest.TestCase):
    """``config_parser.get_drive_flatten_packages`` returns the
    operator's choice. Default is False so existing installs are
    unaffected; opt-in via the YAML key."""

    def test_default_when_unset(self):
        self.assertFalse(config_parser.get_drive_flatten_packages({}))

    def test_default_when_drive_block_absent(self):
        self.assertFalse(config_parser.get_drive_flatten_packages({"photos": {}}))

    def test_true_when_set(self):
        cfg = {"drive": {"flatten_packages": True}}
        self.assertTrue(config_parser.get_drive_flatten_packages(cfg))

    def test_false_when_set_explicit(self):
        cfg = {"drive": {"flatten_packages": False}}
        self.assertFalse(config_parser.get_drive_flatten_packages(cfg))

    def test_none_config_is_safe(self):
        self.assertFalse(config_parser.get_drive_flatten_packages(None))


if __name__ == "__main__":
    unittest.main()
