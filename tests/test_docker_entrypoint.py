"""Tests for docker-entrypoint.sh script functionality."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import subprocess
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


if __name__ == "__main__":
    unittest.main()
