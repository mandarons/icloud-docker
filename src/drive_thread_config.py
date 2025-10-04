"""Thread configuration utilities.

This module provides thread configuration functionality for parallel operations,
separating thread management from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

from typing import Any

from src import config_parser, configure_icloudpy_logging, get_logger

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def get_max_threads(config: Any) -> int:
    """Get maximum number of threads for parallel downloads.

    Args:
        config: Configuration dictionary

    Returns:
        Maximum number of threads to use
    """
    return config_parser.get_app_max_threads(config)
