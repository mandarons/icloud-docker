"""Tests for sync module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import logging
import unittest
from unittest.mock import patch

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
