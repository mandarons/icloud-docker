__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import logging
from unittest.mock import patch
from src import read_config, get_logger
import tests


class TestSrcInit(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read_config(config_path=tests.CONFIG_PATH)
        return super().setUp()

    def tearDown(self) -> None:
        pass

    @patch("src.read_config")
    def test_get_logger_no_config(self, mock_read_config):
        config = self.config.copy()
        # Add null handler if not configured
        del config["app"]["logger"]
        mock_read_config.return_value = config
        logger = get_logger()
        self.assertTrue(
            len([h for h in logger.handlers if isinstance(h, logging.NullHandler)]) > 0
        )

    @patch("src.read_config")
    def test_get_logger(self, mock_read_config):
        config = self.config.copy()
        # success flow
        mock_read_config.return_value = config
        logger = get_logger()
        self.assertTrue(len(logger.handlers) > 1)

    @patch("src.read_config")
    def test_get_logger_no_duplicate_handlers(self, mock_read_config):
        config = self.config.copy()
        # No duplicate hanlders
        mock_read_config.return_value = config
        logger = get_logger()
        number_of_handlers = len(logger.handlers)
        logger = get_logger()
        self.assertEqual(len(logger.handlers), number_of_handlers)
