"""Configuration utility functions for reusable config operations.

This module provides low-level utilities for configuration traversal and retrieval,
separated from business logic to follow Single Responsibility Principle.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

from typing import Any


def config_path_to_string(config_path: list[str]) -> str:
    """Build config path as string for display purposes.

    Args:
        config_path: List of config keys forming a path (e.g., ["app", "credentials", "username"])

    Returns:
        String representation of the config path (e.g., "app > credentials > username")
    """
    return " > ".join(config_path)


def traverse_config_path(config: dict, config_path: list[str]) -> bool:
    """Traverse and validate existence of a config path.

    Recursively checks if a path exists in the configuration dictionary.
    Does not retrieve values, only validates path existence.

    Args:
        config: Configuration dictionary to traverse
        config_path: List of keys forming the path to check

    Returns:
        True if path exists and is valid, False otherwise
    """
    if len(config_path) == 0:
        return True
    if not (config and config_path[0] in config):
        return False
    return traverse_config_path(config[config_path[0]], config_path=config_path[1:])


def get_config_value(config: dict, config_path: list[str]) -> Any:
    """Retrieve value from config using a path.

    Recursively navigates the configuration dictionary to retrieve a value.
    Should only be called after validating path existence with traverse_config_path().

    Args:
        config: Configuration dictionary
        config_path: List of keys forming the path to the value

    Returns:
        The configuration value at the specified path

    Raises:
        KeyError: If the path doesn't exist (should be prevented by prior validation)
    """
    if len(config_path) == 1:
        return config[config_path[0]]
    return get_config_value(config=config[config_path[0]], config_path=config_path[1:])


def get_config_value_or_none(config: dict, config_path: list[str]) -> Any | None:
    """Safely retrieve config value or return None if path doesn't exist.

    Combines path validation and value retrieval for cases where None is acceptable.

    Args:
        config: Configuration dictionary
        config_path: List of keys forming the path to the value

    Returns:
        The configuration value if path exists, None otherwise
    """
    if not traverse_config_path(config=config, config_path=config_path):
        return None
    return get_config_value(config=config, config_path=config_path)


def get_config_value_or_default(config: dict, config_path: list[str], default: Any) -> Any:
    """Retrieve config value or return default if path doesn't exist.

    Args:
        config: Configuration dictionary
        config_path: List of keys forming the path to the value
        default: Default value to return if path doesn't exist

    Returns:
        The configuration value if path exists, default otherwise
    """
    value = get_config_value_or_none(config=config, config_path=config_path)
    return value if value is not None else default
