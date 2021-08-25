__author__ = "Mandar Patil (mandarons@pm.me)"

import datetime
import os
import re
import time
from pathlib import Path
from shutil import copyfileobj, rmtree

from pyicloud import PyiCloudService, utils, exceptions

from src import config_parser
from src import notify


def wanted_file(filters, file_path, verbose=False):
    if not file_path:
        return False
    if not filters or len(filters) == 0:
        return True
    for file_extension in filters:
        if re.search(f"{file_extension}$", file_path, re.IGNORECASE):
            return True
    if verbose:
        print(f"Skipping the unwanted file {file_path}")
    return False


def wanted_folder(filters, root, folder_path, verbose=False):
    if not filters or not folder_path or not root or len(filters) == 0:
        # Nothing to filter, return True
        return True
        # Something to filter
    folder_path = Path(folder_path)
    for folder in filters:
        child_path = Path(
            os.path.join(
                os.path.abspath(root), folder.removeprefix("/").removesuffix("/")
            )
        )
        if (
            folder_path in child_path.parents
            or child_path in folder_path.parents
            or folder_path == child_path
        ):
            return True
    return False


def wanted_parent_folder(filters, root, folder_path, verbose=False):
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


def process_folder(item, destination_path, filters, root, verbose=False):
    if not (item and destination_path and root):
        return None
    new_directory = os.path.join(destination_path, item.name)
    if not wanted_folder(
        filters=filters, folder_path=new_directory, root=root, verbose=verbose
    ):
        if verbose:
            print(f"Skipping the unwanted folder {new_directory}...")
        return None
    os.makedirs(new_directory, exist_ok=True)
    return new_directory


def file_exists(item, local_file, verbose=False):
    if item and local_file and os.path.isfile(local_file):
        local_file_modified_time = int(os.path.getmtime(local_file))
        remote_file_modified_time = int(item.date_modified.timestamp())
        local_file_size = os.path.getsize(local_file)
        remote_file_size = item.size
        if (
            local_file_modified_time == remote_file_modified_time
            and local_file_size == remote_file_size
        ):
            if verbose:
                print(f"No changes detected. Skipping the file {local_file}")
            return True
    return False


def download_file(item, local_file, verbose=False):
    if not (item and local_file):
        return False
    if verbose:
        print(f"Downloading {local_file} ...")
    try:
        with item.open(stream=True) as response:
            with open(local_file, "wb") as file_out:
                copyfileobj(response.raw, file_out)
        item_modified_time = time.mktime(item.date_modified.timetuple())
        os.utime(local_file, (item_modified_time, item_modified_time))
    except (exceptions.PyiCloudAPIResponseException, FileNotFoundError, Exception) as e:
        print(f"Failed to download {local_file}: {str(e)}")
        return False
    return True


def process_file(item, destination_path, filters, files, verbose=False):
    if not (item and destination_path and files is not None):
        return False
    local_file = os.path.join(destination_path, item.name)
    if not wanted_file(filters=filters, file_path=local_file, verbose=verbose):
        return False
    files.add(local_file)
    if file_exists(item=item, local_file=local_file, verbose=verbose):
        return False
    download_file(item=item, local_file=local_file, verbose=verbose)
    return True


def remove_obsolete(destination_path, files, verbose=False):
    removed_paths = set()
    if not (destination_path and files is not None):
        return removed_paths
    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if local_file not in files:
            if verbose:
                print(f"Removing {local_file}")
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
    remove=False,
    verbose=False,
):
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
                    verbose=verbose,
                )
                if not new_folder:
                    continue
                files.add(new_folder)
                files.update(
                    sync_directory(
                        drive=item,
                        destination_path=new_folder,
                        items=item.dir(),
                        root=root,
                        top=False,
                        filters=filters,
                        verbose=verbose,
                    )
                )
            elif item.type == "file":
                if wanted_parent_folder(
                    filters=filters["folders"]
                    if filters and "folders" in filters
                    else None,
                    root=root,
                    folder_path=destination_path,
                    verbose=verbose,
                ):
                    process_file(
                        item=item,
                        destination_path=destination_path,
                        filters=filters["file_extensions"]
                        if filters and "file_extensions" in filters
                        else None,
                        files=files,
                        verbose=verbose,
                    )
        if top and remove:
            remove_obsolete(
                destination_path=destination_path, files=files, verbose=verbose
            )
    return files


def sync_drive():
    last_send = None
    while True:
        config = config_parser.read_config()
        verbose = config_parser.get_verbose(config=config)
        username = config_parser.get_username(config=config)
        destination_path = config_parser.prepare_drive_destination(config=config)
        if username and destination_path:
            try:
                api = PyiCloudService(
                    apple_id=username,
                    password=utils.get_password_from_keyring(username=username),
                )
                if not api.requires_2sa:
                    sync_directory(
                        drive=api.drive,
                        destination_path=destination_path,
                        root=destination_path,
                        items=api.drive.dir(),
                        top=True,
                        filters=config["filters"] if "filters" in config else None,
                        remove=config_parser.get_drive_remove_obsolete(config=config),
                        verbose=verbose,
                    )
                else:
                    print("Error: 2FA is required. Please log in.")
                    last_send = notify.send(config, last_send)
            except exceptions.PyiCloudNoStoredPasswordAvailableException:

                print(
                    "password is not stored in keyring. Please save the password in keyring."
                )
        sleep_for = config_parser.get_sync_interval(config=config)
        next_sync = (
            datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
        ).strftime("%c")
        print(f"Resyncing at {next_sync} ...")
        if sleep_for < 0:
            break
        time.sleep(sleep_for)
