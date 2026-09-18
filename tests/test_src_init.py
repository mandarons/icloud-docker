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
