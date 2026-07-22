"""Tests for docker-entrypoint.sh script functionality."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import subprocess
import tempfile
import unittest


class TestDockerEntrypoint(unittest.TestCase):
    """Tests class for docker-entrypoint.sh script."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.entrypoint_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "docker-entrypoint.sh",
        )
        return super().setUp()

    def test_entrypoint_script_exists(self):
        """Test that the docker-entrypoint.sh script exists."""
        self.assertTrue(os.path.exists(self.entrypoint_path))

    def test_entrypoint_script_syntax(self):
        """Test that the docker-entrypoint.sh script has valid shell syntax."""
        result = subprocess.run(
            ["sh", "-n", self.entrypoint_path],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Script syntax error: {result.stderr}")


class TestKeyringMigration(unittest.TestCase):
    """Tests for keyring migration from old to new location."""

    MIGRATION_SNIPPET = """\
OLD_KEYRING="{old}"
NEW_KEYRING="{new}"
if [ -f "$OLD_KEYRING" ] && [ ! -f "$NEW_KEYRING" ]; then
    mkdir -p "$(dirname "$NEW_KEYRING")"
    cp "$OLD_KEYRING" "$NEW_KEYRING"
fi
"""

    def setUp(self):
        """Create temporary directories for test isolation."""
        self.tmpdir = tempfile.mkdtemp()
        self.old_dir = os.path.join(self.tmpdir, "old_keyring")
        self.new_dir = os.path.join(self.tmpdir, "new_keyring")
        self.old_keyring = os.path.join(self.old_dir, "keyring_pass.cfg")
        self.new_keyring = os.path.join(self.new_dir, "keyring_pass.cfg")

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.tmpdir)

    def _run_migration(self):
        """Run the migration snippet with test paths."""
        snippet = self.MIGRATION_SNIPPET.format(old=self.old_keyring, new=self.new_keyring)
        result = subprocess.run(["sh", "-c", snippet], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"Migration snippet failed: {result.stderr}")

    def test_migration_from_old_location(self):
        """Test that keyring is copied when old exists and new doesn't."""
        os.makedirs(self.old_dir)
        with open(self.old_keyring, "w") as f:
            f.write("test_password_data")

        self._run_migration()

        self.assertTrue(os.path.exists(self.new_keyring))
        with open(self.new_keyring) as f:
            self.assertEqual(f.read(), "test_password_data")

    def test_no_migration_when_new_keyring_exists(self):
        """Test that old keyring is NOT copied when new already exists."""
        os.makedirs(self.old_dir)
        os.makedirs(self.new_dir)
        with open(self.old_keyring, "w") as f:
            f.write("old_password_data")
        with open(self.new_keyring, "w") as f:
            f.write("new_password_data")

        self._run_migration()

        with open(self.new_keyring) as f:
            self.assertEqual(f.read(), "new_password_data")

    def test_no_migration_when_old_keyring_missing(self):
        """Test that no file is created when old keyring doesn't exist."""
        self._run_migration()

        self.assertFalse(os.path.exists(self.new_keyring))

    def test_no_migration_when_neither_exists(self):
        """Test that no error occurs when neither keyring exists."""
        self._run_migration()

        self.assertFalse(os.path.exists(self.old_keyring))
        self.assertFalse(os.path.exists(self.new_keyring))


if __name__ == "__main__":
    unittest.main()
