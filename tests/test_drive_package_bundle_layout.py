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
                local_file=local_file,
                flatten=True,
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
                local_file=local_file,
                flatten=True,
            )
            self.assertEqual(result, local_file)
            self.assertTrue(os.path.isfile(local_file))


class TestZipEntriesSelfPrefixedEdgeCases(unittest.TestCase):
    """Edge cases for ``_zip_entries_self_prefixed``."""

    def test_returns_none_for_empty_zip(self):
        """A zip whose only entry is the bare bundle folder itself (no
        contents) returns ``None`` — there's nothing to prefix-check,
        and downstream logic should fall through to the bundle-subdir
        layout rather than extracting nothing into the parent."""
        bundle = "Empty.numbers"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "empty.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr(bundle + "/", "")
            with zipfile.ZipFile(zip_path) as zf:
                assert (
                    drive_package_processing._zip_entries_self_prefixed(  # noqa: SLF001
                        zf,
                        bundle,
                    )
                    is None
                )

    def test_returns_self_for_self_prefixed(self):
        """Plain ``<bundle>/...`` entries classify as ``self``."""
        bundle = "Project.band"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "p.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr(f"{bundle}/projectData", b"x")
                zf.writestr(f"{bundle}/Resources/Info.plist", b"<plist/>")
            with zipfile.ZipFile(zip_path) as zf:
                assert (
                    drive_package_processing._zip_entries_self_prefixed(  # noqa: SLF001
                        zf,
                        bundle,
                    )
                    == "self"
                )

    def test_returns_traversal_for_dotdot_prefixed(self):
        """``../<bundle>/...`` entries classify as ``traversal`` — the
        layout used by gzip-wrapped bundles in the wild. The safety
        boundary chooser uses this to widen the boundary to the
        grandparent dir so the legitimate traversal is allowed."""
        bundle = "ms.band"
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "m.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr(f"../{bundle}/projectData", b"x")
                zf.writestr(f"../{bundle}/Resources/Info.plist", b"<plist/>")
            with zipfile.ZipFile(zip_path) as zf:
                assert (
                    drive_package_processing._zip_entries_self_prefixed(  # noqa: SLF001
                        zf,
                        bundle,
                    )
                    == "traversal"
                )


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


class TestZipSlipDefence(unittest.TestCase):
    """``_safe_extractall`` must reject any zip member whose final
    target path escapes the configured safety boundary.

    Defends against Zip Slip (CWE-22) on untrusted CloudKit-served
    package bytes. The exploit shape: a zip entry with an absolute
    path or unbounded ``..`` traversal makes ``extractall`` write
    outside the destination directory."""

    def _make_malicious_zip(
        self,
        tmpdir: str,
        name: str,
        members: dict[str, bytes],
    ) -> str:
        """Build a zip with arbitrary internal paths (including evil ones)."""
        path = os.path.join(tmpdir, name)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for arcname, body in members.items():
                zf.writestr(arcname, body)
        with open(path, "wb") as f:
            f.write(buf.getvalue())
        return path

    def test_absolute_path_entry_is_rejected(self):
        """A zip member with an absolute path (``/etc/poisoned``)
        is refused; benign entries in the same zip still extract."""
        with tempfile.TemporaryDirectory() as base:
            extract_dir = os.path.join(base, "extract")
            os.makedirs(extract_dir)
            zip_path = self._make_malicious_zip(
                base,
                "evil.zip",
                {
                    "/etc/poisoned": b"would overwrite system file",
                    "data/safe.txt": b"this should land",
                },
            )
            with zipfile.ZipFile(zip_path) as zf:
                drive_package_processing._safe_extractall(  # noqa: SLF001
                    zf,
                    extract_dir,
                    extract_dir,
                )  # noqa: SLF001
            # Benign entry made it.
            self.assertTrue(
                os.path.isfile(os.path.join(extract_dir, "data", "safe.txt")),
            )
            # /etc was never touched (and obviously the test process
            # wouldn't have perms anyway -- the assertion is that
            # `_safe_extractall` returned without raising).

    def test_dotdot_traversal_entry_is_rejected(self):
        """``../../../escape.txt`` is refused even with shallow
        ``..`` segments that resolve outside ``extract_dir``."""
        with tempfile.TemporaryDirectory() as base:
            extract_dir = os.path.join(base, "extract")
            os.makedirs(extract_dir)
            zip_path = self._make_malicious_zip(
                base,
                "evil.zip",
                {
                    "../../escape.txt": b"would land in tempdir parent",
                    "inside.txt": b"this should land",
                },
            )
            with zipfile.ZipFile(zip_path) as zf:
                drive_package_processing._safe_extractall(  # noqa: SLF001
                    zf,
                    extract_dir,
                    extract_dir,
                )  # noqa: SLF001
            self.assertTrue(os.path.isfile(os.path.join(extract_dir, "inside.txt")))
            self.assertFalse(os.path.isfile(os.path.join(base, "escape.txt")))
            self.assertFalse(
                os.path.isfile(os.path.join(os.path.dirname(base), "escape.txt")),
            )

    def test_benign_dotdot_does_not_get_blocked_when_boundary_widens(self):
        """When ``safety_boundary`` is widened to the parent of
        ``extract_dir`` (which is what ``_process_zip_package`` does
        for the ``traversal`` layout), a ``../<bundle>/...`` entry is
        NOT blocked. Where the file physically lands depends on
        Python's path-sanitisation policy; we just assert the guard
        didn't refuse the entry."""
        import logging

        with tempfile.TemporaryDirectory() as base:
            extract_dir = os.path.join(base, "Bundle.xcwhatever")
            os.makedirs(extract_dir)
            zip_path = self._make_malicious_zip(
                base,
                "bundle.zip",
                {
                    "../Bundle.xcwhatever/Resources/Info.plist": b"<plist/>",
                },
            )
            with zipfile.ZipFile(zip_path) as zf, self.assertLogs(
                drive_package_processing.LOGGER,
                level=logging.WARNING,
            ) as cm:
                # Push a sentinel WARNING so assertLogs always has at
                # least one record; the assertion below filters to
                # zip-slip-blocked messages.
                drive_package_processing.LOGGER.warning("sentinel")
                drive_package_processing._safe_extractall(  # noqa: SLF001
                    zf,
                    extract_dir,
                    base,
                )
            blocked = [m for m in cm.output if "Zip Slip blocked" in m]
            self.assertEqual(blocked, [])

    def test_real_world_dotdot_bundle_blocked_when_boundary_too_tight(self):
        """Conversely: with ``safety_boundary == extract_dir`` (the
        bare-rooted layout), a ``../<sibling-bundle>/...`` entry
        actually escapes extract_dir and IS blocked. Proves the
        boundary widening in the ``traversal`` layout is what makes
        legit bundles work."""
        import logging

        with tempfile.TemporaryDirectory() as base:
            # extract_dir's basename differs from the bundle name in
            # the entry, so the ``..`` actually escapes upward into
            # ``<base>/ms.band/...`` rather than round-tripping back
            # into extract_dir.
            extract_dir = os.path.join(base, "Sample")
            os.makedirs(extract_dir)
            zip_path = self._make_malicious_zip(
                base,
                "bundle.zip",
                {"../ms.band/Resources/Info.plist": b"<plist/>"},
            )
            with zipfile.ZipFile(zip_path) as zf, self.assertLogs(
                drive_package_processing.LOGGER,
                level=logging.WARNING,
            ) as cm:
                drive_package_processing._safe_extractall(  # noqa: SLF001
                    zf,
                    extract_dir,
                    extract_dir,
                )
            blocked = [m for m in cm.output if "Zip Slip blocked" in m]
            self.assertEqual(len(blocked), 1)


class TestProcessPackageNeverTouchesRegularUserZips(unittest.TestCase):
    """Invariant: ``process_package`` is the unpacker for Apple
    *package* downloads (``/packageDownload?`` URLs only). User-uploaded
    zip files take the regular ``data_token`` download path and never
    reach this function. This test class lives at the unit level to
    lock the invariant in -- the URL gate is a string check in
    ``drive_file_download.py``, but mistakes have happened (CWE-22
    upstream) and the cost of accidentally unpacking a user's .zip is
    high (irrecoverable: the .zip file on iCloud is replaced by a
    directory tree on disk, dedup breaks, restore is manual)."""

    def test_url_gate_is_the_only_caller(self):
        """Audit: ``process_package`` has exactly one external caller
        in the codebase, and that call site has the URL gate."""
        import re
        from pathlib import Path as _Path

        callers = []
        for src_file in _Path("src").rglob("*.py"):
            if src_file.name == "drive_package_processing.py":
                continue  # ignore the recursive self-call inside the module
            text = src_file.read_text()
            if "process_package(" in text:
                callers.append(src_file)

        self.assertEqual(
            len(callers),
            1,
            f"process_package should have exactly 1 external caller "
            f"(the URL-gated one in drive_file_download); found {len(callers)}: "
            f"{[str(c) for c in callers]}",
        )
        # And that caller is gated on the packageDownload URL substring.
        caller_text = callers[0].read_text()
        gate_pattern = re.compile(
            r"if[^\n]*packageDownload\?[^\n]*in[^\n]*response\.url[\s\S]*?process_package\(",
        )
        self.assertRegex(
            caller_text,
            gate_pattern,
            "process_package call must be gated on a `/packageDownload?` "
            "URL substring check so user-uploaded .zip files (which come "
            "via data_token URLs without that segment) are never passed "
            "to the unpacker.",
        )
