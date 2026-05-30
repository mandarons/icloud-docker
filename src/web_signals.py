"""Cross-thread signalling for the embedded web UI.

The web UI (``src.web``) runs in a daemon thread alongside the sync
loop (``src.sync``). Two things need to flow between them:

1. **Force-sync sentinels** — when the user taps "Sync now" on the
   dashboard, the web thread touches ``$CONFIG_DIR/.force-sync-<svc>``
   and the sync loop deletes the sentinel + zeroes the countdown on
   its next iteration.

2. **Last-sync state** — after each per-service sync run, the sync
   loop writes a small JSON file the dashboard reads on every
   refresh (last completion time, file counts, error count).

Files are chosen over a shared module-level singleton so the same
mechanism keeps working if a future refactor splits sync + web into
two processes. They live in ``ICLOUD_DOCKER_CONFIG_DIR`` (default
``/config``) — same place the keyring and session cookies live, so
they're persisted across container recreations.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import json
import os
import time
from typing import Any

from src import DEFAULT_COOKIE_DIRECTORY, get_logger

LOGGER = get_logger()


def _config_dir() -> str:
    """Resolve the directory force-sync sentinels + state JSON live in.

    Mirrors the ICLOUD_DOCKER_CONFIG_DIR / DEFAULT_COOKIE_DIRECTORY
    setup: same logic the keyring redirect uses, so dev hosts without
    ``/config`` still work via a tempdir.
    """
    # DEFAULT_COOKIE_DIRECTORY is "<config_dir>/session_data"; strip the
    # trailing component to recover the config dir.
    return os.path.dirname(DEFAULT_COOKIE_DIRECTORY) or "/config"


_VALID_SERVICES = ("drive", "photos")


def _sentinel_path(service: str) -> str:
    return os.path.join(_config_dir(), f".force-sync-{service}")


def _state_path() -> str:
    return os.path.join(_config_dir(), ".last-sync-state.json")


def request_force_sync(service: str) -> bool:
    """Touch the sentinel for ``service``.

    Returns True on success, False on validation/IO failure. Idempotent —
    re-tapping while a previous request is still queued is a no-op.
    """
    if service not in _VALID_SERVICES:
        return False
    path = _sentinel_path(service)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(str(time.time()))
        return True
    except OSError as e:
        LOGGER.warning(f"web_signals: failed to write {path}: {e!s}")
        return False


def pending_force_syncs() -> list[str]:
    """Return services currently queued for an immediate sync.

    Used by the dashboard to render "Queued ✓" instead of "Sync now".
    """
    return [
        service
        for service in _VALID_SERVICES
        if os.path.isfile(_sentinel_path(service))
    ]


def consume_force_sync(service: str) -> bool:
    """Atomically check + delete the sentinel. Sync loop calls this on
    each iteration; True means "user requested an immediate run."

    ``os.unlink`` raises ``FileNotFoundError`` if another caller beat us
    to it — treated as "no request" rather than an error.
    """
    if service not in _VALID_SERVICES:
        return False
    try:
        os.unlink(_sentinel_path(service))
        return True
    except FileNotFoundError:
        return False
    except OSError as e:
        LOGGER.warning(f"web_signals: failed to consume {service} sentinel: {e!s}")
        return False


def record_sync_completion(
    service: str,
    *,
    files_downloaded: int | None = None,
    files_skipped: int | None = None,
    files_removed: int | None = None,
    errors: int | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Persist per-service stats after a sync run completes.

    All counters are optional — passing ``None`` leaves the previous
    value alone. Writes atomically (temp + rename) so a partial write
    can't corrupt the file.
    """
    if service not in _VALID_SERVICES:
        return
    state = _load_state()
    entry = state.get(service, {})
    entry["completed_at"] = time.time()
    if files_downloaded is not None:
        entry["files_downloaded"] = int(files_downloaded)
    if files_skipped is not None:
        entry["files_skipped"] = int(files_skipped)
    if files_removed is not None:
        entry["files_removed"] = int(files_removed)
    if errors is not None:
        entry["errors"] = int(errors)
    if duration_seconds is not None:
        entry["duration_seconds"] = float(duration_seconds)
    state[service] = entry
    _save_state(state)


def get_sync_state(service: str) -> dict[str, Any]:
    """Return the persisted last-sync state for ``service``.

    Empty dict on missing/corrupt file — the dashboard renders absence
    gracefully.
    """
    if service not in _VALID_SERVICES:
        return {}
    return _load_state().get(service, {})


def _load_state() -> dict[str, dict[str, Any]]:
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError) as e:
        LOGGER.warning(f"web_signals: failed to load {path}: {e!s} — treating as empty")
    return {}


def _save_state(state: dict[str, dict[str, Any]]) -> None:
    path = _state_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.rename(tmp, path)
    except OSError as e:
        LOGGER.warning(f"web_signals: failed to save {path}: {e!s}")
        try:
            os.unlink(tmp)
        except OSError:
            pass


def format_relative_time(epoch_seconds: float, *, now: float | None = None) -> str:
    """Human-friendly relative time for dashboard display.

    "Just now" / "5 min ago" / "2 h ago" / "3 d ago". Avoids
    "1 hour ago" pluralisation gymnastics by sticking to compact
    unit suffixes.
    """
    if not epoch_seconds:
        return ""
    if now is None:
        now = time.time()
    delta = max(0, now - epoch_seconds)
    if delta < 30:
        return "Just now"
    if delta < 120:
        return f"{int(delta)} sec ago"
    if delta < 3600:
        return f"{int(delta // 60)} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    return f"{int(delta // 86400)} d ago"
