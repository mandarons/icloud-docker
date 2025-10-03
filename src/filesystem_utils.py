"""File system utilities for directory operations.

Provides reusable functions for directory creation and path manipulation,
separated from configuration logic per Single Responsibility Principle.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os


def ensure_directory_exists(path: str) -> str:
    """Create directory if it doesn't exist and return absolute path.

    Args:
        path: Directory path to create

    Returns:
        Absolute path to the created/existing directory
    """
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def join_and_ensure_path(base_path: str, *paths: str) -> str:
    """Join paths and ensure the resulting directory exists.

    Args:
        base_path: Base directory path
        *paths: Additional path components to join

    Returns:
        Absolute path to the created/existing directory
    """
    full_path = os.path.join(base_path, *paths)
    return ensure_directory_exists(full_path)
