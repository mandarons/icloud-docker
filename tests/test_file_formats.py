"""photos.file_format — single filename template applied to all versions."""

import base64
import datetime
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from src import config_parser, photo_path_utils


def _photo(
    filename="IMG_1234.HEIC",
    pid="ABC/123",
    created: datetime.datetime | None = datetime.datetime(2021, 3, 7),
):
    photo = MagicMock()
    photo.filename = filename
    photo.id = pid
    photo.created = created
    photo.versions = {"original": {"type": "public.heic"}}
    return photo


class TestRenderFilenameTemplate(unittest.TestCase):
    """render_filename_template token substitution + variant handling."""

    def tearDown(self):
        photo_path_utils.set_file_format(None)  # reset separator/template globals

    def test_primary_version_has_empty_variant(self):
        tmpl = "${photo.year}.${photo.month}.${photo.day} ${photo.filename}${photo.variant_suffix}.${photo.ext}"
        self.assertEqual(
            photo_path_utils.render_filename_template(tmpl, _photo(), "original"),
            "2021.03.07 IMG_1234.HEIC",
        )

    def test_full_is_also_primary(self):
        out = photo_path_utils.render_filename_template(
            "${photo.filename}${photo.variant_suffix}",
            _photo(),
            "full",
        )
        self.assertEqual(out, "IMG_1234")

    def test_variant_version_is_suffixed(self):
        out = photo_path_utils.render_filename_template(
            "${photo.filename}${photo.variant_suffix}.${photo.ext}",
            _photo(),
            "medium",
        )
        self.assertEqual(out, "IMG_1234_medium.HEIC")

    def test_bare_variant_token(self):
        out = photo_path_utils.render_filename_template(
            "${photo.filename}--${photo.variant}",
            _photo(),
            "thumb",
        )
        self.assertEqual(out, "IMG_1234--thumb")

    def test_configurable_separator(self):
        photo_path_utils.set_file_format("x", variant_separator="-")
        out = photo_path_utils.render_filename_template(
            "${photo.filename}${photo.variant_suffix}",
            _photo(),
            "medium",
        )
        self.assertEqual(out, "IMG_1234-medium")

    def test_id_and_file_size_tokens(self):
        out = photo_path_utils.render_filename_template(
            "${photo.id}__${photo.file_size}",
            _photo(),
            "original",
        )
        self.assertEqual(
            out,
            f"{base64.urlsafe_b64encode(b'ABC/123').decode()}__original",
        )

    def test_unknown_token_left_literal(self):
        out = photo_path_utils.render_filename_template(
            "${photo.bogus}-${photo.filename}",
            _photo(),
            "original",
        )
        self.assertEqual(out, "${photo.bogus}-IMG_1234")

    def test_missing_created_renders_blank(self):
        out = photo_path_utils.render_filename_template(
            "${photo.year}-${photo.filename}",
            _photo(created=None),
            "original",
        )
        self.assertEqual(out, "-IMG_1234")


class TestSetFileFormat(unittest.TestCase):
    def tearDown(self):
        photo_path_utils.set_file_format(None)

    def test_set_and_get(self):
        photo_path_utils.set_file_format("tmpl")
        self.assertEqual(photo_path_utils.get_file_format(), "tmpl")

    def test_empty_clears(self):
        photo_path_utils.set_file_format("tmpl")
        photo_path_utils.set_file_format(None)
        self.assertIsNone(photo_path_utils.get_file_format())

    def test_none_separator_defaults_to_underscore(self):
        photo_path_utils.set_file_format(
            "${photo.filename}${photo.variant_suffix}",
            variant_separator=None,
        )
        out = photo_path_utils.render_filename_template(
            "${photo.filename}${photo.variant_suffix}",
            _photo(),
            "medium",
        )
        self.assertEqual(out, "IMG_1234_medium")


class TestGenerateWithFileFormat(unittest.TestCase):
    def tearDown(self):
        photo_path_utils.set_file_format(None)

    def test_file_format_applies(self):
        photo_path_utils.set_file_format(
            "${photo.filename}${photo.variant_suffix}.${photo.ext}",
        )
        self.assertEqual(
            photo_path_utils.generate_photo_filename_with_metadata(
                _photo(),
                "original",
            ),
            "IMG_1234.HEIC",
        )

    def test_forced_metadata_bypasses_file_format(self):
        photo_path_utils.set_file_format("${photo.filename}.${photo.ext}")
        out = photo_path_utils.generate_photo_filename_with_metadata(
            _photo(),
            "original",
            "metadata",
        )
        self.assertIn("__original__", out)

    def test_empty_render_falls_back(self):
        # A template that renders empty for this version must not yield an empty
        # name; it falls back to filename_format (metadata default here).
        photo_path_utils.set_file_format("${photo.variant}")
        out = photo_path_utils.generate_photo_filename_with_metadata(_photo(), "original")
        self.assertIn("__original__", out)


class TestConfigGetters(unittest.TestCase):
    def test_file_format_absent(self):
        self.assertIsNone(config_parser.get_photos_file_format({"photos": {}}))

    def test_file_format_blank_or_nonstring(self):
        self.assertIsNone(
            config_parser.get_photos_file_format({"photos": {"file_format": "   "}}),
        )
        self.assertIsNone(
            config_parser.get_photos_file_format({"photos": {"file_format": 123}}),
        )

    def test_file_format_valid(self):
        self.assertEqual(
            config_parser.get_photos_file_format(
                {"photos": {"file_format": "${photo.filename}"}},
            ),
            "${photo.filename}",
        )

    def test_variant_separator_default_and_custom(self):
        self.assertEqual(
            config_parser.get_photos_variant_separator({"photos": {}}),
            "_",
        )
        self.assertEqual(
            config_parser.get_photos_variant_separator(
                {"photos": {"variant_separator": "-"}},
            ),
            "-",
        )


class TestFileFormatCollisionFallback(unittest.TestCase):
    """A templated name that collides falls back to the unique metadata name."""

    def setUp(self):
        photo_path_utils.set_file_format("${photo.filename}.${photo.ext}")
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        photo_path_utils.set_file_format(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_collision_routes_to_metadata(self):
        from src.photo_download_manager import collect_download_task

        occupied = os.path.join(self.tmp, "IMG_EEEE.HEIC")
        with open(occupied, "wb") as f:
            f.write(b"x" * 9999)
        photo = _photo(filename="IMG_EEEE.HEIC", pid="different-id")
        photo.versions = {"original": {"type": "public.heic", "size": 12345}}

        task = collect_download_task(
            photo,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        self.assertIsNotNone(task)
        self.assertIn("__original__", task.photo_path)
        self.assertEqual(os.path.getsize(occupied), 9999)


if __name__ == "__main__":
    unittest.main()
