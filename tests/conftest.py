"""Pytest fixtures shared across the test tree.

Session-wide redirect of ``ICLOUD_DOCKER_CONFIG_DIR`` to a writable
tempdir. The container's ``/config`` mount doesn't exist on dev hosts
(macOS especially — read-only root). Without this redirect, the suite
hits FileNotFoundError on ``/config/.data`` (usage cache) and
``/config/session_data`` (icloudpy cookie dir), and a swath of tests
fail despite the production code being correct.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import tempfile

import pytest

_CONFIG_DIR_KEY = "ICLOUD_DOCKER_CONFIG_DIR"


@pytest.fixture(scope="session", autouse=True)
def _redirect_config_dir():
    """Session-wide ``ICLOUD_DOCKER_CONFIG_DIR`` → tempdir.

    The redirect MUST be set before any ``from src import ...`` happens
    at module-import time (because ``DEFAULT_COOKIE_DIRECTORY`` is
    captured at import). Pytest collects conftest first, so this fires
    early — but we also patch the cached constants here in case ``src``
    was already imported by an earlier conftest layer.
    """
    if _CONFIG_DIR_KEY in os.environ:
        # Honor explicit caller override (e.g. CI integration tests).
        yield
        return

    tmpdir = tempfile.mkdtemp(prefix="icloud_test_config_")
    os.environ[_CONFIG_DIR_KEY] = tmpdir

    import src
    import src.usage

    src.DEFAULT_COOKIE_DIRECTORY = os.path.join(tmpdir, "session_data")
    src.usage.CACHE_FILE_NAME = os.path.join(tmpdir, ".data")
    os.makedirs(src.DEFAULT_COOKIE_DIRECTORY, exist_ok=True)
    try:
        yield
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
        os.environ.pop(_CONFIG_DIR_KEY, None)
