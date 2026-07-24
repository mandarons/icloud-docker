"""Photo file operations module.

This module contains utilities for photo file operations including
downloading, hardlink creation, and file existence checking.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import json
import os
import shutil
import threading
from datetime import timezone
from urllib.parse import urlencode

from src import get_logger

LOGGER = get_logger()

# Module-level lock to protect thread-safe mutation of photo._versions during retries
_versions_refresh_lock = threading.Lock()

# CloudKit fields to request when re-fetching a photo record for fresh download URLs.
# Mirrors the desiredKeys list used by icloudpy's PhotoAlbum._list_query_gen().
_DESIRED_KEYS = [
    "resJPEGFullWidth",
    "resJPEGFullHeight",
    "resJPEGFullFileType",
    "resJPEGFullFingerprint",
    "resJPEGFullRes",
    "resJPEGLargeWidth",
    "resJPEGLargeHeight",
    "resJPEGLargeFileType",
    "resJPEGLargeFingerprint",
    "resJPEGLargeRes",
    "resJPEGMedWidth",
    "resJPEGMedHeight",
    "resJPEGMedFileType",
    "resJPEGMedFingerprint",
    "resJPEGMedRes",
    "resJPEGThumbWidth",
    "resJPEGThumbHeight",
    "resJPEGThumbFileType",
    "resJPEGThumbFingerprint",
    "resJPEGThumbRes",
    "resVidFullWidth",
    "resVidFullHeight",
    "resVidFullFileType",
    "resVidFullFingerprint",
    "resVidFullRes",
    "resVidMedWidth",
    "resVidMedHeight",
    "resVidMedFileType",
    "resVidMedFingerprint",
    "resVidMedRes",
    "resVidSmallWidth",
    "resVidSmallHeight",
    "resVidSmallFileType",
    "resVidSmallFingerprint",
    "resVidSmallRes",
    "resSidecarWidth",
    "resSidecarHeight",
    "resSidecarFileType",
    "resSidecarFingerprint",
    "resSidecarRes",
    "itemType",
    "dataClassType",
    "filenameEnc",
    "originalOrientation",
    "resOriginalWidth",
    "resOriginalHeight",
    "resOriginalFileType",
    "resOriginalFingerprint",
    "resOriginalRes",
    "resOriginalAltWidth",
    "resOriginalAltHeight",
    "resOriginalAltFileType",
    "resOriginalAltFingerprint",
    "resOriginalAltRes",
    "resOriginalVidComplWidth",
    "resOriginalVidComplHeight",
    "resOriginalVidComplFileType",
    "resOriginalVidComplFingerprint",
    "resOriginalVidComplRes",
    "isDeleted",
    "isExpunged",
    "dateExpunged",
    "remappedRef",
    "recordName",
    "recordType",
    "recordChangeTag",
    "masterRef",
    "adjustmentRenderType",
    "assetDate",
    "addedDate",
    "isFavorite",
    "isHidden",
    "orientation",
    "duration",
    "assetSubtype",
    "assetSubtypeV2",
    "assetHDRType",
    "burstFlags",
    "burstFlagsExt",
    "burstId",
    "captionEnc",
    "extendedDescEnc",
    "locationEnc",
    "locationV2Enc",
    "locationLatitude",
    "locationLongitude",
    "adjustmentType",
    "timeZoneOffset",
    "vidComplDurValue",
    "vidComplDurScale",
    "vidComplDispValue",
    "vidComplDispScale",
    "vidComplVisibilityState",
    "customRenderedValue",
    "containerId",
    "itemId",
    "position",
    "isKeyAsset",
    "importedByBundleIdentifierEnc",
    "importedByDisplayNameEnc",
    "importedBy",
]


def _refresh_photo_download_url(photo) -> bool:
    """Re-fetch the photo's master record from iCloud to obtain fresh download URLs.

    iCloud download URLs are signed CDN tokens that expire after ~30–40 minutes.
    When a URL expires (HTTP 410 Gone), clearing ``photo._versions`` alone is
    insufficient because icloudpy re-parses the same stale ``_master_record``
    which still contains the expired URL.  This function makes a new
    ``records/query`` API call to get an updated master record with fresh URLs,
    then updates ``photo._master_record`` in place and clears ``_versions`` so
    the next ``download()`` call uses the fresh URL.

    Args:
        photo: PhotoAsset object from icloudpy

    Returns:
        True if the master record was successfully refreshed, False otherwise.
    """
    try:
        record_name = photo._master_record["recordName"]  # noqa: SLF001
        record_type = photo._master_record.get("recordType", "CPLMaster")  # noqa: SLF001
    except (AttributeError, KeyError, TypeError):
        LOGGER.debug("Cannot refresh download URL: photo missing _master_record or recordName")
        return False

    service = getattr(photo, "_service", None)
    if service is None:
        LOGGER.debug("Cannot refresh download URL: photo missing _service")
        return False

    endpoint = getattr(service, "_service_endpoint", None)
    session = getattr(service, "session", None)
    params = getattr(service, "params", None)
    zone_id = getattr(service, "zone_id", None)

    if not all([endpoint, session, params, zone_id]):
        LOGGER.debug("Cannot refresh download URL: photo._service missing required attributes")
        return False

    try:
        url = f"{endpoint}/records/query?{urlencode(params)}"
        query = {
            "query": {
                "recordType": record_type,
                "filterBy": [
                    {
                        "fieldName": "recordName",
                        "comparator": "IN",
                        "fieldValue": {
                            "type": "STRING_LIST",
                            "value": [record_name],
                        },
                    },
                ],
            },
            "resultsLimit": 1,
            "desiredKeys": _DESIRED_KEYS,
            "zoneID": zone_id,
        }
        request = session.post(
            url,
            data=json.dumps(query),
            headers={"Content-type": "text/plain"},
        )
        response = request.json()
        records = response.get("records", [])

        for rec in records:
            if rec.get("recordName") == record_name:
                photo._master_record = rec  # noqa: SLF001
                with _versions_refresh_lock:
                    photo._versions = None  # noqa: SLF001
                LOGGER.debug(f"Refreshed download URL for {record_name}")
                return True

        LOGGER.debug(f"Record {record_name} not found in iCloud response during URL refresh")
        return False

    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"Failed to refresh download URL for {record_name}: {e!s}")
        return False


def check_photo_exists(photo, file_size: str, local_path: str) -> bool:
    """Check if photo exists locally with correct size.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        local_path: Local file path to check

    Returns:
        True if photo exists locally with correct size, False otherwise
    """
    if not (photo and local_path and os.path.isfile(local_path)):
        return False

    local_size = os.path.getsize(local_path)
    remote_size = int(photo.versions[file_size]["size"])

    if local_size == remote_size:
        LOGGER.debug(f"No changes detected. Skipping the file {local_path} ...")
        return True
    else:
        LOGGER.debug(f"Change detected: local_file_size is {local_size} and remote_file_size is {remote_size}.")
        return False


def create_hardlink(source_path: str, destination_path: str) -> bool:
    """Create a hard link from source to destination.

    Args:
        source_path: Path to existing file to link from
        destination_path: Path where hardlink should be created

    Returns:
        True if hardlink was created successfully, False otherwise
    """
    try:
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        # Create hard link
        os.link(source_path, destination_path)
        LOGGER.info(f"Created hard link: {destination_path} (linked to existing file: {source_path})")
        return True
    except (OSError, FileNotFoundError) as e:
        LOGGER.warning(f"Failed to create hard link {destination_path}: {e!s}")
        return False


def download_photo_from_server(photo, file_size: str, destination_path: str, max_retries: int = 1) -> bool:
    """Download photo from iCloud server to local path.

    This function implements automatic retry logic for HTTP 410 (Gone) errors,
    which occur when iCloud download URLs expire. When a 410 error is detected,
    the function re-fetches the photo's master record from iCloud to obtain
    fresh download URLs, then retries the download.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        destination_path: Local path where photo should be saved
        max_retries: Maximum number of retries on 410 errors (default: 1)

    Returns:
        True if download was successful, False otherwise
    """
    if not (photo and file_size and destination_path):
        return False

    LOGGER.info(f"Downloading {destination_path} ...")

    max_retries = max(0, max_retries)  # Clamp to minimum 0 for predictable behavior
    attempt = 0
    max_attempts = max_retries + 1  # Initial attempt + retries

    while attempt < max_attempts:  # noqa: PERF203
        try:
            download = photo.download(file_size)
            with open(destination_path, "wb") as file_out:
                shutil.copyfileobj(download.raw, file_out)

            # Set file modification time to photo's added date.
            # iCloudPy returns added_date as an aware UTC datetime; replace() is a
            # safe no-op here because tzinfo is already UTC. If it ever returns a
            # naive datetime, replace(tzinfo=utc) correctly treats it as UTC.
            local_modified_time = photo.added_date.replace(tzinfo=timezone.utc).timestamp()
            os.utime(destination_path, (local_modified_time, local_modified_time))

            return True

        except Exception as e:  # noqa: PERF203
            # Enhanced error logging with file path context
            # This catches all exceptions including iCloudPy errors like ObjectNotFoundException
            error_msg = str(e)

            # Check for HTTP 410 Gone error - download URL has expired
            # The iCloudPy library raises exceptions with "Gone (410)" in the message
            # when the download URL has expired (typically after 30-40 minutes)
            if "Gone (410)" in error_msg:
                attempt += 1
                if attempt < max_attempts:
                    LOGGER.warning(
                        f"Download URL expired (410) for {destination_path}. "
                        f"Refreshing URL and retrying (attempt {attempt}/{max_attempts})...",
                    )
                    # Re-fetch the master record from iCloud to obtain fresh download URLs.
                    # Simply clearing _versions is insufficient because icloudpy re-parses
                    # the same stale _master_record which still contains the expired URL.
                    _refresh_photo_download_url(photo)
                    continue
                else:
                    LOGGER.error(
                        f"Failed to download {destination_path} after {max_retries} retries: {error_msg}",
                    )
                    return False

            # Handle other errors
            if "ObjectNotFoundException" in error_msg or "NOT_FOUND" in error_msg:
                LOGGER.error(f"Photo not found in iCloud Photos - {destination_path}: {error_msg}")
            else:
                LOGGER.error(f"Failed to download {destination_path}: {error_msg}")
            return False

    # This line should never be reached due to the logic above, but is kept as defensive programming
    return False  # pragma: no cover


def rename_legacy_file_if_exists(old_path: str, new_path: str) -> None:
    """Rename legacy file format to new format if it exists.

    Args:
        old_path: Path to legacy file format
        new_path: Path to new file format
    """
    if os.path.isfile(old_path):
        os.rename(old_path, new_path)
