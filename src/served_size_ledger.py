"""Persisted record of photo renditions kept at a non-declared size.

A complete transfer whose byte count differs from the CloudKit-declared size is
accepted by the download path. Without a durable note, the next sync's
``check_photo_exists`` compares only against the declared size, treats the file
as missing and downloads it again — the loop this issue is about.

Entries pin the version record, variant, declared size and served size. A
change to either size invalidates the exception, so an unrelated file of a
coincidentally matching length is not accepted. The file follows the same
config-directory convention as the web UI's state and survives container
recreations with the mounted volume.
"""

import json
import os
import sys
import threading

from src import get_logger

LOGGER = get_logger()

_FILENAME = ".served-photo-sizes.json"
_LOCK = threading.RLock()
_entries_by_path: dict[str, dict[str, dict]] = {}


def _path() -> str:
    """Resolve the ledger path under the config directory.

    Reads ``DEFAULT_COOKIE_DIRECTORY`` through ``sys.modules`` so the test
    suite's redirect is honoured, matching ``web_signals``.
    """
    cookie_dir = sys.modules["src"].DEFAULT_COOKIE_DIRECTORY
    return os.path.join(os.path.dirname(cookie_dir) or "/config", _FILENAME)


def _key(record_id: str, file_size: str) -> str:
    """Key one rendition by its CloudKit record and version name."""
    return f"{record_id}|{file_size}"


def _entries(path: str) -> dict[str, dict]:
    """Load and cache the ledger stored at ``path``."""
    with _LOCK:
        if path not in _entries_by_path:
            try:
                with open(path) as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = {}
            except (OSError, json.JSONDecodeError) as e:
                LOGGER.warning(f"served_size_ledger: failed to load {path}: {e!s} - treating as empty")
                data = {}
            _entries_by_path[path] = data if isinstance(data, dict) else {}
        return _entries_by_path[path]


def _save(path: str, entries: dict[str, dict]) -> None:
    """Publish ``entries`` atomically, warning instead of failing a sync."""
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        LOGGER.warning(f"served_size_ledger: failed to save {path}: {e!s}")
        try:
            os.unlink(tmp)
        except OSError:
            pass


def record(record_id: str, file_size: str, declared: int, served: int) -> None:
    """Remember that ``served`` bytes were accepted for this rendition."""
    path = _path()
    with _LOCK:
        entries = _entries(path)
        entries[_key(record_id, file_size)] = {"declared": declared, "served": served}
        _save(path, entries)


def matches(record_id: str, file_size: str, declared: int, served: int) -> bool:
    """Whether this exact rendition was accepted at ``served`` bytes."""
    with _LOCK:
        entry = _entries(_path()).get(_key(record_id, file_size))
    return (
        isinstance(entry, dict)
        and entry.get("declared") == declared
        and entry.get("served") == served
    )


def forget(record_id: str, file_size: str) -> None:
    """Drop an entry once the declared size matches what is on disk again."""
    path = _path()
    with _LOCK:
        entries = _entries(path)
        if entries.pop(_key(record_id, file_size), None) is not None:
            _save(path, entries)
