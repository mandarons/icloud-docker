import time
import os
import shutil
from src import config_parser, LOGGER
from icloudpy import exceptions


def generate_file_name(photo, file_size, destination_path):
    filename = photo.filename
    if file_size != "original":
        tokens = photo.filename.rsplit(".", 1)
        tokens.insert(len(tokens) - 1, file_size)
        filename = "__".join(tokens[:-1]) + "." + tokens[-1]
    else:
        tokens = photo.filename.rsplit(".", 1)
        tokens.insert(len(tokens) - 1, file_size)
        original_filename = "__".join(tokens[:-1]) + "." + tokens[-1]
        original_file_path = os.path.join(destination_path, original_filename)
        if os.path.isfile(original_file_path):
            os.rename(original_file_path, os.path.join(destination_path, filename))
    return os.path.abspath(os.path.join(destination_path, filename))


def photo_exists(photo, file_size, local_path):
    if photo and local_path and os.path.isfile(local_path):
        local_size = os.path.getsize(local_path)
        remote_size = int(photo.versions[file_size]["size"])
        if local_size == remote_size:
            LOGGER.info("No changes detected. Skipping the file %s", local_path)
            return True
        return False


def download_photo(photo, file_size, destination_path):
    if not (photo and file_size and destination_path):
        return False
    LOGGER.info("Downloading %s ...", destination_path)
    try:
        download = photo.download(file_size)
        with open(destination_path, "wb") as file_out:
            shutil.copyfileobj(download.raw, file_out)
        local_modified_time = time.mktime(photo.added_date.timetuple())
        os.utime(destination_path, (local_modified_time, local_modified_time))
    except (exceptions.ICloudPyAPIResponseException, FileNotFoundError, Exception) as e:
        LOGGER.error("Failed to download %s: %s", destination_path, str(e))
        return False
    return True


def process_photo(photo, file_size, destination_path):
    photo_path = generate_file_name(
        photo=photo, file_size=file_size, destination_path=destination_path
    )
    if file_size not in photo.versions:
        LOGGER.warning(
            "File size %s not found on server. Skipping the photo %s ...",
            file_size,
            photo_path,
        )
        return False
    if photo_exists(photo, file_size, photo_path):
        return False
    download_photo(photo, file_size, photo_path)
    return True


def sync_album(album, destination_path, file_sizes):
    if not (album and destination_path and file_sizes):
        return None
    os.makedirs(destination_path, exist_ok=True)
    for photo in album:
        for file_size in file_sizes:
            process_photo(photo, file_size, destination_path)


def sync_photos(config, photos):
    destination_path = config_parser.prepare_photos_destination(config=config)
    filters = config_parser.get_photos_filters(config=config)
    if filters["albums"]:
        for album in iter(filters["albums"]):
            sync_album(
                album=photos.albums[album],
                destination_path=os.path.join(destination_path, album),
                file_sizes=filters["file_sizes"],
            )
    else:
        sync_album(
            album=photos.all,
            destination_path=os.path.join(destination_path, "all"),
            file_sizes=filters["file_sizes"],
        )


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
