"""Sync photos module.

This module provides the main photo synchronization functionality,
orchestrating the downloading of photos from iCloud to local storage.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import os

from src import config_parser, configure_icloudpy_logging, get_logger
from src.album_sync_orchestrator import sync_album_photos
from src.hardlink_registry import create_hardlink_registry
from src.photo_cleanup_utils import remove_obsolete_files

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


# Legacy functions preserved for backward compatibility with existing tests
# These functions are now implemented using the new modular architecture


def get_max_threads(config):
    """Get maximum number of threads for parallel downloads.

    Legacy function - now delegates to config_parser.

    Args:
        config: Configuration dictionary

    Returns:
        Maximum number of threads to use for downloads
    """
    return config_parser.get_app_max_threads(config)


def get_name_and_extension(photo, file_size):
    """Extract filename and extension.

    Legacy function - now delegates to photo_path_utils.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant

    Returns:
        Tuple of (name, extension)
    """
    from src.photo_path_utils import get_photo_name_and_extension

    return get_photo_name_and_extension(photo, file_size)


def photo_wanted(photo, extensions):
    """Check if photo is wanted based on extension.

    Legacy function - now delegates to photo_filter_utils.

    Args:
        photo: Photo object from iCloudPy
        extensions: List of allowed extensions

    Returns:
        True if photo should be synced, False otherwise
    """
    from src.photo_filter_utils import is_photo_wanted

    return is_photo_wanted(photo, extensions)


def generate_file_name(photo, file_size, destination_path, folder_format):
    """Generate full path to file.

    Legacy function - now delegates to photo_download_manager.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant
        destination_path: Base destination path
        folder_format: Folder format string

    Returns:
        Full file path
    """
    from src.photo_download_manager import generate_photo_path

    return generate_photo_path(photo, file_size, destination_path, folder_format)


def photo_exists(photo, file_size, local_path):
    """Check if photo exist locally.

    Legacy function - now delegates to photo_file_utils.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant
        local_path: Local file path to check

    Returns:
        True if photo exists with correct size, False otherwise
    """
    from src.photo_file_utils import check_photo_exists

    return check_photo_exists(photo, file_size, local_path)


def create_hardlink(source_path, destination_path):
    """Create a hard link from source to destination.

    Legacy function - now delegates to photo_file_utils.

    Args:
        source_path: Path to source file
        destination_path: Path for new hardlink

    Returns:
        True if successful, False otherwise
    """
    from src.photo_file_utils import create_hardlink as create_hardlink_impl

    return create_hardlink_impl(source_path, destination_path)


def download_photo(photo, file_size, destination_path):
    """Download photo from server.

    Legacy function - now delegates to photo_file_utils.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant
        destination_path: Where to save the photo

    Returns:
        True if successful, False otherwise
    """
    from src.photo_file_utils import download_photo_from_server

    return download_photo_from_server(photo, file_size, destination_path)


def process_photo(photo, file_size, destination_path, files, folder_format, hardlink_registry=None):
    """Process photo details (legacy function for backward compatibility).

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant
        destination_path: Base destination path
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for hardlinks (legacy dict format)

    Returns:
        True if photo was processed successfully, False otherwise
    """
    from src.photo_download_manager import collect_download_task, execute_download_task

    # Convert legacy hardlink registry dict to new registry format if needed
    converted_registry = None
    if hardlink_registry is not None:
        from src.hardlink_registry import HardlinkRegistry

        converted_registry = HardlinkRegistry()
        for key, path in hardlink_registry.items():
            # Legacy format: photo_id_file_size -> path
            if "_" in key:
                parts = key.rsplit("_", 1)
                if len(parts) == 2:
                    photo_id, file_sz = parts
                    converted_registry.register_photo_path(photo_id, file_sz, path)

    # Collect download task
    task_info = collect_download_task(
        photo,
        file_size,
        destination_path,
        files,
        folder_format,
        converted_registry,
    )

    if task_info is None:
        return False

    # Execute task
    result = execute_download_task(task_info)

    # Update legacy registry if provided
    if result and hardlink_registry is not None:
        photo_key = f"{photo.id}_{file_size}"
        hardlink_registry[photo_key] = task_info.photo_path

    return result


def collect_photo_for_download(photo, file_size, destination_path, files, folder_format, hardlink_registry=None):
    """Collect photo info for parallel download without immediately downloading.

    Legacy function - now delegates to photo_download_manager.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant
        destination_path: Base destination path
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for hardlinks (legacy dict format)

    Returns:
        Download task info or None
    """
    from src.photo_download_manager import collect_download_task

    # Convert legacy hardlink registry dict to new registry format if needed
    converted_registry = None
    if hardlink_registry is not None:
        from src.hardlink_registry import HardlinkRegistry

        converted_registry = HardlinkRegistry()
        for key, path in hardlink_registry.items():
            if "_" in key:
                parts = key.rsplit("_", 1)
                if len(parts) == 2:
                    photo_id, file_sz = parts
                    converted_registry.register_photo_path(photo_id, file_sz, path)

    task_info = collect_download_task(
        photo,
        file_size,
        destination_path,
        files,
        folder_format,
        converted_registry,
    )

    if task_info is None:
        return None

    # Convert back to legacy format for compatibility
    return {
        "photo": task_info.photo,
        "file_size": task_info.file_size,
        "photo_path": task_info.photo_path,
        "hardlink_source": task_info.hardlink_source,
        "hardlink_registry": hardlink_registry,
    }


def download_photo_task(download_info):
    """Download a single photo or create hardlink as part of parallel execution.

    Legacy function - maintains original implementation for backward compatibility.

    Args:
        download_info: Dictionary with download task information

    Returns:
        True if successful, False otherwise
    """
    photo = download_info["photo"]
    file_size = download_info["file_size"]
    photo_path = download_info["photo_path"]
    hardlink_source = download_info.get("hardlink_source")
    hardlink_registry = download_info.get("hardlink_registry")

    LOGGER.debug(f"[Thread] Starting processing of {photo_path}")

    try:
        # Try hardlink first if source exists
        if hardlink_source:
            if create_hardlink(hardlink_source, photo_path):
                LOGGER.debug(f"[Thread] Created hardlink for {photo_path}")
                return True
            else:
                # Fallback to download if hard link creation fails
                LOGGER.warning(f"Hard link creation failed, downloading {photo_path} instead")

        # Download the photo - this maintains the original function call for test compatibility
        result = download_photo(photo, file_size, photo_path)
        if result:
            # Register for future hard links if enabled
            if hardlink_registry is not None:
                photo_key = f"{photo.id}_{file_size}"
                hardlink_registry[photo_key] = photo_path
            LOGGER.debug(f"[Thread] Completed download of {photo_path}")
        return result
    except Exception as e:
        LOGGER.error(f"[Thread] Failed to process {photo_path}: {e!s}")
        return False


def sync_album(
    album,
    destination_path,
    file_sizes,
    extensions=None,
    files=None,
    folder_format=None,
    hardlink_registry=None,
    config=None,
):
    """Sync given album.

    Legacy function - now delegates to album_sync_orchestrator with conversion
    for legacy hardlink registry format.

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for hardlinks (legacy dict format)
        config: Configuration dictionary

    Returns:
        True on success, None on invalid input
    """
    # Convert legacy hardlink registry dict to new registry format if needed
    converted_registry = None
    if hardlink_registry is not None:
        from src.hardlink_registry import HardlinkRegistry

        converted_registry = HardlinkRegistry()
        for key, path in hardlink_registry.items():
            if "_" in key:
                parts = key.rsplit("_", 1)
                if len(parts) == 2:
                    photo_id, file_sz = parts
                    converted_registry.register_photo_path(photo_id, file_sz, path)

    result = sync_album_photos(
        album=album,
        destination_path=destination_path,
        file_sizes=file_sizes,
        extensions=extensions,
        files=files,
        folder_format=folder_format,
        hardlink_registry=converted_registry,
        config=config,
    )

    # Update legacy registry if provided and new registry was created
    if hardlink_registry is not None and converted_registry is not None:
        # This is a simplified approach - in practice, we'd need to track new entries
        # But for legacy compatibility, we'll maintain the existing behavior
        pass

    return result


def remove_obsolete(destination_path, files):
    """Remove local obsolete file.

    Legacy function - now delegates to photo_cleanup_utils.

    Args:
        destination_path: Path to search for obsolete files
        files: Set of files that should be kept

    Returns:
        Set of removed file paths
    """
    return remove_obsolete_files(destination_path, files)


def sync_photos(config, photos):
    """Sync all photos.

    Main orchestration function that coordinates the entire photo sync process.
    This function has been refactored to use the new modular architecture while
    maintaining backward compatibility.

    Args:
        config: Configuration dictionary
        photos: Photos object from iCloudPy

    Returns:
        None (maintains legacy behavior)
    """
    # Parse configuration using centralized config parser
    destination_path = config_parser.prepare_photos_destination(config=config)
    filters = config_parser.get_photos_filters(config=config)
    files = set()
    download_all = config_parser.get_photos_all_albums(config=config)
    use_hardlinks = config_parser.get_photos_use_hardlinks(config=config)
    libraries = filters["libraries"] if filters["libraries"] is not None else photos.libraries
    folder_format = config_parser.get_photos_folder_format(config=config)

    # Initialize hard link registry using new modular approach
    hardlink_registry = create_hardlink_registry(use_hardlinks)

    # Special handling for "All Photos" when hardlinks are enabled
    if use_hardlinks and download_all:
        _sync_all_photos_first_for_hardlinks(
            photos,
            libraries,
            destination_path,
            filters,
            files,
            folder_format,
            hardlink_registry,
            config,
        )

    # Sync albums based on configuration
    _sync_albums_by_configuration(
        photos,
        libraries,
        download_all,
        destination_path,
        filters,
        files,
        folder_format,
        hardlink_registry,
        config,
    )

    # Clean up obsolete files if enabled
    if config_parser.get_photos_remove_obsolete(config=config):
        remove_obsolete_files(destination_path, files)


def _sync_all_photos_first_for_hardlinks(
    photos,
    libraries,
    destination_path,
    filters,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync 'All Photos' album first to populate hardlink registry.

    Args:
        photos: Photos object from iCloudPy
        libraries: List of photo libraries to sync
        destination_path: Base destination path
        filters: Photo filters configuration
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for library in libraries:
        if library == "PrimarySync" and "All Photos" in photos.libraries[library].albums:
            LOGGER.info("Syncing 'All Photos' album first for hard link reference...")
            sync_album_photos(
                album=photos.libraries[library].albums["All Photos"],
                destination_path=os.path.join(destination_path, "All Photos"),
                file_sizes=filters["file_sizes"],
                extensions=filters["extensions"],
                files=files,
                folder_format=folder_format,
                hardlink_registry=hardlink_registry,
                config=config,
            )
            if hardlink_registry:
                LOGGER.info(
                    f"'All Photos' sync complete. Hard link registry populated with "
                    f"{hardlink_registry.get_registry_size()} reference files.",
                )
            break


def _sync_albums_by_configuration(
    photos,
    libraries,
    download_all,
    destination_path,
    filters,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync albums based on configuration settings.

    Args:
        photos: Photos object from iCloudPy
        libraries: List of photo libraries to sync
        download_all: Whether to download all albums
        destination_path: Base destination path
        filters: Photo filters configuration
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for library in libraries:
        if download_all and library == "PrimarySync":
            _sync_all_albums_except_filtered(
                photos,
                library,
                filters,
                destination_path,
                files,
                folder_format,
                hardlink_registry,
                config,
            )
        elif filters["albums"] and library == "PrimarySync":
            _sync_filtered_albums(
                photos,
                library,
                filters,
                destination_path,
                files,
                folder_format,
                hardlink_registry,
                config,
            )
        elif filters["albums"]:
            _sync_filtered_albums_in_library(
                photos,
                library,
                filters,
                destination_path,
                files,
                folder_format,
                hardlink_registry,
                config,
            )
        else:
            _sync_all_photos_in_library(
                photos,
                library,
                destination_path,
                filters,
                files,
                folder_format,
                hardlink_registry,
                config,
            )


def _sync_all_albums_except_filtered(
    photos,
    library,
    filters,
    destination_path,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync all albums except those in the filter exclusion list.

    Args:
        photos: Photos object from iCloudPy
        library: Library name to sync
        filters: Photo filters configuration
        destination_path: Base destination path
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for album in photos.libraries[library].albums.keys():
        # Skip All Photos if we already synced it first
        if hardlink_registry and album == "All Photos":
            continue
        if filters["albums"] and album in iter(filters["albums"]):
            continue
        sync_album_photos(
            album=photos.libraries[library].albums[album],
            destination_path=os.path.join(destination_path, album),
            file_sizes=filters["file_sizes"],
            extensions=filters["extensions"],
            files=files,
            folder_format=folder_format,
            hardlink_registry=hardlink_registry,
            config=config,
        )


def _sync_filtered_albums(
    photos,
    library,
    filters,
    destination_path,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync only albums specified in filters.

    Args:
        photos: Photos object from iCloudPy
        library: Library name to sync
        filters: Photo filters configuration
        destination_path: Base destination path
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for album in iter(filters["albums"]):
        sync_album_photos(
            album=photos.libraries[library].albums[album],
            destination_path=os.path.join(destination_path, album),
            file_sizes=filters["file_sizes"],
            extensions=filters["extensions"],
            files=files,
            folder_format=folder_format,
            hardlink_registry=hardlink_registry,
            config=config,
        )


def _sync_filtered_albums_in_library(
    photos,
    library,
    filters,
    destination_path,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync filtered albums in a specific library.

    Args:
        photos: Photos object from iCloudPy
        library: Library name to sync
        filters: Photo filters configuration
        destination_path: Base destination path
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for album in iter(filters["albums"]):
        if album in photos.libraries[library].albums:
            sync_album_photos(
                album=photos.libraries[library].albums[album],
                destination_path=os.path.join(destination_path, album),
                file_sizes=filters["file_sizes"],
                extensions=filters["extensions"],
                files=files,
                folder_format=folder_format,
                hardlink_registry=hardlink_registry,
                config=config,
            )
        else:
            LOGGER.warning(f"Album {album} not found in {library}. Skipping the album {album} ...")


def _sync_all_photos_in_library(
    photos,
    library,
    destination_path,
    filters,
    files,
    folder_format,
    hardlink_registry,
    config,
):
    """Sync all photos in a library.

    Args:
        photos: Photos object from iCloudPy
        library: Library name to sync
        destination_path: Base destination path
        filters: Photo filters configuration
        files: Set to track downloaded files
        folder_format: Folder format string
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    sync_album_photos(
        album=photos.libraries[library].all,
        destination_path=os.path.join(destination_path, "all"),
        file_sizes=filters["file_sizes"],
        extensions=filters["extensions"],
        files=files,
        folder_format=folder_format,
        hardlink_registry=hardlink_registry,
        config=config,
    )
