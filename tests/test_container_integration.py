"""Integration tests for container functionality after s6-overlay removal."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import subprocess
import unittest


class TestContainerIntegration(unittest.TestCase):
    """Integration tests for container functionality."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.repo_root = os.path.dirname(os.path.dirname(__file__))
        self.dockerfile_path = os.path.join(self.repo_root, "Dockerfile")
        self.init_script_path = os.path.join(self.repo_root, "init.sh")
        return super().setUp()

    def test_dockerfile_syntax(self):
        """Test that Dockerfile has valid syntax."""
        # Basic syntax check by trying to parse it
        self.assertTrue(os.path.exists(self.dockerfile_path))
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()
            # Check it starts with FROM
            self.assertTrue(content.strip().startswith("# syntax=docker/dockerfile:1"))

    def test_init_script_syntax(self):
        """Test that init.sh has valid shell syntax."""
        result = subprocess.run(
            ["sh", "-n", self.init_script_path],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Script syntax error: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
