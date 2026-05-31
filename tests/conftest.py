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

    Implementation note: the ``os.environ`` setting alone is NOT what
    makes the redirect work. ``DEFAULT_COOKIE_DIRECTORY`` and
    ``CACHE_FILE_NAME`` are captured at module-import time, and by the
    time this autouse fixture runs (first test execution) the test
    modules have already done ``from src import ...`` and the constants
    have already resolved to ``/config/...``. The reassignment of
    ``src.DEFAULT_COOKIE_DIRECTORY`` / ``src.usage.CACHE_FILE_NAME``
    below is what actually redirects callers. The env-var set is kept
    only so child processes (if any) inherit the override. Future
    contributors who add a new module that captures
    ``ICLOUD_DOCKER_CONFIG_DIR`` at import time MUST add a matching
    reassignment here.
    """
    # Resolve the target config dir: external override if the caller
    # set it (e.g. CI integration tests), otherwise a fresh tempdir.
    # Note the cleanup contract differs: we never rmtree an externally
    # supplied dir, only the tempdir we created ourselves.
    external = _CONFIG_DIR_KEY in os.environ
    tmpdir = (
        os.environ[_CONFIG_DIR_KEY]
        if external
        else tempfile.mkdtemp(prefix="icloud_test_config_")
    )
    if not external:
        os.environ[_CONFIG_DIR_KEY] = tmpdir

    # The constants were captured at import time; re-sync them to the
    # resolved dir whether it came from env override or the tempdir.
    # Without this re-sync on the override path, the same
    # FileNotFoundError chain this fixture exists to prevent would
    # resurface (callers would still read /config-resolved paths from
    # the captured constants).
    import src
    import src.usage

    src.DEFAULT_COOKIE_DIRECTORY = os.path.join(tmpdir, "session_data")
    src.usage.CACHE_FILE_NAME = os.path.join(tmpdir, ".data")
    # NOTE: we deliberately do NOT pre-create ``session_data/`` here.
    # ``tests/test_sync.py::test_sync`` asserts that ``sync.sync()``
    # itself creates the directory on first run; pre-creating would
    # make that assertion trivially pass regardless of whether the
    # production code path actually ran.
    try:
        yield
    finally:
        # Only clean up if WE owned the tempdir — leave externally-
        # supplied dirs (CI mounts, user-managed paths) intact.
        if not external:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
            os.environ.pop(_CONFIG_DIR_KEY, None)
