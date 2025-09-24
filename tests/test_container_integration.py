"""Integration tests for container functionality after s6-overlay removal."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unittest
from unittest.mock import Mock, patch


class TestContainerIntegration(unittest.TestCase):
    """Integration tests for container functionality."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.repo_root = os.path.dirname(os.path.dirname(__file__))
        self.entrypoint_path = os.path.join(self.repo_root, "docker-entrypoint.sh")
        self.dockerfile_path = os.path.join(self.repo_root, "Dockerfile")
        self.init_script_path = os.path.join(self.repo_root, "init.sh")
        return super().setUp()

    def test_init_script_compatibility(self):
        """Test that init.sh is compatible with the new setup."""
        # Check that init.sh exists and has correct content
        self.assertTrue(os.path.exists(self.init_script_path))

        with open(self.init_script_path, encoding="utf-8") as f:
            content = f.read()

        # Verify init.sh uses the correct Python virtual environment path
        self.assertIn("/venv/bin", content)
        self.assertIn("python ./src/main.py", content)

    def test_dockerfile_removes_linuxserver_dependencies(self):
        """Test that Dockerfile no longer depends on linuxserver base image."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Should not contain linuxserver references
        self.assertNotIn("linuxserver", content.lower())
        self.assertNotIn("lsiown", content.lower())

        # Should use Alpine base
        self.assertIn("FROM alpine:3.19", content)

    def test_dockerfile_package_installation(self):
        """Test that Dockerfile installs all required packages."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        required_packages = [
            "python3",
            "py3-pip",
            "sudo",
            "libmagic",
            "shadow",
            "dumb-init",
            "su-exec",
        ]

        for package in required_packages:
            self.assertIn(package, content, f"Required package '{package}' not found in Dockerfile")

    def test_dockerfile_user_creation(self):
        """Test that Dockerfile properly creates the abc user."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Check user and group creation
        self.assertIn("addgroup -g 911 abc", content)
        self.assertIn("adduser -D -u 911 -G abc abc", content)

    def test_dockerfile_directory_creation(self):
        """Test that Dockerfile creates necessary directories."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Check directory creation
        self.assertIn("mkdir -p /icloud /config/session_data", content)
        self.assertIn("chown -R abc:abc /app /config /icloud", content)

    def test_entrypoint_environment_handling(self):
        """Test that entrypoint properly handles environment variables."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            content = f.read()

        # Check environment variable handling
        self.assertIn("PUID=${PUID:-911}", content)
        self.assertIn("PGID=${PGID:-911}", content)

    @patch("subprocess.run")
    def test_entrypoint_script_execution_simulation(self, mock_run):
        """Test entrypoint script execution with mocked system calls."""
        # Mock successful execution of system commands
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Read the entrypoint script
        with open(self.entrypoint_path, encoding="utf-8") as f:
            script_content = f.read()

        # Verify the script contains expected commands
        expected_commands = [
            "groupmod",
            "usermod",
            "mkdir -p",
            "chown",
            "exec su-exec",
        ]

        for cmd in expected_commands:
            self.assertIn(cmd, script_content)

    def test_dockerfile_entrypoint_configuration(self):
        """Test that Dockerfile properly configures the entrypoint."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Check entrypoint configuration
        self.assertIn('ENTRYPOINT ["/usr/bin/dumb-init", "--"]', content)
        self.assertIn('CMD ["/usr/local/bin/docker-entrypoint.sh"]', content)
        self.assertIn("COPY docker-entrypoint.sh /usr/local/bin/", content)
        self.assertIn("chmod +x /usr/local/bin/docker-entrypoint.sh", content)

    def test_python_venv_setup(self):
        """Test that Dockerfile sets up Python virtual environment correctly."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Check Python venv setup
        self.assertIn("python3 -m venv /venv", content)
        self.assertIn("/venv/bin/pip install", content)

    def test_build_cleanup(self):
        """Test that Dockerfile properly cleans up after build."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Check cleanup commands
        self.assertIn("apk del --purge", content)
        self.assertIn("build-dependencies", content)
        self.assertIn("rm -rf", content)

    def test_compatibility_with_existing_volumes(self):
        """Test that the new setup is compatible with existing volume mounts."""
        # Read both entrypoint and dockerfile
        with open(self.entrypoint_path, encoding="utf-8") as f:
            entrypoint_content = f.read()

        with open(self.dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Verify that standard volume mount points are handled
        expected_paths = ["/config", "/icloud", "/app"]

        for path in expected_paths:
            # Should be mentioned in either entrypoint or dockerfile
            path_found = path in entrypoint_content or path in dockerfile_content
            self.assertTrue(path_found, f"Volume path {path} not properly handled")

    def test_environment_variable_defaults(self):
        """Test that environment variables have proper defaults."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            dockerfile_content = f.read()

        # Check default environment variables
        self.assertIn("ENV PUID=911", dockerfile_content)
        self.assertIn("ENV PGID=911", dockerfile_content)
        self.assertIn('ENV HOME="/app"', dockerfile_content)

    def test_s6_overlay_functionality_replacement(self):
        """Test that key s6-overlay functionality has been replaced."""
        with open(self.entrypoint_path, encoding="utf-8") as f:
            entrypoint_content = f.read()

        # Check that entrypoint handles what s6-overlay used to do:
        # 1. User management
        self.assertIn("groupmod", entrypoint_content)
        self.assertIn("usermod", entrypoint_content)

        # 2. Directory creation and permissions
        self.assertIn("mkdir -p", entrypoint_content)
        self.assertIn("chown", entrypoint_content)

        # 3. Process execution as correct user
        self.assertIn("su-exec abc", entrypoint_content)

        # 4. Information display (equivalent to s6 service messages)
        self.assertIn("Setting up user", entrypoint_content)

    def test_no_dependency_on_s6_specific_tools(self):
        """Test that new setup doesn't depend on s6-specific tools."""
        files_to_check = [self.dockerfile_path, self.entrypoint_path, self.init_script_path]

        s6_tools = ["s6-setuidgid", "s6-rc", "with-contenv", "s6-overlay"]

        for file_path in files_to_check:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            for tool in s6_tools:
                # Skip comments that mention s6 for documentation purposes
                lines = [line.strip() for line in content.split("\n")
                        if not line.strip().startswith("#")]
                non_comment_content = "\n".join(lines)

                self.assertNotIn(tool, non_comment_content,
                    f"Found s6 tool '{tool}' in {os.path.basename(file_path)}")

    def test_dockerfile_build_stages_optimization(self):
        """Test that Dockerfile is optimized for build efficiency."""
        with open(self.dockerfile_path, encoding="utf-8") as f:
            content = f.read()

        # Should have proper layer organization
        # Check that expensive operations (package installs) are early
        lines = content.split("\n")

        # Find where packages are installed vs where app files are copied
        package_install_line = -1
        app_copy_line = -1

        for i, line in enumerate(lines):
            if "apk add" in line and package_install_line == -1:
                package_install_line = i
            if "COPY . /app/" in line:
                app_copy_line = i

        # Package installation should come before app copying for better caching
        if package_install_line > -1 and app_copy_line > -1:
            self.assertLess(package_install_line, app_copy_line,
                          "Package installation should come before app files for better Docker layer caching")


if __name__ == "__main__":
    unittest.main()
