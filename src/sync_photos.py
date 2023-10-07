"""Sync photos module."""
___author___ = "Mandar Patil <mandarons@pm.me>"
import base64
import os
import shutil
import time
import unicodedata
from pathlib import Path

from icloudpy import exceptions

from src import LOGGER, config_parser


def photo_wanted(photo, extensions):
    """Check if photo is wanted based on extension."""
    if not extensions or len(extensions) == 0:
        return True
    for extension in extensions:
        if photo.filename.lower().endswith(str(extension).lower()):
            return True
    return False


def generate_file_name(photo, file_size, destination_path, folder_format):
    """Generate full path to file."""
    filename = photo.filename
    name, extension = filename.rsplit(".", 1) if "." in filename else [filename, ""]
    file_path = os.path.join(destination_path, filename)
    file_size_path = os.path.join(
        destination_path,
        f'{"__".join([name, file_size])}'
        if extension == ""
        else f'{"__".join([name, file_size])}.{extension}',
    )
    file_size_id_path = os.path.join(
        destination_path,
        f'{"__".join([name, file_size, base64.urlsafe_b64encode(photo.id.encode()).decode()])}'
        if extension == ""
        else f'{"__".join([name, file_size, base64.urlsafe_b64encode(photo.id.encode()).decode()])}.{extension}',
    )

    if folder_format is not None:
        folder = photo.created.strftime(folder_format)
        file_size_id_path = os.path.join(
            destination_path,
            folder,
            f'{"__".join([name, file_size, base64.urlsafe_b64encode(photo.id.encode()).decode()])}'
            if extension == ""
            else f'{"__".join([name, file_size, base64.urlsafe_b64encode(photo.id.encode()).decode()])}.{extension}',
        )
        os.makedirs(os.path.join(destination_path, folder), exist_ok=True)

    file_size_id_path_norm = unicodedata.normalize("NFC", file_size_id_path)

    if os.path.isfile(file_path):
        os.rename(file_path, file_size_id_path)
    if os.path.isfile(file_size_path):
        os.rename(file_size_path, file_size_id_path)
    if os.path.isfile(file_size_id_path):
        os.rename(file_size_id_path, file_size_id_path_norm)
    return file_size_id_path_norm


def photo_exists(photo, file_size, local_path):
    """Check if photo exist locally."""
    if photo and local_path and os.path.isfile(local_path):
        local_size = os.path.getsize(local_path)
        remote_size = int(photo.versions[file_size]["size"])
        if local_size == remote_size:
            LOGGER.debug(f"No changes detected. Skipping the file {local_path} ...")
            return True
        else:
            LOGGER.debug(
                f"Change detected: local_file_size is {local_size} and remote_file_size is {remote_size}."
            )
        return False


def download_photo(photo, file_size, destination_path):
    """Download photo from server."""
    if not (photo and file_size and destination_path):
        return False
    LOGGER.info(f"Downloading {destination_path} ...")
    try:
        download = photo.download(file_size)
        with open(destination_path, "wb") as file_out:
            shutil.copyfileobj(download.raw, file_out)
        local_modified_time = time.mktime(photo.added_date.timetuple())
        os.utime(destination_path, (local_modified_time, local_modified_time))
    except (exceptions.ICloudPyAPIResponseException, FileNotFoundError, Exception) as e:
        LOGGER.error(f"Failed to download {destination_path}: {str(e)}")
        return False
    return True


def process_photo(photo, file_size, destination_path, files, folder_format):
    """Process photo details."""
    photo_path = generate_file_name(
        photo=photo,
        file_size=file_size,
        destination_path=destination_path,
        folder_format=folder_format,
    )
    if file_size not in photo.versions:
        LOGGER.warning(
            f"File size {file_size} not found on server. Skipping the photo {photo_path} ..."
        )
        return False
    if files is not None:
        files.add(photo_path)
    if photo_exists(photo, file_size, photo_path):
        return False
    download_photo(photo, file_size, photo_path)
    return True


def sync_album(
    album, destination_path, file_sizes, extensions=None, files=None, folder_format=None
):
    """Sync given album."""
    if album is None or destination_path is None or file_sizes is None:
        return None
    os.makedirs(unicodedata.normalize("NFC", destination_path), exist_ok=True)
    LOGGER.info(f"Syncing {album.title}")
    for photo in album:
        if photo_wanted(photo, extensions):
            for file_size in file_sizes:
                process_photo(photo, file_size, destination_path, files, folder_format)
        else:
            LOGGER.debug(f"Skipping the unwanted photo {photo.filename}.")
    for subalbum in album.subalbums:
        sync_album(
            album.subalbums[subalbum],
            os.path.join(destination_path, subalbum),
            file_sizes,
            extensions,
            files,
            folder_format,
        )
    return True


def remove_obsolete(destination_path, files):
    """Remove local obsolete file."""
    removed_paths = set()
    if not (destination_path and files is not None):
        return removed_paths
    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if local_file not in files:
            if path.is_file():
                LOGGER.info(f"Removing {local_file} ...")
                path.unlink(missing_ok=True)
                removed_paths.add(local_file)
    return removed_paths


def sync_photos(config, photos):
    """Sync all photos."""
    for l in photos.libraries:
        LOGGER.info(f"Available library: {l}")
    destination_path = config_parser.prepare_photos_destination(config=config)
    filters = config_parser.get_photos_filters(config=config)
    files = set()
    download_all = config_parser.get_photos_all_albums(config=config)
    library = config_parser.get_photos_library(config=config)
    folder_format = config_parser.get_photos_folder_format(config=config)
    if download_all:
        for album in photos.libraries[library].albums.keys():
            if filters["albums"] and album in iter(filters["albums"]):
                continue
            sync_album(
                album=photos.libraries[library].albums[album],
                destination_path=os.path.join(destination_path, album),
                file_sizes=filters["file_sizes"],
                extensions=filters["extensions"],
                files=files,
                folder_format=folder_format,
            )
    elif filters["albums"]:
        for album in iter(filters["albums"]):
            sync_album(
                album=photos.libraries[library].albums[album],
                destination_path=os.path.join(destination_path, album),
                file_sizes=filters["file_sizes"],
                extensions=filters["extensions"],
                files=files,
                folder_format=folder_format,
            )
    else:
        sync_album(
            album=photos.libraries[library].all,
            destination_path=os.path.join(destination_path, "all"),
            file_sizes=filters["file_sizes"],
            extensions=filters["extensions"],
            files=files,
            folder_format=folder_format,
        )

    if config_parser.get_photos_remove_obsolete(config=config):
        remove_obsolete(destination_path, files)


# def enable_debug():
#     import contextlib
#     import http.client
#     import logging
#     import requests
#     import warnings

#     # from pprint import pprint
#     # from icloudpy import ICloudPyService
#     from urllib3.exceptions import InsecureRequestWarning

#     # Handle certificate warnings by ignoring them
#     old_merge_environment_settings = requests.Session.merge_environment_settings

#     @contextlib.contextmanager
#     def no_ssl_verification():
#         opened_adapters = set()

#         def merge_environment_settings(self, url, proxies, stream, verify, cert):
#             # Verification happens only once per connection so we need to close
#             # all the opened adapters once we're done. Otherwise, the effects of
#             # verify=False persist beyond the end of this context manager.
#             opened_adapters.add(self.get_adapter(url))

#             settings = old_merge_environment_settings(
#                 self, url, proxies, stream, verify, cert
#             )
#             settings["verify"] = False

#             return settings

#         requests.Session.merge_environment_settings = merge_environment_settings

#         try:
#             with warnings.catch_warnings():
#                 warnings.simplefilter("ignore", InsecureRequestWarning)
#                 yield
#         finally:
#             requests.Session.merge_environment_settings = old_merge_environment_settings

#             for adapter in opened_adapters:
#                 try:
#                     adapter.close()
#                 except Exception as e:
#                     pass

#     # Monkeypatch the http client for full debugging output
#     httpclient_logger = logging.getLogger("http.client")

#     def httpclient_logging_patch(level=logging.DEBUG):
#         """Enable HTTPConnection debug logging to the logging framework"""

#         def httpclient_log(*args):
#             httpclient_logger.log(level, " ".join(args))

#         # mask the print() built-in in the http.client module to use
#         # logging instead
#         http.client.print = httpclient_log
#         # enable debugging
#         http.client.HTTPConnection.debuglevel = 1

#     # Enable general debug logging
#     logging.basicConfig(filename="log1.txt", encoding="utf-8", level=logging.DEBUG)

#     httpclient_logging_patch()


# if __name__ == "__main__":
#     # enable_debug()
#     sync_photos()
