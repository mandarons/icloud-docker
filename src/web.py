"""Web UI for icloud-docker.

Goal — give the user a single page they can hit from any device to:
  1) (primary) authenticate / re-authenticate Apple ID + 2FA;
  2) (secondary) confirm config paths, mount markers, and last-sync status;
  3) (tertiary) tail the recent log lines.

The web server runs in a daemon thread spawned from ``main.py`` alongside
the existing ``sync.sync()`` loop. The two share state through the
filesystem (keyring, session cookies, log file). No new persistence layer.

Designed for **LAN- or proxy-trusted** exposure. There is no built-in
login on this UI — put Cloudflare Access / Authelia / Tailscale in front
when exposing publicly. Opt-out via ``app.web_ui.enabled: false`` in
``config.yaml``.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import threading

from typing import Any

from flask import Flask, jsonify

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    ENV_CONFIG_FILE_PATH_KEY,
    config_parser,
    get_logger,
    read_config,
)

LOGGER = get_logger()


def _current_config_path() -> str:
    """Resolve the active config path the same way sync.py does."""
    return os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)


def _load_current_config() -> dict | None:
    """Re-read config.yaml fresh on every request so edits show up live."""
    path = _current_config_path()
    if not os.path.isfile(path):
        return None
    return read_config(config_path=path)


def _get_marker_filename(config: dict) -> str:
    """Marker filename from ``app.mount_marker_filename`` if PR 8 helpers
    are available, falling back to ``.mounted`` otherwise.

    Keeps PR 9 standalone — works on both vanilla mandarons and the
    combined fork."""
    getter = getattr(config_parser, "get_mount_marker_filename", None)
    if getter is None:
        return ".mounted"
    return getter(config=config)


def _get_require_mount_marker(config: dict, service: str) -> bool:
    """``{drive,photos}.require_mount_marker`` if PR 8 helpers are
    available, falling back to False otherwise."""
    getter = getattr(config_parser, f"get_{service}_require_mount_marker", None)
    if getter is None:
        return False
    return bool(getter(config=config))


def _build_service(config: dict, service: str, marker_filename: str) -> dict[str, Any]:
    """Compose a single service entry (Photos or Drive) for /api/status."""
    if service == "photos":
        destination = config_parser.prepare_photos_destination(config=config)
        interval = config_parser.get_photos_sync_interval(config=config, log_messages=False)
        name = "Photos"
    else:
        destination = config_parser.prepare_drive_destination(config=config)
        interval = config_parser.get_drive_sync_interval(config=config, log_messages=False)
        name = "Drive"

    marker_path = os.path.join(destination, marker_filename)
    return {
        "name": name,
        "destination": destination,
        "destination_exists": os.path.isdir(destination),
        "sync_interval_s": interval,
        "require_mount_marker": _get_require_mount_marker(config=config, service=service),
        "marker_present": os.path.isfile(marker_path),
        "marker_path": marker_path,
    }


def _logger_filename(config: dict | None) -> str:
    """Resolve where ``sync.py`` is writing log lines. Best-effort.

    Reads ``app.logger.filename`` directly off the config dict to avoid
    introducing a new ``config_parser`` helper just for this — keeps the
    upstream PR diff small.
    """
    if not config:
        return ""
    try:
        return config.get("app", {}).get("logger", {}).get("filename", "") or ""
    except AttributeError:
        return ""


def _tail_log_file(path: str, lines: int = 200) -> list[str]:
    """Return the last ``lines`` lines of ``path``.

    Best-effort: missing path, unreadable file, or decode failure all
    return an empty list. Reads from the end in 8 KiB blocks so the cost
    is bounded by ``lines * average_line_length`` rather than file size.
    """
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= lines:
                read_size = min(block, size)
                size -= read_size
                f.seek(size)
                data = f.read(read_size) + data
        return data.decode("utf-8", errors="replace").splitlines()[-lines:]
    except OSError as e:
        LOGGER.warning(f"Web UI could not tail log {path}: {e!s}")
        return []


def _build_status(config: dict | None) -> dict[str, Any]:
    """Compose the payload returned by /api/status (and consumed by the
    dashboard template)."""
    if not config:
        return {
            "config_loaded": False,
            "config_path": _current_config_path(),
            "username": None,
            "services": [],
        }

    marker_filename = _get_marker_filename(config=config)
    services = []
    if "photos" in config:
        services.append(_build_service(config=config, service="photos", marker_filename=marker_filename))
    if "drive" in config:
        services.append(_build_service(config=config, service="drive", marker_filename=marker_filename))

    return {
        "config_loaded": True,
        "config_path": _current_config_path(),
        "username": config_parser.get_username(config=config),
        "region": config_parser.get_region(config=config),
        "marker_filename": marker_filename,
        "services": services,
    }


def create_app(testing: bool = False) -> Flask:
    """Construct the Flask app.

    Splitting this out keeps ``tests/`` able to build the app under
    ``TESTING=True`` without spawning a thread.
    """
    app = Flask(__name__)
    app.config["TESTING"] = testing

    @app.route("/api/health")
    def health():
        """Tiny endpoint for external monitors.

        - 200 ``{"state": "ok"}`` when the config file is readable.
        - 503 ``{"state": "config_missing"}`` when it isn't.

        ``2fa_required`` is *not* a 503 — Apple sessions expire all the time
        and the dashboard must stay reachable so the user can re-auth.
        """
        if not os.path.isfile(_current_config_path()):
            return jsonify({"state": "config_missing"}), 503
        return jsonify({"state": "ok"})

    @app.route("/api/status")
    def status():
        """Live status payload for the dashboard + external consumers."""
        config = _load_current_config()
        payload = _build_status(config=config)
        if not payload["config_loaded"]:
            return jsonify(payload), 503
        return jsonify(payload)

    @app.route("/api/logs")
    def logs():
        """Last 200 lines of the configured log file. Best-effort: missing
        or unreadable returns an empty list (never 500 — the dashboard
        relies on this being reachable to render the rest of the page)."""
        config = _load_current_config()
        return jsonify({"lines": _tail_log_file(path=_logger_filename(config=config), lines=200)})

    return app


def start_in_thread(host: str = "0.0.0.0", port: int = 8080) -> threading.Thread:  # noqa: S104
    """Launch the Flask app on a daemon thread.

    The main sync loop owns the process; the web thread dies when the
    parent process exits.
    """
    app = create_app()

    def _serve():
        try:
            # Werkzeug dev server — single user, behind a proxy.
            # Zero extra runtime deps (no gunicorn).
            app.run(host=host, port=port, debug=False, use_reloader=False)
        except OSError as e:
            LOGGER.error(f"Web UI failed to bind {host}:{port} — {e!s}")

    thread = threading.Thread(target=_serve, name="icloud-web-ui", daemon=True)
    thread.start()
    LOGGER.info(f"Web UI listening on http://{host}:{port}/")
    return thread
