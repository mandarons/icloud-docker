"""Sync drive module."""
__author__ = "Mandar Patil (mandarons@pm.me)"

import gzip
import os
import re
import time
from pathspec import PathSpec
from pathlib import Path
from shutil import copyfileobj, rmtree, unpack_archive

import magic
from icloudpy import exceptions

from src import LOGGER, config_parser


def wanted_file(filters, ignore, file_path):
    """Check if file is wanted."""
    if not file_path:
        return False
    if ignore:
        if PathSpec.from_lines("gitwildmatch", ignore).match_file(file_path):
            LOGGER.debug(f"Skipping the unwanted file {file_path}")
            return False
    if not filters or len(filters) == 0:
        return True
    for file_extension in filters:
        if re.search(f"{file_extension}$", file_path, re.IGNORECASE):
            return True
    LOGGER.debug(f"Skipping the unwanted file {file_path}")
    return False


def wanted_folder(filters, root, folder_path):
    """Check if folder is wanted."""
    if not filters or not folder_path or not root or len(filters) == 0:
        # Nothing to filter, return True
        return True
        # Something to filter
    folder_path = Path(folder_path)
    for folder in filters:
        child_path = Path(
            os.path.join(
                os.path.abspath(root), str(folder).removeprefix("/").removesuffix("/")
            )
        )
        if (
            folder_path in child_path.parents
            or child_path in folder_path.parents
            or folder_path == child_path
        ):
            return True
    return False


def wanted_parent_folder(filters, root, folder_path):
    """Check if parent folder is wanted."""
    if not filters or not folder_path or not root or len(filters) == 0:
        return True
    folder_path = Path(folder_path)
    for folder in filters:
        child_path = Path(
            os.path.join(
                os.path.abspath(root), folder.removeprefix("/").removesuffix("/")
            )
        )
        if child_path in folder_path.parents or folder_path == child_path:
            return True
    return False


def process_folder(item, destination_path, filters, root):
    """Process the given folder."""
    if not (item and destination_path and root):
        return None
    new_directory = os.path.join(destination_path, item.name)
    if not wanted_folder(filters=filters, folder_path=new_directory, root=root):
        LOGGER.debug(f"Skipping the unwanted folder {new_directory} ...")
        return None
    os.makedirs(new_directory, exist_ok=True)
    return new_directory


def package_exists(item, local_package_path):
    """Check for package existence."""
    if item and local_package_path and os.path.isdir(local_package_path):
        local_package_modified_time = int(os.path.getmtime(local_package_path))
        remote_package_modified_time = int(item.date_modified.timestamp())
        local_package_size = sum(
            f.stat().st_size
            for f in Path(local_package_path).glob("**/*")
            if f.is_file()
        )
        remote_package_size = item.size
        if (
            local_package_modified_time == remote_package_modified_time
            and local_package_size == remote_package_size
        ):
            LOGGER.debug(
                f"No changes detected. Skipping the package {local_package_path} ..."
            )
            return True
        else:
            LOGGER.info(
                f"Changes detected: local_modified_time is {local_package_modified_time}, "
                + f"remote_modified_time is {remote_package_modified_time}, "
                + f"local_package_size is {local_package_size} and remote_package_size is {remote_package_size}."
            )
            rmtree(local_package_path)
    else:
        LOGGER.debug(f"Package {local_package_path} does not exist locally.")
    return False


def file_exists(item, local_file):
    """Check for file existence locally."""
    if item and local_file and os.path.isfile(local_file):
        local_file_modified_time = int(os.path.getmtime(local_file))
        remote_file_modified_time = int(item.date_modified.timestamp())
        local_file_size = os.path.getsize(local_file)
        remote_file_size = item.size
        if local_file_modified_time == remote_file_modified_time and (
            local_file_size == remote_file_size
            or (local_file_size == 0 and remote_file_size is None)
            or (local_file_size is None and remote_file_size == 0)
        ):
            LOGGER.debug(f"No changes detected. Skipping the file {local_file} ...")
            return True
        else:
            LOGGER.debug(
                f"Changes detected: local_modified_time is {local_file_modified_time}, "
                + f"remote_modified_time is {remote_file_modified_time}, "
                + f"local_file_size is {local_file_size} and remote_file_size is {remote_file_size}."
            )
    else:
        LOGGER.debug(f"File {local_file} does not exist locally.")
    return False


def process_package(local_file):
    """Process the package."""
    archive_file = local_file
    magic_object = magic.Magic(mime=True)
    if "application/zip" == magic_object.from_file(filename=local_file):
        archive_file += ".zip"
        os.rename(local_file, archive_file)
        LOGGER.info(f"Unpacking {archive_file} to {os.path.dirname(archive_file)}")
        unpack_archive(filename=archive_file, extract_dir=os.path.dirname(archive_file))
        os.remove(archive_file)
    elif "application/gzip" == magic_object.from_file(filename=local_file):
        archive_file += ".gz"
        os.rename(local_file, archive_file)
        LOGGER.info(f"Unpacking {archive_file} to {os.path.dirname(local_file)}")
        with gzip.GzipFile(filename=archive_file, mode="rb") as gz_file:
            with open(file=local_file, mode="wb") as package_file:
                copyfileobj(gz_file, package_file)
        os.remove(archive_file)
        process_package(local_file=local_file)
    else:
        LOGGER.error(
            f"Unhandled file type - cannot unpack the package {magic_object.from_file(filename=archive_file)}."
        )
        return False
    LOGGER.info(f"Successfully unpacked the package {archive_file}.")
    return True


def is_package(item):
    """Determine if item is a package."""
    file_is_a_package = False
    with item.open(stream=True) as response:
        file_is_a_package = response.url and "/packageDownload?" in response.url
    return file_is_a_package


def download_file(item, local_file):
    """Download file from server."""
    if not (item and local_file):
        return False
    LOGGER.info(f"Downloading {local_file} ...")
    try:
        with item.open(stream=True) as response:
            with open(local_file, "wb") as file_out:
                copyfileobj(response.raw, file_out)
            if response.url and "/packageDownload?" in response.url:
                process_package(local_file=local_file)
        item_modified_time = time.mktime(item.date_modified.timetuple())
        os.utime(local_file, (item_modified_time, item_modified_time))
    except (exceptions.ICloudPyAPIResponseException, FileNotFoundError, Exception) as e:
        LOGGER.error(f"Failed to download {local_file}: {str(e)}")
        return False
    return True


def process_file(item, destination_path, filters, ignore, files):
    """Process given item as file."""
    if not (item and destination_path and files is not None):
        return False
    local_file = os.path.join(destination_path, item.name)
    if not wanted_file(filters=filters, ignore=ignore, file_path=local_file):
        return False
    files.add(local_file)
    item_is_package = is_package(item=item)
    if item_is_package:
        if package_exists(item=item, local_package_path=local_file):
            for f in Path(local_file).glob("**/*"):
                files.add(str(f))
            return False
    elif file_exists(item=item, local_file=local_file):
        return False
    download_file(item=item, local_file=local_file)
    if item_is_package:
        for f in Path(local_file).glob("**/*"):
            files.add(str(f))
    return True


def remove_obsolete(destination_path, files):
    """Remove local obsolete file."""
    removed_paths = set()
    if not (destination_path and files is not None):
        return removed_paths
    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if local_file not in files:
            LOGGER.info(f"Removing {local_file} ...")
            if path.is_file():
                path.unlink(missing_ok=True)
                removed_paths.add(local_file)
            elif path.is_dir():
                rmtree(local_file)
                removed_paths.add(local_file)
    return removed_paths


def sync_directory(
    drive,
    destination_path,
    items,
    root,
    top=True,
    filters=None,
    ignore=None,
    remove=False,
):
    """Sync folder."""
    files = set()
    if drive and destination_path and items and root:
        for i in items:
            item = drive[i]
            if item.type in ("folder", "app_library"):
                new_folder = process_folder(
                    item=item,
                    destination_path=destination_path,
                    filters=filters["folders"]
                    if filters and "folders" in filters
                    else None,
                    root=root,
                )
                if not new_folder:
                    continue
                try:
                    files.add(new_folder)
                    files.update(
                        sync_directory(
                            drive=item,
                            destination_path=new_folder,
                            items=item.dir(),
                            root=root,
                            top=False,
                            filters=filters,
                        )
                    )
                except Exception:
                    # Continue execution to next item, without crashing the app
                    pass
            elif item.type == "file":
                if wanted_parent_folder(
                    filters=filters["folders"]
                    if filters and "folders" in filters
                    else None,
                    root=root,
                    folder_path=destination_path,
                ):
                    try:
                        process_file(
                            item=item,
                            destination_path=destination_path,
                            filters=filters["file_extensions"]
                            if filters and "file_extensions" in filters
                            else None,
                            ignore=ignore,
                            files=files,
                        )
                    except Exception:
                        # Continue execution to next item, without crashing the app
                        pass
        if top and remove:
            remove_obsolete(destination_path=destination_path, files=files)
    return files


def sync_drive(config, drive):
    """Sync drive."""
    destination_path = config_parser.prepare_drive_destination(config=config)
    return sync_directory(
        drive=drive,
        destination_path=destination_path,
        root=destination_path,
        items=drive.dir(),
        top=True,
        filters=config["drive"]["filters"]
        if "drive" in config and "filters" in config["drive"]
        else None,
        ignore=config["drive"]["ignore"]
        if "drive" in config and "ignore" in config["drive"]
        else None,
        remove=config_parser.get_drive_remove_obsolete(config=config),
    )
