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



class TestConfigSubdirsBelongToAbc(unittest.TestCase):
    """The entrypoint runs as root and creates session_data and
    python_keyring. Its ownership loop skips /config when /config is already
    owned by abc (the usual bind mount), which left both root-owned and the
    documented 2FA command unable to write its session file."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker-entrypoint.sh")
        with open(path, encoding="utf-8") as fh:
            self.lines = fh.read().splitlines()

    def _index(self, predicate, what):
        index = next((i for i, line in enumerate(self.lines) if predicate(line.strip())), None)
        self.assertIsNotNone(index, f"{what} not found in docker-entrypoint.sh")
        return index

    def test_both_subdirs_are_chowned_unconditionally_after_creation(self):
        created = self._index(
            lambda line: line.startswith("mkdir -p") and "/config/python_keyring" in line,
            "`mkdir -p` creating /config/python_keyring",
        )
        chowned = self._index(
            lambda line: line.startswith("chown -R abc:abc")
            and "/config/session_data" in line
            and "/config/python_keyring" in line,
            "unconditional `chown -R abc:abc /config/session_data /config/python_keyring`",
        )
        handed_over = self._index(
            lambda line: line.startswith("exec su-exec abc"),
            "`exec su-exec abc`",
        )
        self.assertLess(created, chowned)
        self.assertLess(chowned, handed_over)
        # Not indented: the fix must not sit inside the conditional loop.
        self.assertFalse(self.lines[chowned].startswith((" ", "\t")))


class TestUmask(unittest.TestCase):
    """`UMASK` must reach the process, not just the container environment.

    Issue #608: the variable was present in the environment but the entrypoint
    never applied it, so files were created 0644/0755 instead of 0664/0775.
    The function under test is extracted from the real script, so the test
    cannot drift from the implementation.
    """

    def setUp(self):
        self.entrypoint_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "docker-entrypoint.sh",
        )
        with open(self.entrypoint_path, encoding="utf-8") as fh:
            self.script = fh.read()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _function(self):
        """Return the `apply_umask` definition exactly as shipped."""
        start = self.script.index("apply_umask() {")
        end = self.script.index("\n}\n", start) + len("\n}\n")
        return self.script[start:end]

    def _run(self, umask=None):
        """Run the shipped function, then report umask and created modes."""
        env = dict(os.environ)
        env.pop("UMASK", None)
        if umask is not None:
            env["UMASK"] = umask
        env["UMASK_TEST_DIR"] = self.tmpdir
        snippet = (
            self._function()
            + "\napply_umask\numask\n"
            + 'touch "$UMASK_TEST_DIR/file" && mkdir -p "$UMASK_TEST_DIR/dir"\n'
        )
        return subprocess.run(
            ["sh", "-c", snippet], capture_output=True, text=True, env=env,
        )

    def _modes(self):
        file_mode = os.stat(os.path.join(self.tmpdir, "file")).st_mode & 0o777
        dir_mode = os.stat(os.path.join(self.tmpdir, "dir")).st_mode & 0o777
        return file_mode, dir_mode

    def test_umask_002_is_applied(self):
        """The reported case: group-writable files and directories."""
        result = self._run("002")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(result.stdout.strip(), 8), 0o002)
        self.assertEqual(self._modes(), (0o664, 0o775))

    def test_default_is_022(self):
        """An unset variable keeps the previous image default."""
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(result.stdout.strip(), 8), 0o022)
        self.assertEqual(self._modes(), (0o644, 0o755))

    def test_four_digit_value_is_accepted(self):
        """`0022` is a common compose spelling and must not warn."""
        result = self._run("0022")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(result.stdout.strip(), 8), 0o022)
        self.assertNotIn("Invalid UMASK", result.stdout)

    def test_invalid_value_warns_and_falls_back(self):
        """A bad value must not fail the container start."""
        for value in ("abc", "999", "0o22"):
            with self.subTest(value=value):
                result = self._run(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"Invalid UMASK '{value}'", result.stdout)
                self.assertEqual(int(result.stdout.strip().splitlines()[-1], 8), 0o022)

    def test_applied_before_directories_are_created_and_privileges_dropped(self):
        """Created directories and the app process must inherit the mask."""
        applied = self.script.index("\napply_umask\n")
        first_mkdir = self.script.index("mkdir -p")
        handed_over = self.script.index("exec su-exec abc")
        self.assertLess(applied, first_mkdir)
        self.assertLess(applied, handed_over)


if __name__ == "__main__":
    unittest.main()
