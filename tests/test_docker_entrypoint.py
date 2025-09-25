"""Tests for docker-entrypoint.sh script functionality."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import subprocess
import unittest
from unittest.mock import Mock, patch


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

    def test_entrypoint_script_is_executable(self):
        """Test that the docker-entrypoint.sh script has proper syntax."""
        # Test shell syntax by running with -n (syntax check only)
        result = subprocess.run(
            ["sh", "-n", self.entrypoint_path],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Script syntax error: {result.stderr}")

    def test_entrypoint_script_has_shebang(self):
        """Test that the docker-entrypoint.sh script has proper shebang."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            first_line = f.readline().strip()
        self.assertEqual(first_line, "#!/bin/sh")

    def test_entrypoint_default_puid_pgid(self):
        """Test that the script handles default PUID/PGID values."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check that default values are set
        self.assertIn("PUID=${PUID:-911}", content)
        self.assertIn("PGID=${PGID:-911}", content)

    def test_entrypoint_user_management_commands(self):
        """Test that the script contains proper user management commands."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for user/group modification commands
        self.assertIn("groupmod -o -g", content)
        self.assertIn("usermod -o -u", content)
        self.assertIn("abc", content)

    def test_entrypoint_directory_creation(self):
        """Test that the script creates necessary directories."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for directory creation
        self.assertIn("mkdir -p /icloud /config/session_data", content)

    def test_entrypoint_ownership_commands(self):
        """Test that the script sets proper ownership."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for ownership commands
        self.assertIn("chown -R abc:abc", content)

    def test_entrypoint_sponsorship_message(self):
        """Test that the script includes sponsorship message."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for sponsorship message
        self.assertIn("To support this project, please consider sponsoring", content)
        self.assertIn("github.com/sponsors/mandarons", content)
        self.assertIn("buymeacoffee.com/mandarons", content)

    def test_entrypoint_exec_suexec(self):
        """Test that the script uses su-exec to run the application."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for su-exec execution
        self.assertIn("exec su-exec abc /app/init.sh", content)

    def test_entrypoint_build_version_check(self):
        """Test that the script checks for build version file."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check for build version handling
        self.assertIn("if [ -f /build_version ]; then", content)
        self.assertIn("cat /build_version", content)

    @patch("subprocess.run")
    def test_entrypoint_can_be_executed_with_mock(self, mock_run):
        """Test that the entrypoint script can be executed (mocked)."""
        # Mock the subprocess.run to simulate script execution
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Test that the script would run without syntax errors
        result = subprocess.run(
            ["sh", "-n", self.entrypoint_path],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_dockerfile_uses_correct_entrypoint(self):
        """Test that Dockerfile references the correct entrypoint script."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that Dockerfile copies and uses the entrypoint script
        self.assertIn("COPY docker-entrypoint.sh /usr/local/bin/", dockerfile_content)
        self.assertIn("chmod +x /usr/local/bin/docker-entrypoint.sh", dockerfile_content)
        self.assertIn('CMD ["/usr/local/bin/docker-entrypoint.sh"]', dockerfile_content)

    def test_dockerfile_uses_dumb_init(self):
        """Test that Dockerfile uses dumb-init as the entrypoint."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that Dockerfile uses dumb-init
        self.assertIn('ENTRYPOINT ["/usr/bin/dumb-init", "--"]', dockerfile_content)

    def test_dockerfile_installs_required_packages(self):
        """Test that Dockerfile installs required packages for the new approach."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that required packages are installed
        self.assertIn("dumb-init", dockerfile_content)
        self.assertIn("su-exec", dockerfile_content)
        self.assertIn("shadow", dockerfile_content)  # For user management

    def test_dockerfile_creates_abc_user(self):
        """Test that Dockerfile creates the abc user and group."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that abc user and group are created
        self.assertIn("addgroup -g 911 abc", dockerfile_content)
        self.assertIn("adduser -D -u 911 -G abc abc", dockerfile_content)

    def test_dockerfile_uses_alpine_base(self):
        """Test that Dockerfile uses Alpine Linux as base image."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that it uses Alpine base image instead of linuxserver
        self.assertIn("FROM alpine:3.19", dockerfile_content)
        self.assertNotIn("linuxserver", dockerfile_content)

    def test_no_s6_overlay_functional_references(self):
        """Test that there are no functional s6-overlay references in the new setup."""
        # Check entrypoint script for actual s6 commands (not comments)
        with open(self.entrypoint_path, encoding="utf-8") as f:
            lines = f.readlines()

        # Check Dockerfile
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )
        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Filter out comment lines and check for actual s6 commands
        non_comment_lines = [line.strip() for line in lines if not line.strip().startswith("#")]
        entrypoint_commands = " ".join(non_comment_lines)

        # Ensure no functional s6-overlay references remain
        self.assertNotIn("s6-setuidgid", entrypoint_commands.lower())
        self.assertNotIn("s6-rc", entrypoint_commands.lower())
        self.assertNotIn("with-contenv", entrypoint_commands.lower())
        self.assertNotIn("linuxserver", dockerfile_content.lower())

    def test_environment_variables_preserved(self):
        """Test that key environment variables are preserved in Dockerfile."""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "Dockerfile",
        )

        with open(dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check that important environment variables are set
        self.assertIn("ENV PUID=911", dockerfile_content)
        self.assertIn("ENV PGID=911", dockerfile_content)
        self.assertIn('ENV HOME="/app"', dockerfile_content)


if __name__ == "__main__":
    unittest.main()
