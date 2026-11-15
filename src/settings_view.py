"""What this container is configured to do, for the web UI's Settings page.

Each row names a config.yaml key, the value in effect, and where it came
from: the file, the built-in default, or an environment variable. Secrets
are reported as set or not set, never shown.

A few keys can be changed from the page. Only keys whose change cannot
delete, move or re-download anything are editable; the rest say to edit
config.yaml. A write keeps the file's comments (ruamel round trip), backs
the file up first and replaces it atomically. The sync loop re-reads the
config every cycle, so a change applies from the next one.
"""

import datetime
import glob
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any

from ruamel.yaml import YAML

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_DRIVE_DESTINATION,
    DEFAULT_ENUMERATION_CHUNK_SIZE,
    DEFAULT_LOGGER_LEVEL,
    DEFAULT_OBSOLETE_DELETE_LIMIT_PERCENT,
    DEFAULT_PHOTOS_DESTINATION,
    DEFAULT_REQUEST_TIMEOUT_SEC,
    DEFAULT_RETRY_LOGIN_INTERVAL_SEC,
    DEFAULT_ROOT_DESTINATION,
    DEFAULT_SYNC_INTERVAL_SEC,
    ENV_CONFIG_FILE_PATH_KEY,
    ENV_ICLOUD_PASSWORD_KEY,
    read_config,
)

_MISSING = object()


@dataclass(frozen=True)
class Setting:
    """One config.yaml key as the Settings page shows it.

    ``kind`` is ``text``, ``int``, ``bool``, ``list``, ``map`` or
    ``secret``. ``editable`` keys accept a new value from the page.
    """

    group: str
    path: tuple[str, ...]
    label: str
    default: Any = None
    kind: str = "text"
    editable: bool = False
    note: str = ""
    unit: str = ""

    @property
    def key(self) -> str:
        return ".".join(self.path)


# Editable keys are limited to ones whose change cannot delete, move or
# re-download a file. Intervals, notification switches and hardlinks
# (turning it off only stops new links) qualify. Destinations, formats,
# filters and remove_obsolete do not: each of those changes which files
# belong where, so a slip from a phone would cost a re-download or a
# cleanup.
SETTINGS: tuple[Setting, ...] = (
    Setting("Account", ("app", "credentials", "username"), "Apple ID"),
    Setting("Account", ("app", "region"), "Region", "global"),
    Setting(
        "Account",
        ("app", "credentials", "retry_login_interval"),
        "Sign-in retry",
        DEFAULT_RETRY_LOGIN_INTERVAL_SEC,
        "int",
        unit="s",
    ),
    Setting(
        "Account",
        ("app", "trust_expiry_warn_days"),
        "Warn before trust expires (days)",
        7,
        "int",
    ),
    Setting(
        "Account",
        ("app", "trust_refresh_days"),
        "Refresh trust at (days left)",
        14,
        "int",
    ),
    Setting("App", ("app", "root"), "Root folder", DEFAULT_ROOT_DESTINATION),
    Setting("App", ("app", "max_threads"), "Download threads", "auto"),
    Setting("App", ("app", "mount_marker_filename"), "Mount marker file", ".mounted"),
    Setting("App", ("app", "logger", "level"), "Log level", DEFAULT_LOGGER_LEVEL),
    Setting("App", ("app", "logger", "filename"), "Log file"),
    Setting("App", ("app", "recycle_bin", "enabled"), "Recycle bin", False, "bool"),
    Setting(
        "App",
        ("app", "recycle_bin", "retention_days"),
        "Recycle bin keeps (days)",
        None,
        "int",
    ),
    Setting("App", ("app", "web_ui", "host"), "Web UI host", "127.0.0.1"),
    Setting("App", ("app", "web_ui", "port"), "Web UI port", 8080, "int"),
    Setting("App", ("app", "web_ui", "public_url"), "Web UI public URL"),
    Setting("App", ("app", "usage_tracking", "enabled"), "Usage tracking", True, "bool"),
    Setting("iCloud Drive", ("drive", "destination"), "Folder", DEFAULT_DRIVE_DESTINATION),
    Setting(
        "iCloud Drive",
        ("drive", "sync_interval"),
        "Back up every",
        DEFAULT_SYNC_INTERVAL_SEC,
        "int",
        editable=True,
        note="In seconds. Negative runs once and stops.",
        unit="s",
    ),
    Setting(
        "iCloud Drive",
        ("drive", "remove_obsolete"),
        "Delete files removed from iCloud",
        False,
        "bool",
    ),
    Setting(
        "iCloud Drive",
        ("drive", "flatten_packages"),
        "Keep packages as one file",
        False,
        "bool",
    ),
    Setting(
        "iCloud Drive",
        ("drive", "require_mount_marker"),
        "Require mount marker",
        False,
        "bool",
    ),
    Setting(
        "iCloud Drive",
        ("drive", "request_timeout"),
        "Request timeout",
        DEFAULT_REQUEST_TIMEOUT_SEC,
        "int",
        unit="s",
    ),
    Setting("iCloud Drive", ("drive", "filters", "folders"), "Only these folders", None, "list"),
    Setting(
        "iCloud Drive",
        ("drive", "filters", "file_extensions"),
        "Only these extensions",
        None,
        "list",
    ),
    Setting("iCloud Drive", ("drive", "ignore"), "Ignore", None, "list"),
    Setting("Photos", ("photos", "destination"), "Folder", DEFAULT_PHOTOS_DESTINATION),
    Setting(
        "Photos",
        ("photos", "sync_interval"),
        "Back up every",
        DEFAULT_SYNC_INTERVAL_SEC,
        "int",
        editable=True,
        note="In seconds. Negative runs once and stops.",
        unit="s",
    ),
    Setting(
        "Photos",
        ("photos", "remove_obsolete"),
        "Delete photos removed from iCloud",
        False,
        "bool",
    ),
    Setting(
        "Photos",
        ("photos", "obsolete_delete_limit_percent"),
        "Cleanup limit (%)",
        DEFAULT_OBSOLETE_DELETE_LIMIT_PERCENT,
        "int",
    ),
    Setting("Photos", ("photos", "all_albums"), "Albums as folders", False, "bool"),
    Setting(
        "Photos",
        ("photos", "use_hardlinks"),
        "Hardlink duplicates",
        False,
        "bool",
        editable=True,
        note="Turning it off only stops new links.",
    ),
    Setting("Photos", ("photos", "folder_format"), "Folder format"),
    Setting("Photos", ("photos", "filename_format"), "Filename format", "metadata"),
    Setting("Photos", ("photos", "file_format"), "File format template"),
    Setting("Photos", ("photos", "variant_separator"), "Variant separator", "_"),
    Setting(
        "Photos",
        ("photos", "preserve_originals_as_bak"),
        "Keep originals as .bak",
        False,
        "bool",
    ),
    Setting(
        "Photos",
        ("photos", "require_mount_marker"),
        "Require mount marker",
        False,
        "bool",
    ),
    Setting(
        "Photos",
        ("photos", "request_timeout"),
        "Request timeout",
        DEFAULT_REQUEST_TIMEOUT_SEC,
        "int",
        unit="s",
    ),
    Setting(
        "Photos",
        ("photos", "enumeration_chunk_size"),
        "Enumeration chunk",
        DEFAULT_ENUMERATION_CHUNK_SIZE,
        "int",
    ),
    Setting("Photos", ("photos", "library_destinations"), "Library folders", None, "map"),
    Setting(
        "Photos",
        ("photos", "filters", "libraries"),
        "Only these libraries",
        None,
        "list",
    ),
    Setting("Photos", ("photos", "filters", "albums"), "Albums filter", None, "list"),
    Setting("Photos", ("photos", "filters", "file_sizes"), "Versions", ["original"], "list"),
    Setting(
        "Photos",
        ("photos", "filters", "extensions"),
        "Only these extensions",
        None,
        "list",
    ),
    Setting(
        "Photos",
        ("photos", "filters", "fallback_to_original"),
        "Fall back to original",
        False,
        "bool",
    ),
    Setting(
        "Notifications",
        ("app", "notifications", "sync_summary", "enabled"),
        "Sync summary",
        False,
        "bool",
        editable=True,
    ),
    Setting(
        "Notifications",
        ("app", "notifications", "sync_summary", "on_success"),
        "Summary on success",
        True,
        "bool",
        editable=True,
    ),
    Setting(
        "Notifications",
        ("app", "notifications", "sync_summary", "on_error"),
        "Summary on error",
        True,
        "bool",
        editable=True,
    ),
    Setting(
        "Notifications",
        ("app", "notifications", "sync_summary", "min_downloads"),
        "Summary needs downloads",
        1,
        "int",
        editable=True,
    ),
    Setting(
        "Notifications",
        ("app", "telegram", "bot_token"),
        "Telegram bot",
        None,
        "secret",
    ),
    Setting("Notifications", ("app", "telegram", "chat_id"), "Telegram chat", None, "secret"),
    Setting(
        "Notifications",
        ("app", "telegram", "listen"),
        "Telegram 2FA replies",
        False,
        "bool",
    ),
    Setting("Notifications", ("app", "discord", "webhook_url"), "Discord", None, "secret"),
    Setting("Notifications", ("app", "pushover", "api_token"), "Pushover", None, "secret"),
    Setting("Notifications", ("app", "smtp", "email"), "Email from", None, "secret"),
    Setting("Notifications", ("app", "smtp", "to"), "Email to", None, "secret"),
    Setting("Notifications", ("app", "smtp", "password"), "Email password", None, "secret"),
    Setting("Notifications", ("app", "webhooks", "url"), "Webhook", None, "secret"),
    Setting("Notifications", ("app", "webhooks", "start"), "Ping on start", None, "secret"),
    Setting(
        "Notifications",
        ("app", "webhooks", "success"),
        "Ping on success",
        None,
        "secret",
    ),
    Setting(
        "Notifications",
        ("app", "webhooks", "failure"),
        "Ping on failure",
        None,
        "secret",
    ),
)

SETTINGS_BY_KEY = {setting.key: setting for setting in SETTINGS}

# Shown up front; everything else waits under Advanced.
COMMON = frozenset(
    {
        "photos.destination",
        "photos.sync_interval",
        "photos.remove_obsolete",
        "drive.destination",
        "drive.sync_interval",
        "drive.remove_obsolete",
        "app.notifications.sync_summary.enabled",
        "app.recycle_bin.enabled",
    },
)

# Where alerts can go, by the key that turns each one on.
_ALERT_CHANNELS = (
    ("app.telegram.bot_token", "Telegram"),
    ("app.discord.webhook_url", "Discord"),
    ("app.pushover.api_token", "Pushover"),
    ("app.smtp.email", "Email"),
    ("app.webhooks.url", "Webhook"),
)

# Variables the container reads. Values are shown except for the password,
# which is only reported as set.
ENVIRONMENT = (
    (ENV_ICLOUD_PASSWORD_KEY, "Apple ID password", True),
    (ENV_CONFIG_FILE_PATH_KEY, "Config file", False),
    ("ICLOUD_DOCKER_CONFIG_DIR", "Config folder", False),
    ("PUID", "File owner (user id)", False),
    ("PGID", "File owner (group id)", False),
    ("TZ", "Time zone", False),
    ("APP_VERSION", "Version", False),
)


def lookup(config: dict | None, path: tuple[str, ...]) -> Any:
    """The value at ``path``, or ``_MISSING`` when any part is absent.

    A key present with an empty value (``telegram:`` with nothing under
    it) counts as absent: the app treats it as unset.
    """
    node: Any = config
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return _MISSING if node is None else node


def _is_set(raw: Any) -> bool:
    return raw is not _MISSING and bool(str(raw).strip())


def _duration(seconds: int) -> str:
    """``3600`` -> ``1 h``, ``500`` -> ``8 min 20 s``: an interval as a person says it."""
    if seconds < 0:
        return "Once"
    if seconds >= 86400 and seconds % 86400 == 0:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''}"
    parts = []
    for size, unit in ((3600, "h"), (60, "min"), (1, "s")):
        if seconds >= size:
            parts.append(f"{seconds // size} {unit}")
            seconds %= size
    return " ".join(parts) or "0 s"


def _display(setting: Setting, value: Any) -> str:
    if setting.unit == "s" and isinstance(value, int) and not isinstance(value, bool):
        return _duration(value)
    if setting.kind == "bool":
        return "on" if value else "off"
    if setting.kind == "list":
        if isinstance(value, str):
            return value
        return ", ".join(str(v) for v in value) if value else "none"
    if setting.kind == "map":
        return ", ".join(f"{k} → {v}" for k, v in value.items()) if value else "none"
    return "" if value is None else str(value)


def build_rows(config: dict | None) -> list[dict[str, Any]]:
    """One row per setting, grouped in ``SETTINGS`` order."""
    rows = []
    for setting in SETTINGS:
        raw = lookup(config, setting.path)
        from_file = raw is not _MISSING
        value = raw if from_file else setting.default
        row = {
            "group": setting.group,
            "key": setting.key,
            "label": setting.label,
            "kind": setting.kind,
            "editable": setting.editable,
            "note": setting.note,
            "source": "config.yaml" if from_file else "default",
            "value": value,
            "common": setting.key in COMMON,
        }
        if setting.kind == "secret":
            row["display"] = "set" if _is_set(raw) else "not set"
            row["value"] = None
        else:
            row["display"] = _display(setting, value) if value is not None else "not set"
        rows.append(row)
    if os.environ.get(ENV_ICLOUD_PASSWORD_KEY):
        rows.insert(
            1,
            {
                "group": "Account",
                "key": "password",
                "label": "Password",
                "kind": "secret",
                "editable": False,
                "note": "",
                "source": "env",
                "value": None,
                "display": "set",
                "common": False,
            },
        )
    channels = [name for key, name in _ALERT_CHANNELS if _is_set(lookup(config, tuple(key.split("."))))]
    rows.append(
        {
            "group": "Notifications",
            "key": "",
            "label": "Alerts",
            "kind": "text",
            "editable": False,
            "note": "Set up in config.yaml: "
            + ", ".join(
                f"{name} under {key.rsplit('.', 1)[0]}{' (on)' if name in channels else ''}"
                for key, name in _ALERT_CHANNELS
            )
            + ".",
            "source": "config.yaml" if channels else "default",
            "value": None,
            "display": ", ".join(channels) or "None set",
            "common": True,
        },
    )
    return rows


def build_environment() -> list[dict[str, Any]]:
    """The environment variables the container reads, and their values."""
    rows = []
    for name, label, secret in ENVIRONMENT:
        value = os.environ.get(name)
        if name == ENV_CONFIG_FILE_PATH_KEY and not value:
            display, source = DEFAULT_CONFIG_FILE_PATH, "default"
        elif value is None or value == "":
            display, source = "not set", "default"
        else:
            display, source = ("set" if secret else value), "env"
        rows.append({"name": name, "label": label, "display": display, "source": source})
    return rows


class SettingError(ValueError):
    """A submitted value the page refuses, with a message for the user."""


def parse_value(setting: Setting, submitted: str) -> Any:
    """Turn a form value into what config.yaml should hold."""
    text = (submitted or "").strip()
    if setting.kind == "bool":
        if text in ("on", "true", "1"):
            return True
        if text in ("off", "false", "0", ""):
            return False
        msg = f"{setting.label}: expected on or off"
        raise SettingError(msg)
    if setting.kind == "int":
        try:
            number = int(text)
        except ValueError as e:
            msg = f"{setting.label}: expected a whole number"
            raise SettingError(msg) from e
        if setting.path[-1] == "sync_interval" and number == 0:
            msg = f"{setting.label}: 0 is not allowed; use a negative number to run once"
            raise SettingError(msg)
        if setting.path[-1] == "min_downloads" and number < 0:
            msg = f"{setting.label}: must be 0 or more"
            raise SettingError(msg)
        return number
    msg = f"{setting.label} can't be changed here"
    raise SettingError(msg)


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    return yaml


def _load_document(config_path: str) -> tuple[YAML, Any]:
    yaml = _yaml()
    with open(config_path, encoding="utf-8") as f:
        document = yaml.load(f)
    if document is None:
        msg = "config.yaml is empty"
        raise SettingError(msg)
    return yaml, document


_KEEP_BACKUPS = 5
_BACKUP_STAMP = re.compile(r"\.bak-\d{8}-\d{6}(?:-\d{6})?$")


def _prune_backups(config_path: str) -> None:
    """Keep the newest ``_KEEP_BACKUPS`` backups this page wrote. A backup
    someone made by hand has a different name and is never touched."""
    backups = sorted(p for p in glob.glob(f"{glob.escape(config_path)}.bak-*") if _BACKUP_STAMP.search(p))
    for old in backups[:-_KEEP_BACKUPS]:
        os.unlink(old)


def _save_document(config_path: str, yaml: YAML, document: Any) -> None:
    """Back up config.yaml, then replace it atomically with ``document``.

    The new file is read back with the app's own reader before it replaces
    the old one, so a write that would break the config never lands.
    """
    directory = os.path.dirname(os.path.abspath(config_path))
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    shutil.copy2(config_path, f"{config_path}.bak-{stamp}")
    _prune_backups(config_path)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(document, f)
        read_config(config_path=temp_path)
        shutil.copymode(config_path, temp_path)
        os.replace(temp_path, config_path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def write_setting(config_path: str, key: str, submitted: str) -> Any:
    """Set one editable key in config.yaml; return the value written.

    Keeps the file's comments and writes ``<config>.bak-<timestamp>``
    first, keeping the newest five; see ``_save_document``.
    """
    setting = SETTINGS_BY_KEY.get(key)
    if setting is None or not setting.editable:
        msg = "That setting can't be changed here; edit config.yaml"
        raise SettingError(msg)
    value = parse_value(setting, submitted)
    yaml, document = _load_document(config_path)

    node = document
    for part in setting.path[:-1]:
        child = node.get(part)
        if child is None:
            child = {}
            node[part] = child
            child = node[part]
        if not isinstance(child, dict):
            msg = f"{'.'.join(setting.path)}: {part} is not a section in config.yaml"
            raise SettingError(msg)
        node = child
    if node.get(setting.path[-1]) == value and isinstance(node.get(setting.path[-1]), type(value)):
        return value
    node[setting.path[-1]] = value
    _save_document(config_path, yaml, document)
    return value
