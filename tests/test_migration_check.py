"""Tests for ``src.migration_check.check_library`` — the per-photo
file-existence check driven by ``--dry-run --check-files``."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import tempfile
import unittest
from unittest.mock import MagicMock

import tests  # noqa: F401  — env setup
from src import migration_check


def _fake_photo(filename: str, size: int, year: int = 2024, month: int = 1):
    """Build a MagicMock that quacks like an icloudpy PhotoAsset."""
    from datetime import datetime

    photo = MagicMock()
    photo.filename = filename
    photo.created = datetime(year, month, 15)
    photo.versions = {"original": {"size": size, "type": "public.heic"}}
    photo.id = filename.encode().hex()  # stable, unique-ish id for testing
    return photo


def _fake_library(photos: list):
    """Wrap a list of photo mocks in an object shaped like a PhotoLibrary."""
    library = MagicMock()
    library.albums = {"All Photos": photos}
    return library


# Whether the upstream supports the "simple" filename_format toggle.
# Used as a hint inside setUp — if PR 5 isn't merged, we monkey-patch
# the metadata-format filename generator to return the photo's bare
# `.filename` instead, so the test fixtures (`IMG_N.HEIC`) still match
# the path that check_library computes. Lifts cleanly once
# feat/photos-filename-format-simple is merged upstream.
_SIMPLE_FORMAT_AVAILABLE = hasattr(
    __import__("src.photo_path_utils", fromlist=["x"]),
    "set_default_filename_format",
)


class TestCheckLibrary(unittest.TestCase):
    """Behaviour of the per-library walk."""

    def setUp(self):
        if _SIMPLE_FORMAT_AVAILABLE:
            # PR 5 merged: use the real simple-format toggle.
            migration_check.set_default_filename_format("simple")
            self._addCleanup_no_patch = True
        else:
            # PR 5 NOT merged: monkey-patch the filename generator at the
            # migration_check level to return the photo's bare filename.
            # Reproduces what "simple" mode would do without depending on
            # the PR 5 code path.
            from unittest.mock import patch

            self._patcher = patch.object(
                migration_check,
                "generate_photo_filename_with_metadata",
                side_effect=lambda photo, _size: photo.filename,
            )
            self._patcher.start()
            self.addCleanup(self._patcher.stop)

    def test_empty_library(self):
        with tempfile.TemporaryDirectory() as base:
            result = migration_check.check_library(
                library=_fake_library([]),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 0)

    def test_all_photos_present_and_correct_size(self):
        with tempfile.TemporaryDirectory() as base:
            # Create three photos on disk at the expected paths with the
            # expected sizes; check_library should report all would_skip.
            photos = []
            for i, size in enumerate([1000, 2000, 3000]):
                name = f"IMG_{i}.HEIC"
                path = os.path.join(base, name)
                with open(path, "wb") as f:
                    f.write(b"x" * size)
                photos.append(_fake_photo(name, size))

            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},  # empty mapping → fall through to base
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 3)
            self.assertEqual(result["stats"]["size_mismatch"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 3)

    def test_all_photos_missing(self):
        with tempfile.TemporaryDirectory() as base:
            photos = [_fake_photo(f"IMG_{i}.HEIC", 1000 + i) for i in range(3)]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["not_found"], 3)
            self.assertEqual(result["stats"]["would_skip"], 0)

    def test_size_mismatch_counts_separately_from_not_found(self):
        with tempfile.TemporaryDirectory() as base:
            # One file present at correct size, one at wrong size, one missing.
            with open(os.path.join(base, "IMG_a.HEIC"), "wb") as f:
                f.write(b"x" * 1000)  # matches
            with open(os.path.join(base, "IMG_b.HEIC"), "wb") as f:
                f.write(b"x" * 500)  # wrong size — expected 2000

            photos = [
                _fake_photo("IMG_a.HEIC", 1000),
                _fake_photo("IMG_b.HEIC", 2000),
                _fake_photo("IMG_c.HEIC", 3000),  # no file on disk
            ]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 1)
            self.assertEqual(result["stats"]["not_found"], 1)
            # samples capture the per-status examples
            self.assertEqual(len(result["samples"]["would_skip"]), 1)
            self.assertEqual(len(result["samples"]["size_mismatch"]), 1)
            # size_mismatch sample carries (path, expected, actual)
            path, expected, actual = result["samples"]["size_mismatch"][0]
            self.assertEqual(expected, 2000)
            self.assertEqual(actual, 500)

    def test_sample_caps_walk_at_N(self):
        """``sample=N`` walks N stride-sampled photos and stops."""
        with tempfile.TemporaryDirectory() as base:
            photos = [_fake_photo(f"IMG_{i}.HEIC", 1000) for i in range(200)]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=10,
            )
            self.assertEqual(result["checked"], 10)


def _fake_drive_file(name: str, size: int):
    """Build a MagicMock that quacks like an icloudpy Drive file node."""
    node = MagicMock()
    node.name = name
    node.type = "file"
    node.size = size
    return node


def _fake_drive_folder(name: str, children: dict):
    """Build a MagicMock that quacks like an icloudpy Drive folder node.

    ``children`` is a dict mapping child-name → child-mock (file or folder).
    """
    node = MagicMock()
    node.name = name
    node.type = "folder"
    node.dir.return_value = list(children.keys())
    node.__getitem__.side_effect = lambda key: children[key]
    return node


class TestCheckDrive(unittest.TestCase):
    """Behaviour of the iCloud Drive walker."""

    def test_empty_drive(self):
        with tempfile.TemporaryDirectory() as base:
            drive = _fake_drive_folder("root", {})
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["checked"], 0)
            self.assertEqual(result["stats"]["would_skip"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)

    def test_all_files_present_at_root(self):
        with tempfile.TemporaryDirectory() as base:
            # Three files on disk with known sizes
            for name, size in [("a.txt", 100), ("b.txt", 200), ("c.txt", 300)]:
                with open(os.path.join(base, name), "wb") as f:
                    f.write(b"x" * size)
            drive = _fake_drive_folder(
                "root",
                {
                    "a.txt": _fake_drive_file("a.txt", 100),
                    "b.txt": _fake_drive_file("b.txt", 200),
                    "c.txt": _fake_drive_file("c.txt", 300),
                },
            )
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 3)
            self.assertEqual(result["stats"]["size_mismatch"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 3)

    def test_missing_and_size_mismatch_at_root(self):
        with tempfile.TemporaryDirectory() as base:
            # a.txt matches; b.txt wrong size; c.txt missing.
            with open(os.path.join(base, "a.txt"), "wb") as f:
                f.write(b"x" * 100)
            with open(os.path.join(base, "b.txt"), "wb") as f:
                f.write(b"x" * 50)  # expected 200
            drive = _fake_drive_folder(
                "root",
                {
                    "a.txt": _fake_drive_file("a.txt", 100),
                    "b.txt": _fake_drive_file("b.txt", 200),
                    "c.txt": _fake_drive_file("c.txt", 300),
                },
            )
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 1)
            self.assertEqual(result["stats"]["not_found"], 1)
            self.assertEqual(len(result["samples"]["size_mismatch"]), 1)
            _, expected, actual = result["samples"]["size_mismatch"][0]
            self.assertEqual(expected, 200)
            self.assertEqual(actual, 50)

    def test_recurses_into_subfolders(self):
        with tempfile.TemporaryDirectory() as base:
            # On-disk: base/sub/leaf.txt @ 42 bytes
            os.makedirs(os.path.join(base, "sub"))
            with open(os.path.join(base, "sub", "leaf.txt"), "wb") as f:
                f.write(b"x" * 42)
            sub_folder = _fake_drive_folder(
                "sub",
                {"leaf.txt": _fake_drive_file("leaf.txt", 42)},
            )
            drive = _fake_drive_folder("root", {"sub": sub_folder})
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["checked"], 1)

    def test_unpacked_package_directory_counts_as_skip_when_size_matches(self):
        """Mandarons-unpacked packages live as directories on disk; sum
        of contained-file sizes must match the package item size."""
        with tempfile.TemporaryDirectory() as base:
            # Package directory with two inner files summing to 150
            pkg_path = os.path.join(base, "Project.band")
            os.makedirs(pkg_path)
            with open(os.path.join(pkg_path, "metadata.plist"), "wb") as f:
                f.write(b"x" * 50)
            with open(os.path.join(pkg_path, "projectdata"), "wb") as f:
                f.write(b"x" * 100)
            drive = _fake_drive_folder(
                "root",
                {"Project.band": _fake_drive_file("Project.band", 150)},
            )
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 0)

    def test_sample_caps_drive_walk_at_N(self):
        with tempfile.TemporaryDirectory() as base:
            children = {
                f"f{i}.txt": _fake_drive_file(f"f{i}.txt", 100) for i in range(20)
            }
            drive = _fake_drive_folder("root", children)
            result = migration_check.check_drive(
                drive=drive,
                drive_destination=base,
                sample=5,
            )
            self.assertEqual(result["checked"], 5)


class TestCheckOnePhotoEdges(unittest.TestCase):
    """Branches of ``_check_one_photo`` not covered by happy-path tests."""

    def setUp(self):
        # Same monkey-patch as TestCheckLibrary so the metadata-format
        # generator returns the photo's bare filename.
        if not _SIMPLE_FORMAT_AVAILABLE:
            from unittest.mock import patch

            self._patcher = patch.object(
                migration_check,
                "generate_photo_filename_with_metadata",
                side_effect=lambda photo, _size: photo.filename,
            )
            self._patcher.start()
            self.addCleanup(self._patcher.stop)

    def test_missing_original_version_returns_error(self):
        """A photo with no `original` version key (incomplete CloudKit
        record) returns the `error` status without crashing."""
        with tempfile.TemporaryDirectory() as base:
            photo = _fake_photo("IMG_0.HEIC", 1000)
            photo.versions = {"medium": {"size": 500}}  # no "original"
            result = migration_check.check_library(
                library=_fake_library([photo]),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["error"], 1)

    def test_path_computation_exception_returns_error(self):
        """If the filename generator itself raises (malformed photo,
        unicode oddity, …) the per-photo result is `error`, not a
        crash that kills the whole walk."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            photo = _fake_photo("IMG_0.HEIC", 1000)
            with patch.object(
                migration_check,
                "generate_photo_filename_with_metadata",
                side_effect=RuntimeError("filename boom"),
            ):
                result = migration_check.check_library(
                    library=_fake_library([photo]),
                    library_name="PrimarySync",
                    photos_base=base,
                    mapping={},
                    folder_format=None,
                    sample=0,
                )
            self.assertEqual(result["stats"]["error"], 1)

    def test_getsize_oserror_returns_error(self):
        """``os.path.getsize`` can raise OSError on perms / FS errors
        even when ``isfile`` returned True. That edge is reported as
        `error`, not size_mismatch."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            name = "IMG_0.HEIC"
            with open(os.path.join(base, name), "wb") as f:
                f.write(b"x" * 1000)
            photo = _fake_photo(name, 1000)
            with patch("os.path.getsize", side_effect=OSError("perms")):
                result = migration_check.check_library(
                    library=_fake_library([photo]),
                    library_name="PrimarySync",
                    photos_base=base,
                    mapping={},
                    folder_format=None,
                    sample=0,
                )
            self.assertEqual(result["stats"]["error"], 1)

    def test_iteration_exception_stops_early_without_crash(self):
        """A walk that explodes mid-iteration (transient iCloud error)
        is logged and returns partial counts — not a hard fail."""

        class BoomLibrary:
            def __init__(self):
                self.albums = {"All Photos": self}

            def __iter__(self):
                yield _fake_photo("IMG_0.HEIC", 1000)
                msg = "iter boom"
                raise RuntimeError(msg)

        with tempfile.TemporaryDirectory() as base:
            result = migration_check.check_library(
                library=BoomLibrary(),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            # Got one error (the one photo we saw before boom), then
            # the iterator died — checked=1, not None.
            self.assertEqual(result["checked"], 1)


class TestCheckOneDriveFileEdges(unittest.TestCase):
    """Branches of ``_check_one_drive_file`` not covered by happy-path
    tests in TestCheckDrive (size guard, getsize OSError, directory
    sum OSError, missing-on-disk → not_found)."""

    def test_missing_item_size_attr_is_error(self):
        with tempfile.TemporaryDirectory() as base:
            item = MagicMock()
            item.name = "weird.txt"
            item.size = "not a number"  # int() raises
            status, _path, _expected, _actual = migration_check._check_one_drive_file(  # noqa: SLF001
                item,
                os.path.join(base, "weird.txt"),
            )
            self.assertEqual(status, "error")

    def test_disk_getsize_oserror_returns_error(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            path = os.path.join(base, "file.txt")
            with open(path, "wb") as f:
                f.write(b"x" * 100)
            item = _fake_drive_file("file.txt", 100)
            with patch("os.path.getsize", side_effect=OSError("perms")):
                status, *_ = migration_check._check_one_drive_file(item, path)  # noqa: SLF001
            self.assertEqual(status, "error")

    def test_directory_sum_oserror_returns_error(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            pkg = os.path.join(base, "pkg.band")
            os.makedirs(pkg)
            item = _fake_drive_file("pkg.band", 100)
            with patch(
                "pathlib.Path.glob",
                side_effect=OSError("perms"),
            ):
                status, *_ = migration_check._check_one_drive_file(item, pkg)  # noqa: SLF001
            self.assertEqual(status, "error")


class TestWalkDriveRecursiveEdges(unittest.TestCase):
    """Branches of ``_walk_drive_recursive`` not exercised by the
    flat-folder happy-path tests in TestCheckDrive."""

    def test_dir_call_exception_returns_silently(self):
        """If folder.dir() raises (transient iCloud error) the walker
        logs and returns — doesn't crash the whole sync."""
        folder = MagicMock()
        folder.dir.side_effect = RuntimeError("dir boom")
        state = {
            "checked": 0,
            "stats": {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0},
            "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
        }
        migration_check._walk_drive_recursive(  # noqa: SLF001
            folder=folder,
            destination_path="/x",
            sample=0,
            state=state,
        )
        self.assertEqual(state["checked"], 0)

    def test_item_getitem_failure_counted_as_error(self):
        """``folder[name]`` can raise (item disappeared / permission
        change between dir() and getitem). Each failure adds an error
        stat — the walk continues."""
        folder = MagicMock()
        folder.dir.return_value = ["a", "b"]
        folder.__getitem__.side_effect = RuntimeError("item boom")
        state = {
            "checked": 0,
            "stats": {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0},
            "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
        }
        migration_check._walk_drive_recursive(  # noqa: SLF001
            folder=folder,
            destination_path="/x",
            sample=0,
            state=state,
        )
        self.assertEqual(state["stats"]["error"], 2)

    def test_recurses_into_subfolders_and_files(self):
        """Folder → sub-folder → file chain works. Covers the recursive
        branch + the file branch."""
        with tempfile.TemporaryDirectory() as base:
            inner_dir = os.path.join(base, "inner")
            os.makedirs(inner_dir)
            with open(os.path.join(inner_dir, "f.txt"), "wb") as f:
                f.write(b"x" * 50)
            inner_folder = _fake_drive_folder(
                "inner",
                {"f.txt": _fake_drive_file("f.txt", 50)},
            )
            inner_folder.name = "inner"
            root = _fake_drive_folder("root", {"inner": inner_folder})
            result = migration_check.check_drive(
                drive=root,
                drive_destination=base,
                sample=0,
            )
            self.assertEqual(result["checked"], 1)
            self.assertEqual(result["stats"]["would_skip"], 1)


class TestWalkDriveRecursiveExtraEdges(unittest.TestCase):
    """More edge branches inside ``_walk_drive_recursive``."""

    def test_returns_early_when_sample_already_met(self):
        """If the caller passes state with checked >= sample, the walker
        returns immediately without calling .dir() at all."""
        folder = MagicMock()
        state = {
            "checked": 10,
            "stats": {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0},
            "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
        }
        migration_check._walk_drive_recursive(  # noqa: SLF001
            folder=folder,
            destination_path="/x",
            sample=5,
            state=state,
        )
        folder.dir.assert_not_called()

    def test_folder_unquote_exception_falls_back_to_raw_name(self):
        """If urllib unquote raises on a folder name (highly unusual),
        the walker uses the raw name and continues recursing."""
        from unittest.mock import patch

        inner = _fake_drive_folder("inner", {})
        inner.name = "name-that-breaks-unquote"
        root = _fake_drive_folder("root", {"inner": inner})
        state = {
            "checked": 0,
            "stats": {"would_skip": 0, "size_mismatch": 0, "not_found": 0, "error": 0},
            "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
        }
        with patch.object(
            migration_check,
            "unquote",
            side_effect=RuntimeError("unquote boom"),
        ):
            migration_check._walk_drive_recursive(  # noqa: SLF001
                folder=root,
                destination_path="/x",
                sample=0,
                state=state,
            )
        # No crash; the inner folder was visited (empty so nothing checked).
        self.assertEqual(state["checked"], 0)

    def test_file_unquote_exception_falls_back_to_raw_name(self):
        """Same fallback for file items."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            # File on disk at a path that matches the raw name fallback.
            name = "file.txt"
            with open(os.path.join(base, name), "wb") as f:
                f.write(b"x" * 50)
            root = _fake_drive_folder("root", {name: _fake_drive_file(name, 50)})
            state = {
                "checked": 0,
                "stats": {
                    "would_skip": 0,
                    "size_mismatch": 0,
                    "not_found": 0,
                    "error": 0,
                },
                "samples": {"would_skip": [], "size_mismatch": [], "not_found": []},
            }
            with patch.object(
                migration_check,
                "unquote",
                side_effect=RuntimeError("unquote boom"),
            ):
                migration_check._walk_drive_recursive(  # noqa: SLF001
                    folder=root,
                    destination_path=base,
                    sample=0,
                    state=state,
                )
            self.assertEqual(state["checked"], 1)
            self.assertEqual(state["stats"]["would_skip"], 1)


class TestCheckDriveExceptionPath(unittest.TestCase):
    """``check_drive``'s try/except — if _walk_drive_recursive raises,
    the wrapper logs a warning and returns the partial state instead
    of letting the exception bubble out."""

    def test_walk_exception_logged_and_partial_returned(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as base:
            drive = _fake_drive_folder("root", {})
            with patch.object(
                migration_check,
                "_walk_drive_recursive",
                side_effect=RuntimeError("walk boom"),
            ):
                result = migration_check.check_drive(
                    drive=drive,
                    drive_destination=base,
                    sample=0,
                )
            self.assertIn("stats", result)
            self.assertEqual(result["checked"], 0)


class TestCheckMigrationLibraryDestinationsBranch(unittest.TestCase):
    """Cover the `hasattr(config_parser, "get_photos_library_destinations")`
    True branch — fires when PR 3 (feat/photos-library-destinations) IS
    merged. Since this branch doesn't have PR 3, we monkey-patch the
    config_parser to expose the function so the True branch is exercised."""

    def setUp(self):
        from src import read_config

        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        import shutil

        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    def test_uses_real_library_destinations_when_PR3_is_merged(self):
        """When PR 3 is merged, ``get_photos_library_destinations`` exists
        and check_migration uses it directly. Coverage-only test."""
        from unittest.mock import MagicMock as _MM
        from unittest.mock import patch

        api = _MM()
        api.photos.libraries = {"PrimarySync": _fake_library([])}
        fake_getter = _MM(return_value={"PrimarySync": "personal"})
        with patch.object(
            migration_check.config_parser,
            "get_photos_library_destinations",
            fake_getter,
            create=True,
        ):
            migration_check.check_migration(api=api, config=self.config, sample=0)
        fake_getter.assert_called_once_with(config=self.config)


class TestCheckMigrationOrchestrator(unittest.TestCase):
    """``check_migration`` iterates api.photos.libraries and routes to
    ``check_library`` per library. ``check_drive_migration`` resolves
    drive_destination and routes to ``check_drive``."""

    def setUp(self):
        from src import read_config

        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        import shutil

        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    def test_check_migration_iterates_all_libraries(self):
        """Two libraries → result dict has both keys + each value is
        the per-library result shape from check_library."""
        api = MagicMock()
        api.photos.libraries = {
            "PrimarySync": _fake_library([]),
            "SharedLibrary": _fake_library([]),
        }
        results = migration_check.check_migration(
            api=api,
            config=self.config,
            sample=0,
        )
        self.assertEqual(set(results.keys()), {"PrimarySync", "SharedLibrary"})
        for r in results.values():
            self.assertIn("library_dest", r)
            self.assertIn("stats", r)

    def test_check_migration_sets_filename_format_from_config(self):
        """When `photos.filename_format` is set in config, the
        orchestrator pushes it through to set_default_filename_format
        before walking."""
        from unittest.mock import patch

        api = MagicMock()
        api.photos.libraries = {"PrimarySync": _fake_library([])}
        self.config["photos"]["filename_format"] = "simple"
        with patch.object(
            migration_check,
            "set_default_filename_format",
        ) as fake_setter:
            migration_check.check_migration(api=api, config=self.config, sample=0)
        fake_setter.assert_called_once_with("simple")

    def test_check_drive_migration_returns_none_when_no_drive_section(self):
        config = {"photos": {"destination": "/photos"}}
        self.assertIsNone(
            migration_check.check_drive_migration(api=MagicMock(), config=config),
        )

    def test_check_drive_migration_returns_none_when_destination_resolution_fails(self):
        from unittest.mock import patch

        with patch.object(
            migration_check.config_parser,
            "prepare_drive_destination",
            side_effect=RuntimeError("bad path"),
        ):
            self.assertIsNone(
                migration_check.check_drive_migration(
                    api=MagicMock(),
                    config=self.config,
                ),
            )

    def test_check_drive_migration_walks_when_drive_configured(self):
        """Happy path: drive section present, destination resolves, walk
        produces a result dict."""
        api = MagicMock()
        api.drive = _fake_drive_folder("root", {})
        result = migration_check.check_drive_migration(
            api=api,
            config=self.config,
            sample=0,
        )
        self.assertIsNotNone(result)
        self.assertIn("stats", result)


if __name__ == "__main__":
    unittest.main()
