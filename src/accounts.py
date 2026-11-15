"""Household accounts: Apple IDs beyond the main one.

Configured as a list under ``accounts:``::

    accounts:
      - id: alex                          # username optional

Without a username the member types their Apple ID on the sign-in
page, and the first successful sign-in pins it to the account
(``<config dir>/accounts/<id>/account.json``). Each account keeps its own
saved session in ``<config dir>/accounts/<id>/session_data``, written by
the sign-in pages (``src.member_signin``) and resumed by the member sync
(``src.member_sync``).

What a member backs up (``member_config``): their personal photo library,
into ``<photos destination>/<id>``, and their iCloud Drive, into a folder
beside the main account's (``drive/Eric`` -> ``drive/<id>``), never inside
it, where the main account's cleanup would delete what it does not
recognise. Not the Shared Library: the primary already backs it up.
Obsolete-file cleanup is off unless the entry turns it on. Drive is on
whenever the main account syncs Drive, unless the entry says
``drive: false`` (the member's own page has a switch). An entry may change
a few settings::

    accounts:
      - id: alex
        photos:
          library_destinations: {PrimarySync: Alex}
          folder_format: "%Y/%m/%d"
          all_folder: ""           # dated folders straight under Alex/
          adopt: icloudpd          # recognise an icloudpd tree in place
        drive:
          enabled: true
          destination: drive/Alex  # default: beside the main account's
          remove_obsolete: true
"""

import copy
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass

from src import DEFAULT_DRIVE_DESTINATION, config_parser, get_logger

LOGGER = get_logger()

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class Account:
    """One household member's Apple ID."""

    id: str
    username: str | None = None
    name: str | None = None

    @property
    def label(self) -> str:
        """What pages call this person: the entry's ``name``, else the id in title case."""
        return self.name or self.id.replace("_", " ").title()


def config_dir() -> str:
    """The container's config folder, read at call time like ``web_signals``."""
    return os.environ.get("ICLOUD_DOCKER_CONFIG_DIR", "/config")


def get_accounts(config: dict | None) -> list[Account]:
    """Valid entries of ``accounts:``, in config order.

    An entry is skipped, with a warning, when its id isn't a short
    lowercase slug, repeats an earlier id, has no username, or names the
    main Apple ID (that account already has its session).
    """
    raw = (config or {}).get("accounts") or []
    if not isinstance(raw, list):
        LOGGER.warning("accounts: must be a list; ignoring it")
        return []
    if not raw:
        # A single-account config never reads anything else here.
        return []
    main = (config_parser.get_username(config=config) or "").lower()
    accounts: list[Account] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            LOGGER.warning(f"accounts[{index}]: expected id and username; skipping")
            continue
        account_id = str(entry.get("id") or "").strip()
        username = str(entry.get("username") or "").strip()
        if not _ID_PATTERN.match(account_id):
            LOGGER.warning(f"accounts[{index}]: id must be lowercase letters, digits, - or _; skipping")
            continue
        if account_id in seen:
            LOGGER.warning(f"accounts[{index}]: id {account_id} is used twice; skipping the second")
            continue
        username = username or pinned_username(account_id) or ""
        if username and "@" not in username:
            LOGGER.warning(f"accounts[{index}] ({account_id}): username must be an Apple ID; skipping")
            continue
        if username and username.lower() == main:
            LOGGER.warning(f"accounts[{index}] ({account_id}): that is the main Apple ID; skipping")
            continue
        seen.add(account_id)
        name = str(entry.get("name") or "").strip()[:40] or None
        accounts.append(Account(id=account_id, username=username or None, name=name))
    return accounts


def get_account(config: dict | None, account_id: str) -> Account | None:
    """The configured account with this id, or None."""
    return next((a for a in get_accounts(config) if a.id == account_id), None)


def account_directory(account_id: str) -> str:
    """Everything kept for one account: its pinned Apple ID and session."""
    return os.path.join(config_dir(), "accounts", account_id)


def cookie_directory(account_id: str) -> str:
    """Where this account's saved session lives."""
    return os.path.join(account_directory(account_id), "session_data")


def _pin_path(account_id: str) -> str:
    return os.path.join(account_directory(account_id), "account.json")


def pinned_username(account_id: str) -> str | None:
    """The Apple ID the account's first sign-in used, if any."""
    try:
        with open(_pin_path(account_id), encoding="utf-8") as f:
            value = json.load(f).get("username")
    except OSError, ValueError, AttributeError:
        return None
    return value if isinstance(value, str) and value else None


def pin_username(account_id: str, username: str) -> None:
    """Remember which Apple ID this account is, so later links reuse it."""
    os.makedirs(account_directory(account_id), mode=0o700, exist_ok=True)
    temp = _pin_path(account_id) + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump({"username": username}, f)
    os.replace(temp, _pin_path(account_id))


def forget(account_id: str) -> None:
    """Drop the account's pinned Apple ID and saved session.

    The next sign-in asks for an Apple ID again. Photos already
    backed up are not touched; they live under the backup folders.
    """
    shutil.rmtree(account_directory(account_id), ignore_errors=True)


def session_saved(account_id: str) -> bool:
    """True when a sign-in has left a session for this account.

    Says nothing about whether Apple still accepts it; only a sign-in can.
    """
    directory = cookie_directory(account_id)
    try:
        return any(entry.is_file() for entry in os.scandir(directory))
    except OSError:
        return False


# Photo settings a member entry may change. The rest are shared with the
# primary, and some of them (file name style, sizes) are process-wide
# switches that two passes running at once must agree on.
MEMBER_PHOTO_KEYS = frozenset(
    {
        "library_destinations",
        "folder_format",
        "folder_timezone",
        "all_folder",
        "adopt",
        "remove_obsolete",
        "obsolete_delete_limit_percent",
        "sync_interval",
    },
)


# Drive settings a member entry may change. Filters and the ignore list
# are not inherited either: they name the main account's own folders.
MEMBER_DRIVE_KEYS = frozenset({"enabled", "destination", "remove_obsolete", "sync_interval"})


def _entry(config: dict | None, account_id: str) -> dict:
    for entry in (config or {}).get("accounts") or []:
        if isinstance(entry, dict) and str(entry.get("id") or "").strip() == account_id:
            return entry
    return {}


def member_config(config: dict, account: Account) -> dict:
    """The config a member's passes run with.

    The shared config with the member's Apple ID; the personal library,
    into ``<photos destination>/<id>`` (``member_sync`` adds a Shared
    Library the member owns), cleanup off, then the entry's
    allowed photo settings on top; Drive as ``member_drive`` says. A plain
    dict every ``config_parser`` getter accepts.
    """
    effective = copy.deepcopy(config)
    drive = member_drive(config, account)
    if drive is None:
        effective.pop("drive", None)
    else:
        effective["drive"] = drive
    effective.pop("accounts", None)
    app = effective.setdefault("app", {})
    credentials = app.get("credentials")
    app["credentials"] = dict(credentials) if isinstance(credentials, dict) else {}
    app["credentials"]["username"] = account.username
    photos = effective.get("photos")
    photos = dict(photos) if isinstance(photos, dict) else {}
    filters = photos.get("filters")
    filters = dict(filters) if isinstance(filters, dict) else {}
    filters["libraries"] = ["PrimarySync"]
    filters.pop("albums", None)
    photos["filters"] = filters
    photos["all_albums"] = False
    photos["library_destinations"] = {"PrimarySync": account.id}
    photos["remove_obsolete"] = False
    overrides = _entry(config, account.id).get("photos")
    for key, value in (overrides if isinstance(overrides, dict) else {}).items():
        if key in MEMBER_PHOTO_KEYS:
            photos[key] = copy.deepcopy(value)
        else:
            LOGGER.warning(f"accounts ({account.id}): photos.{key} is shared with the main account; ignoring it")
    effective["photos"] = photos
    return effective


def _drive_entry(config: dict | None, account_id: str) -> dict:
    value = _entry(config, account_id).get("drive")
    if value is False:
        return {"enabled": False}
    return value if isinstance(value, dict) else {}


def drive_enabled(config: dict | None, account: Account) -> bool:
    """Whether this member's Drive is backed up: on unless switched off."""
    if not isinstance((config or {}).get("drive"), dict):
        return False
    return _drive_entry(config, account.id).get("enabled", True) is not False


def _primary_drive_destination(config: dict) -> str:
    return str((config.get("drive") or {}).get("destination") or DEFAULT_DRIVE_DESTINATION).strip("/")


def member_drive(config: dict, account: Account) -> dict | None:
    """A member's ``drive:`` section, or None when their Drive is off.

    The main account's section without its filters and ignore list, into
    a folder beside the main account's, cleanup off, then the entry's
    allowed Drive settings on top.
    """
    if not drive_enabled(config, account):
        return None
    drive = {k: copy.deepcopy(v) for k, v in config["drive"].items() if k not in ("filters", "ignore")}
    primary = _primary_drive_destination(config)
    parent = os.path.dirname(primary)
    # Beside the main account's folder when it has a parent to share;
    # otherwise inside it, which ``folder_conflict`` then refuses.
    drive["destination"] = os.path.join(parent or primary, account.id)
    drive["remove_obsolete"] = False
    for key, value in _drive_entry(config, account.id).items():
        if key in MEMBER_DRIVE_KEYS:
            if key != "enabled":
                drive[key] = copy.deepcopy(value)
        else:
            LOGGER.warning(f"accounts ({account.id}): drive.{key} is shared with the main account; ignoring it")
    return drive


def _is_shared(library: str) -> bool:
    return library == "SharedLibrary" or library.startswith("SharedSync-")


def shared_library_folder(config: dict | None) -> str | None:
    """Where the main account's backup keeps the Shared Library, or None.

    Members skip the Shared Library (``member_config``): everyone in it
    sees the same photos, and the main account already backs them up. The
    household page says where. None when the main account doesn't sync
    it either. A trailing zone name (``SharedSync-<id>``) is left off.
    """
    photos = (config or {}).get("photos")
    if not isinstance(photos, dict):
        return None
    filters = photos.get("filters") if isinstance(photos.get("filters"), dict) else {}
    libraries = filters.get("libraries")
    if isinstance(libraries, list) and not any(_is_shared(str(name)) for name in libraries):
        return None
    destination = str(photos.get("destination") or "photos").strip("/")
    mapping = photos.get("library_destinations") if isinstance(photos.get("library_destinations"), dict) else {}
    subdir = next((str(folder) for name, folder in mapping.items() if _is_shared(str(name))), "")
    subdir = subdir.strip("/")
    if os.path.basename(subdir).startswith("SharedSync-"):
        subdir = os.path.dirname(subdir)
    return f"{destination}/{subdir}" if subdir else destination


def shared_zone_folder(config: dict, zone: str, account_id: str) -> str:
    """Where a Shared Library a member owns lands, under the photos destination.

    Only its owner lists a Shared Library among their own libraries;
    everyone else in it sees it as shared with them. So the member who owns
    one is the only account that can back it up, and it is downloaded once.
    It sits beside the main account's Shared Library, in a folder named for
    the library itself, so two libraries never share or nest a folder.
    """
    photos = config.get("photos") if isinstance(config.get("photos"), dict) else {}
    mapping = photos.get("library_destinations") if isinstance(photos.get("library_destinations"), dict) else {}
    subdir = next((str(folder) for name, folder in mapping.items() if _is_shared(str(name))), None)
    if subdir is None:
        return os.path.join("Shared", zone)
    subdir = subdir.strip("/")
    if os.path.basename(subdir).startswith("SharedSync-"):
        return os.path.join(os.path.dirname(subdir), zone)
    return f"{subdir or 'Shared'}-{account_id}"


def photos_path(config: dict, subdir: str) -> str:
    """``subdir`` of an account's photos destination, as a full path."""
    return _clean(os.path.join(_photos_base(config), subdir))


def _photos_base(config: dict) -> str:
    photos = config.get("photos") if isinstance(config.get("photos"), dict) else {}
    root = str((config.get("app") or {}).get("root") or "")
    return os.path.join(root, str(photos.get("destination") or "photos"))


def _clean(path: str) -> str:
    return unicodedata.normalize("NFC", os.path.normpath(path))


def _nested(a: str, b: str) -> bool:
    return a == b or a.startswith(b + os.sep) or b.startswith(a + os.sep)


def member_folder(member: dict) -> str:
    """Where a member's personal library lands (from ``member_config``)."""
    mapping = (member.get("photos") or {}).get("library_destinations") or {}
    return _clean(os.path.join(_photos_base(member), str(mapping.get("PrimarySync", ""))))


def _root(config: dict) -> str:
    return str((config.get("app") or {}).get("root") or "")


def drive_folder(config: dict) -> str | None:
    """Where an account's Drive lands, from its (member or main) config."""
    if not isinstance(config.get("drive"), dict):
        return None
    return _clean(os.path.join(_root(config), _primary_drive_destination(config)))


def cleanup_roots(config: dict) -> list[str]:
    """Folders the main account's photo cleanup walks, or could walk.

    With ``library_destinations`` each mapped library cleans only its own
    folder (an unmapped one is never cleaned); without, one walk covers the
    whole destination.
    """
    base = _photos_base(config)
    photos = config.get("photos") if isinstance(config.get("photos"), dict) else {}
    mapping = photos.get("library_destinations")
    if not isinstance(mapping, dict) or not mapping:
        return [_clean(base)]
    return [_clean(os.path.join(base, str(folder))) for folder in mapping.values()]


def drive_conflict(config: dict, member: dict, other_drives: list[str] = ()) -> str | None:
    """Why a member's Drive folder is unsafe, or None (also when Drive is off).

    The same rule as photos: never where another account's cleanup walks.
    The main account's Drive at the root of the Drive volume leaves no
    folder beside it, so the entry has to name one.
    """
    drive = drive_folder(member)
    if drive is None:
        return None
    main_drive = drive_folder(config)
    if main_drive is not None and _nested(drive, main_drive):
        return "Drive is off: its folder would sit inside the main account's. Set drive.destination on its entry."
    for other in other_drives:
        if _nested(drive, other):
            return "Drive is off: its folder overlaps another member's."
    return None


def folder_conflict(
    config: dict,
    member: dict,
    others: list[str] = (),
    folder: str | None = None,
) -> str | None:
    """Why a member's photo folder (or ``folder``, another of theirs) is unsafe, or None.

    A member's photos must never sit where another account's cleanup walks:
    that cleanup does not know them and would delete them. Pure path
    arithmetic, nothing is listed.
    """
    folder = folder or member_folder(member)
    base = _clean(_photos_base(config))
    if folder == base:
        return "its folder is the whole photos destination"
    for root in cleanup_roots(config):
        if _nested(folder, root):
            return f"its folder overlaps the main account's {os.path.relpath(root, base)}"
    for other in others:
        if _nested(folder, other):
            return f"its folder overlaps another member's {os.path.relpath(other, base)}"
    return None
