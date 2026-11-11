"""Tests for sync module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import logging
import unittest
from unittest.mock import patch

import src
import tests
from src import get_logger, read_config


class TestSrcInit(unittest.TestCase):
    """Tests class for sync module."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.config = read_config(config_path=tests.CONFIG_PATH)
        return super().setUp()

    @patch("src.read_config")
    def test_get_logger_no_config(self, mock_read_config):
        """Test for no config."""
        config = self.config.copy()
        # Add null handler if not configured
        del config["app"]["logger"]
        mock_read_config.return_value = config
        logger = get_logger()
        self.assertTrue(len([h for h in logger.handlers if isinstance(h, logging.NullHandler)]) > 0)

    @patch("src.read_config")
    def test_get_logger(self, mock_read_config):
        """Test for logger."""
        config = self.config.copy()
        # success flow
        mock_read_config.return_value = config
        logger = get_logger()
        self.assertTrue(len(logger.handlers) > 1)

    @patch("src.read_config")
    def test_get_logger_no_duplicate_handlers(self, mock_read_config):
        """Test for no duplicate logger handlers."""
        config = self.config.copy()
        # No duplicate handlers
        mock_read_config.return_value = config
        logger = get_logger()
        number_of_handlers = len(logger.handlers)
        logger = get_logger()
        self.assertEqual(len(logger.handlers), number_of_handlers)


class TestLogRotation(unittest.TestCase):
    """The file handler rotates.

    One line is logged per file *considered* each cycle, so a large
    library grows the log without bound -- a real install reached 5.8 GB
    with no rotation anywhere in the codebase."""

    def test_defaults_are_bounded(self):
        config = {"app": {"logger": {"level": "info", "filename": "icloud.log"}}}
        logger_config = src.get_logger_config(config=config)
        self.assertEqual(logger_config["max_bytes"], src.DEFAULT_LOG_MAX_BYTES)
        self.assertEqual(logger_config["backup_count"], src.DEFAULT_LOG_BACKUP_COUNT)

    def test_a_malformed_bound_falls_back_instead_of_crashing_import(self):
        """This runs at import while logging is being set up, so a typo used
        to raise out of module import and loop the container on restart."""
        from unittest.mock import patch

        config = {
            "app": {
                "logger": {
                    "level": "info",
                    "filename": "icloud.log",
                    "max_bytes": "50MB",
                    "backup_count": None,
                },
            },
        }
        with patch("builtins.print") as said:
            logger_config = src.get_logger_config(config=config)
        self.assertEqual(logger_config["max_bytes"], src.DEFAULT_LOG_MAX_BYTES)
        self.assertEqual(logger_config["backup_count"], src.DEFAULT_LOG_BACKUP_COUNT)
        printed = " ".join(str(c.args[0]) for c in said.call_args_list)
        self.assertIn("app.logger.max_bytes", printed)
        self.assertIn("app.logger.backup_count", printed)

    def test_bounds_are_configurable(self):
        config = {
            "app": {
                "logger": {
                    "level": "info",
                    "filename": "icloud.log",
                    "max_bytes": 1024,
                    "backup_count": 1,
                },
            },
        }
        logger_config = src.get_logger_config(config=config)
        self.assertEqual(logger_config["max_bytes"], 1024)
        self.assertEqual(logger_config["backup_count"], 1)

    def test_handler_is_a_rotating_one(self):
        import logging
        from logging.handlers import RotatingFileHandler

        # get_logger reuses handlers already attached, so an earlier test
        # leaving a plain FileHandler in place would mask the change.
        root = logging.getLogger()
        saved = list(root.handlers)
        for handler in saved:
            root.removeHandler(handler)
        self.addCleanup(lambda: [root.addHandler(h) for h in saved])
        logger = get_logger()
        handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        self.assertTrue(handlers, "expected a file handler")
        self.assertTrue(
            all(isinstance(h, RotatingFileHandler) for h in handlers),
            "file handler should rotate",
        )

    def test_zero_max_bytes_disables_rotation(self):
        """Operators handing the file to an external logrotate can opt out."""
        config = {
            "app": {
                "logger": {"level": "info", "filename": "icloud.log", "max_bytes": 0},
            },
        }
        self.assertEqual(src.get_logger_config(config=config)["max_bytes"], 0)


class TestUnreadableConfigDoesNotBreakImport(unittest.TestCase):
    """``LOGGER = get_logger()`` runs at module scope, so anything raised
    while reading config.yaml stops the container before it can report why
    -- and ``restart: unless-stopped`` turns that into a restart loop."""

    def test_missing_config_falls_back_to_default_logging(self):
        """``read_config`` returns None when the file is not there."""
        from src import get_logger_config

        self.assertIsNone(get_logger_config(config=None))

    def test_wrong_shapes_at_any_level_do_not_raise(self):
        """Parseable-but-wrong YAML must fall back, not TypeError at import."""
        from src import get_logger_config

        for config in (123, "text", ["a"], {"app": 123}, {"app": {"logger": "info"}}, {"app": None}):
            with self.subTest(config=config):
                self.assertIsNone(get_logger_config(config=config))

    def test_partial_config_without_an_app_section(self):
        from src import get_logger_config

        self.assertIsNone(get_logger_config(config={"drive": {}}))

    @patch("src.read_config", side_effect=ValueError("could not parse yaml"))
    def test_unparseable_config_does_not_raise(self, _mock_read_config):
        """A half-written file must not take the process down at import."""
        self.assertIsNotNone(get_logger())


class _RecordingSession:
    """Session double that records the kwargs ``send`` receives.

    ``request`` forwards to ``send`` the way ``requests.Session`` does, so
    the wrapper is exercised at the seam production traffic goes through.
    """

    def __init__(self):
        """Start with no recorded calls."""
        self.calls = []

    def request(self, method, url, **kwargs):
        """Forward like ``requests.Session.request`` does."""
        return self.send(object(), **kwargs)

    def send(self, request, **kwargs):
        """Record the call and answer like a finished response."""
        self.calls.append((request, kwargs))
        return "response"


class TestApplyDefaultRequestTimeout(unittest.TestCase):
    """Tests for apply_default_request_timeout in src/__init__.py."""

    def test_none_session_passes_through(self):
        """No session (a client that failed to build) stays no session."""
        self.assertIsNone(src.apply_default_request_timeout(None))

    def test_missing_timeout_gets_the_default(self):
        """A listing-style call with no timeout is bounded by the default."""
        session = _RecordingSession()
        self.assertIs(src.apply_default_request_timeout(session), session)
        self.assertEqual(session.request("POST", "https://example.invalid/zones/list", data="{}"), "response")
        self.assertEqual(session.calls[0][1]["timeout"], src.DEFAULT_REQUEST_TIMEOUT_SEC)

    def test_explicit_timeout_is_preserved(self):
        """A caller-supplied timeout (the download paths pass theirs) wins."""
        session = _RecordingSession()
        src.apply_default_request_timeout(session, timeout=7)
        session.request("GET", "https://example.invalid", timeout=3)
        self.assertEqual(session.calls[0][1]["timeout"], 3)

    def test_none_timeout_is_filled_with_the_custom_timeout(self):
        """timeout=None means unbounded to requests, so it is filled in too."""
        session = _RecordingSession()
        src.apply_default_request_timeout(session, timeout=7)
        session.request("GET", "https://example.invalid", timeout=None)
        self.assertEqual(session.calls[0][1]["timeout"], 7)

    def test_wrapping_twice_keeps_the_first_wrapper(self):
        """Re-wrapping (a second client built on one session) must not stack."""
        session = _RecordingSession()
        src.apply_default_request_timeout(session, timeout=7)
        wrapped = session.send
        src.apply_default_request_timeout(session, timeout=99)
        self.assertIs(session.send, wrapped)
        session.request("GET", "https://example.invalid")
        self.assertEqual(session.calls[0][1]["timeout"], 7)

    def test_real_requests_session_is_bounded(self):
        """A real requests.Session is marked bounded at send, not request.

        ``ICloudPySession.request`` derives its log logger from
        ``inspect.stack()[2]``; leaving ``request`` alone keeps icloudpy's
        log attribution on the calling service instead of moving it to
        ``requests.sessions``.
        """
        import requests

        session = requests.Session()
        src.apply_default_request_timeout(session, timeout=5)
        self.assertTrue(getattr(session, "_has_default_request_timeout", False))  # noqa: SLF001
        self.assertFalse(getattr(session.request, "_has_default_request_timeout", False))  # noqa: SLF001
