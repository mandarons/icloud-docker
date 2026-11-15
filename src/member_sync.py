"""Back up household members' photo libraries.

One daemon thread, beside the primary account's sync loop, for every
account under ``accounts:``. For each member with a pinned Apple ID and a
saved session (both written by the sign-in pages, ``src.member_signin``):

1. Resume the saved session. Session-only: no password is ever stored or
   sent, so a session Apple no longer accepts marks the member "needs
   sign-in" and nothing is retried until they sign in again.
2. If the member adopts another tool's tree (``photos.adopt``) and nobody
   has started their backup yet, write the read-only report
   (``src.member_report``) for the household page and stop there.
3. Otherwise run an ordinary photo pass with the member's config
   (``accounts.member_config``), then their Drive when it is on, its
   state in the member's own file.

The primary's loop is untouched: its handlers can sleep for half an hour
on a sign-in problem, and none of that reaches here, nor the other way
round. A member's crash is logged and recorded on their card; the thread
carries on with the next member and the next cycle.
"""

import logging
import os
import threading
import time
from typing import Any

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    ENV_CONFIG_FILE_PATH_KEY,
    accounts,
    config_parser,
    get_logger,
    read_config,
    web_signals,
)

LOGGER = get_logger()

# A pass is at most this often, even when the photo interval is shorter or
# negative (one-shot): members are not worth a busy loop.
_MIN_INTERVAL = 300
_DEFAULT_INTERVAL = 3600

_WAKE = threading.Event()
_THREAD: threading.Thread | None = None


def wake() -> None:
    """Run the member passes now (sign-in finished, backup started, Sync now)."""
    _WAKE.set()


class _AccountPrefix(logging.Filter):
    """Prefix ``[id]`` to lines logged during a member's pass."""

    def filter(self, record: logging.LogRecord) -> bool:
        account_id = web_signals.ACCOUNT.get()
        if account_id and not getattr(record, "_account_prefixed", False):
            record.msg = f"[{account_id}] {record.msg}"
            record._account_prefixed = True  # noqa: SLF001 - one prefix across handlers
        return True


def _install_log_prefix() -> None:
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, _AccountPrefix) for f in handler.filters):
            handler.addFilter(_AccountPrefix())


def _load_config() -> dict | None:
    path = os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)
    if not os.path.isfile(path):
        return None
    try:
        return read_config(config_path=path)
    except Exception as e:  # noqa: BLE001 - a broken edit waits for the next cycle
        LOGGER.warning(f"Member sync: could not read the config: {e!s}")
        return None


def _interval(config: dict | None) -> int:
    if not config or "photos" not in config:
        return _DEFAULT_INTERVAL
    try:
        seconds = int(config_parser.get_photos_sync_interval(config=config, log_messages=False))
    except Exception:  # noqa: BLE001
        return _DEFAULT_INTERVAL
    return max(seconds, _MIN_INTERVAL) if seconds > 0 else _DEFAULT_INTERVAL


# Status changes the operator should hear about, because only they can act:
# the report waits for "Start backup", a lost sign-in waits for a new link.
_ANNOUNCE = {
    "review": "{id}'s backup check is done: {download} photos to download. Review it and start the backup: {url}",
    "needs_sign_in": "{id}'s iCloud sign-in has run out. Send them a new link: {url}",
}


def _status(status: str, detail: str | None = None, **fields: Any) -> None:
    previous = web_signals.get_member().get("status")
    web_signals.record_member(status=status, detail=detail, status_at=time.time(), **fields)
    template = _ANNOUNCE.get(status)
    # A member who has never signed in is not news; one whose sign-in ran
    # out after working is.
    if template is None or previous == status or (status == "needs_sign_in" and previous is None):
        return
    _announce(template, fields)


def _announce(template: str, fields: dict) -> None:
    from src import notify

    account_id = web_signals.ACCOUNT.get()
    config = _load_config()
    if not config:
        return
    base = (config_parser.get_web_ui_public_url(config=config) or "").rstrip("/")
    report = fields.get("report") or {}
    message = template.format(
        id=account_id,
        download=f"{report.get('download', 0):,}",
        url=(f"{base}/household/{account_id}" if base else "the dashboard's Household card"),
    )
    try:
        notify.send_household(config, message)
    except Exception as e:  # noqa: BLE001 - the card still shows it
        LOGGER.warning(f"Member sync: could not send the notification: {e!s}")


def _resume(account: accounts.Account, member: dict):
    """The member's iCloud client from their saved session, or None.

    Records why on the member's card when it cannot be had.
    """
    from icloudpy import exceptions

    from src.sync import get_api_instance

    try:
        api = get_api_instance(
            username=account.username,
            password=None,
            cookie_directory=accounts.cookie_directory(account.id),
            server_region=config_parser.get_region(config=member),
        )
    except exceptions.ICloudPyNoStoredPasswordAvailableException:
        LOGGER.info("Member sync: the saved session is no longer accepted; waiting for a new sign-in")
        _status(
            "needs_sign_in",
            "Apple no longer accepts the saved sign-in. Send a new link.",
        )
        return None
    except Exception as e:  # noqa: BLE001 - an outage; try again next cycle
        LOGGER.warning(f"Member sync: could not reach iCloud: {e!s}")
        _status("error", f"Couldn't reach iCloud: {e!s}")
        return None
    if getattr(api, "requires_2fa", False):
        _status("needs_sign_in", "Apple wants the 6-digit code again. Send a new link.")
        return None
    return api


def _mount_ok(member: dict) -> bool:
    from src.sync import _check_mount_marker

    destination = config_parser.prepare_photos_destination(config=member)
    return _check_mount_marker(
        destinations=[destination],
        marker_filename=config_parser.get_mount_marker_filename(config=member),
        required=config_parser.get_photos_require_mount_marker(config=member),
        service_name="Photos",
    )


def _report(api, member: dict) -> None:
    from src import member_report

    _status("checking", "Comparing iCloud with the photos already in the folder.")
    report = member_report.build(api.photos, member)
    _status("review", None, report=report)


def _drive_mounted(config: dict, member: dict) -> bool:
    """Whether the Drive volume is there, checked before anything is created.

    The member's own marker counts, and so does the main account's: their
    folders sit side by side on the same volume. Creating the member's
    folder first would, with the volume missing, write into the container.
    """
    if not config_parser.get_drive_require_mount_marker(config=member):
        return True
    marker = config_parser.get_mount_marker_filename(config=member)
    folders = [accounts.drive_folder(member), accounts.drive_folder(config)]
    return any(folder and os.path.isfile(os.path.join(folder, marker)) for folder in folders)


def _drive_pass(api, config: dict, member: dict) -> str | None:
    """Back up the member's Drive; a sentence for their card when it can't."""
    from src import sync_drive
    from src.sync import _list_local_files

    if not _drive_mounted(config, member):
        LOGGER.warning("Member sync: Drive skipped, its folder's .mounted marker is missing")
        return "Drive is paused: its folder isn't mounted."
    destination = config_parser.prepare_drive_destination(config=member)
    before = _list_local_files(destination) or set()
    web_signals.record_service_running("drive", running=True)
    started = time.time()
    try:
        sync_drive.sync_drive(config=member, drive=api.drive)
    except Exception as e:  # noqa: BLE001 - photos still count; Drive tries again next cycle
        LOGGER.exception("Member sync: the Drive pass failed")
        return f"Drive's last pass failed: {e!s}"
    finally:
        web_signals.record_service_running("drive", running=False)
    after = _list_local_files(destination) or set()
    web_signals.record_sync_completion(
        "drive",
        files_downloaded=len(after - before),
        files_skipped=len(before & after),
        files_removed=len(before - after) if config_parser.get_drive_remove_obsolete(config=member) else None,
        duration_seconds=time.time() - started,
    )
    return None


def _pass(api, config: dict, member: dict, adopt: str | None, drive_problem: str | None = None) -> None:
    from src import photo_adopt, sync_photos

    _status("syncing")
    web_signals.record_service_running("photos", running=True)
    adopter = photo_adopt.Adopter(adopt) if adopt else None
    token = photo_adopt.ADOPTER.set(adopter)
    started = time.time()
    try:
        result = sync_photos.sync_photos(config=member, photos=api.photos)
    finally:
        photo_adopt.ADOPTER.reset(token)
        web_signals.record_service_running("photos", running=False)
    downloaded, failed = result if isinstance(result, tuple) else (0, 0)
    web_signals.record_sync_completion(
        "photos",
        files_downloaded=downloaded,
        errors=failed,
        duration_seconds=time.time() - started,
    )
    detail = _drive_pass(api, config, member) if "drive" in member else drive_problem
    _status("ok", detail, adopted=adopter.adopted if adopter else None)


def _shared_owners(members: list[accounts.Account]) -> dict[str, str]:
    """Each Shared Library someone already backs up: zone name -> account id.

    The main account is ``""``. Read from each account's own library
    states, the main account first, so a library stays with whoever has
    been backing it up.
    """
    owners = {name: "" for name in web_signals.get_library_states() if name.startswith("SharedSync-")}
    for account in members:
        with web_signals.as_account(account.id):
            for name in web_signals.get_library_states():
                if name.startswith("SharedSync-"):
                    owners.setdefault(name, account.id)
    return owners


def _with_own_shared_library(
    api,
    config: dict,
    member: dict,
    account: accounts.Account,
    owners: dict[str, str],
    others: list[str],
) -> dict:
    """Add the Shared Library this member owns, unless another account backs it up.

    Only a library's owner lists it among their own libraries, so this is
    the member's own. Each library goes to exactly one account, which
    ``owners`` tracks across the cycle.
    """
    try:
        zones = [name for name in api.photos.libraries if str(name).startswith("SharedSync-")]
    except Exception as e:  # noqa: BLE001 - the personal library still syncs
        LOGGER.warning(f"Member sync: could not list {account.id}'s libraries: {e!s}")
        return member
    shared = None
    for zone in zones:
        owner = owners.setdefault(zone, account.id)
        if owner != account.id:
            LOGGER.info(
                f"Member sync: {account.id}'s Shared Library is already backed up by {owner or 'the main account'}.",
            )
            continue
        folder = accounts.shared_zone_folder(config, zone, account.id)
        problem = accounts.folder_conflict(config, member, others, folder=accounts.photos_path(member, folder))
        if problem:
            LOGGER.warning(f"Member sync: not backing up {account.id}'s Shared Library: {problem}")
            continue
        photos = member["photos"]
        photos["filters"]["libraries"].append(zone)
        photos["library_destinations"][zone] = folder
        shared = folder
    web_signals.record_member(shared_library=shared)
    return member


def run_member(
    config: dict,
    account: accounts.Account,
    others: list[str],
    other_drives: list[str] = (),
    owners: dict[str, str] | None = None,
) -> None:
    """One cycle for one member, inside their state and log context."""
    member = accounts.member_config(config, account)
    with web_signals.as_account(account.id):
        if "photos" not in config:
            _status(
                "blocked",
                "Photos isn't set up for the main account, so there is nothing to share.",
            )
            return
        conflict = accounts.folder_conflict(config, member, others)
        if conflict:
            LOGGER.error(f"Member sync: not syncing {account.id}: {conflict}")
            _status("blocked", f"Not syncing: {conflict}.")
            return
        drive_problem = accounts.drive_conflict(config, member, other_drives)
        if drive_problem:
            # Photos carry on; only Drive waits for a safe folder.
            LOGGER.warning(f"Member sync: {account.id}: {drive_problem}")
            member.pop("drive", None)
        if not account.username or not accounts.session_saved(account.id):
            _status("needs_sign_in", "Waiting for the first sign-in.")
            return
        api = _resume(account, member)
        if api is None:
            return
        if not _mount_ok(member):
            _status("blocked", "The photos folder's .mounted marker is missing.")
            return
        adopt = config_parser.get_photos_adopt(config=member)
        state = web_signals.get_member()
        if adopt and not state.get("approved"):
            if not state.get("report"):
                _report(api, member)
            return
        member = _with_own_shared_library(api, config, member, account, {} if owners is None else owners, others)
        _pass(api, config, member, adopt, drive_problem)


def run_once(config: dict | None) -> None:
    """One cycle over every member. A member's failure stays theirs."""
    if not config:
        return
    members = accounts.get_accounts(config)
    configs = {a.id: accounts.member_config(config, a) for a in members}
    folders = {i: accounts.member_folder(c) for i, c in configs.items()}
    drives = {i: accounts.drive_folder(c) for i, c in configs.items()}
    owners = _shared_owners(members)
    for account in members:
        others = [folder for other, folder in folders.items() if other != account.id]
        other_drives = [folder for other, folder in drives.items() if other != account.id and folder]
        try:
            run_member(config, account, others, other_drives, owners)
        except Exception as e:  # noqa: BLE001 - one member must not stop the others
            LOGGER.exception(f"Member sync: {account.id} failed")
            with web_signals.as_account(account.id):
                _status("error", f"The last pass failed: {e!s}")


def _loop() -> None:  # pragma: no cover - the forever loop; run_once is tested
    _install_log_prefix()
    while True:
        config = _load_config()
        run_once(config)
        _WAKE.wait(timeout=_interval(config))
        _WAKE.clear()


def start_in_thread() -> threading.Thread:
    """Start the member thread once; later calls return the same thread."""
    global _THREAD
    if _THREAD is None or not _THREAD.is_alive():
        _THREAD = threading.Thread(target=_loop, name="member-sync", daemon=True)
        _THREAD.start()
    return _THREAD
