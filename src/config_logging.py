"""Logging utilities for configuration-related operations.

Provides reusable logging functions to separate logging concerns from
config retrieval logic, following Single Responsibility Principle.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

from typing import Any

from src import get_logger

LOGGER = get_logger()


def log_config_not_found_warning(config_path: list[str], message: str) -> None:
    """Log a warning when a config path is not found.

    Args:
        config_path: List of config keys forming the path
        message: Custom warning message to log
    """
    from src.config_utils import config_path_to_string

    path_str = config_path_to_string(config_path)
    LOGGER.warning(f"{path_str} {message}")


def log_config_found_info(message: str) -> None:
    """Log an info message when config value is found and processed.

    Args:
        message: Info message to log
    """
    LOGGER.info(message)


def log_config_debug(message: str) -> None:
    """Log a debug message for config processing.

    Args:
        message: Debug message to log
    """
    LOGGER.debug(message)


def log_config_error(config_path: list[str], message: str) -> None:
    """Log an error for config validation issues.

    Args:
        config_path: List of config keys forming the path
        message: Error message to log
    """
    from src.config_utils import config_path_to_string

    path_str = config_path_to_string(config_path)
    LOGGER.error(f"{path_str}: {message}")


def log_invalid_config_value(config_path: list[str], invalid_value: Any, valid_values: str) -> None:
    """Log warning about invalid config value.

    Args:
        config_path: List of config keys forming the path
        invalid_value: The invalid value that was found
        valid_values: Description of valid values
    """
    from src.config_utils import config_path_to_string

    path_str = config_path_to_string(config_path)
    LOGGER.warning(f"Invalid value '{invalid_value}' at {path_str}. Valid values: {valid_values}")
