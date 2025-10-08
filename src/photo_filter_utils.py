"""Photo filtering utilities module.

This module contains utilities for photo filtering and validation
during photo synchronization.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"


from src import get_logger

LOGGER = get_logger()


def is_photo_wanted(photo, extensions: list[str] | None) -> bool:
    """Check if photo is wanted based on extension filters.

    Args:
        photo: Photo object from iCloudPy
        extensions: List of allowed file extensions, None means all extensions allowed

    Returns:
        True if photo should be synced, False otherwise
    """
    if not extensions or len(extensions) == 0:
        return True

    for extension in extensions:
        if photo.filename.lower().endswith(str(extension).lower()):
            return True
    return False
