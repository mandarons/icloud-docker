"""Hardlink registry management module.

This module contains utilities for managing hardlink registry
during photo synchronization to avoid duplicate downloads.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"


from src import get_logger

LOGGER = get_logger()


class HardlinkRegistry:
    """Registry to track downloaded photos for hardlink creation.

    This class manages a registry of downloaded photos to enable hardlink
    creation for duplicate photos across different albums.
    """

    def __init__(self):
        """Initialize hardlink registry."""
        self._registry: dict[str, str] = {}

    def get_existing_path(self, photo_id: str, file_size: str) -> str | None:
        """Get existing path for photo if it was already downloaded.

        Args:
            photo_id: Unique photo identifier
            file_size: File size variant (original, medium, thumb, etc.)

        Returns:
            Path to existing file if found, None otherwise
        """
        photo_key = f"{photo_id}_{file_size}"
        return self._registry.get(photo_key)

    def register_photo_path(self, photo_id: str, file_size: str, file_path: str) -> None:
        """Register a downloaded photo path for future hardlink creation.

        Args:
            photo_id: Unique photo identifier
            file_size: File size variant (original, medium, thumb, etc.)
            file_path: Path where photo was downloaded
        """
        photo_key = f"{photo_id}_{file_size}"
        self._registry[photo_key] = file_path

    def get_registry_size(self) -> int:
        """Get number of registered photos.

        Returns:
            Number of photos in the registry
        """
        return len(self._registry)

    def clear(self) -> None:
        """Clear the registry."""
        self._registry.clear()


def create_hardlink_registry(use_hardlinks: bool) -> HardlinkRegistry | None:
    """Create hardlink registry if hardlinks are enabled.

    Args:
        use_hardlinks: Whether hardlinks are enabled in configuration

    Returns:
        HardlinkRegistry instance if hardlinks enabled, None otherwise
    """
    return HardlinkRegistry() if use_hardlinks else None
