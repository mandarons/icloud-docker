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

from flask import Flask, jsonify, redirect, render_template, request, url_for

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_COOKIE_DIRECTORY,
    ENV_CONFIG_FILE_PATH_KEY,
    config_parser,
    get_logger,
    read_config,
)

LOGGER = get_logger()

# Module-level holder for the live icloudpy session created during
# POST /auth/password, so POST /auth/code can call validate_2fa_code on
# the SAME session. Cleared after a successful trust_session or via
# POST /auth/reset.
_PENDING_AUTH: dict[str, Any] = {}
_AUTH_LOCK = threading.Lock()


def _current_config_path() -> str:
    """Resolve the active config path the same way sync.py does."""
    return os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)


def _load_current_config() -> dict | None:
    """Re-read config.yaml fresh on every request so edits show up live.

    Defensive: mandarons' ``read_config`` reaches into
    ``config["app"]["credentials"]["username"]`` unconditionally and
    crashes if the credentials block is missing. Catch that so a partial
    config (e.g. fresh install with only ``app.logger`` set) still lets
    the web UI render the setup-needed state instead of 500-ing.
    """
    path = _current_config_path()
    if not os.path.isfile(path):
        return None
    try:
        return read_config(config_path=path)
    except (KeyError, AttributeError, TypeError) as e:
        LOGGER.warning(f"Web UI: read_config failed (partial config?): {e!s}")
        return None


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
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["TESTING"] = testing

    @app.route("/")
    def dashboard():
        """Render the HTML dashboard — Apple-leaning design."""
        config = _load_current_config()
        status_payload = _build_status(config=config)
        log_path = _logger_filename(config=config)
        log_lines = _tail_log_file(path=log_path, lines=200)
        return render_template(
            "dashboard.html",
            status=status_payload,
            log_lines=log_lines,
            log_path=log_path,
            active_nav="dashboard",
            version=os.environ.get("APP_VERSION", ""),
        )

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

    @app.route("/auth", methods=["GET"])
    def auth_form():
        """Auth form. Renders the password field by default; renders the
        6-digit code field instead when ``_PENDING_AUTH`` indicates that
        the password step already succeeded and 2FA is pending."""
        return _render_auth(message=None, message_kind=None)

    @app.route("/auth/password", methods=["POST"])
    def auth_password():
        """Step 1: store password in keyring, instantiate ICloudPyService,
        trigger 2FA push if needed.

        On success of either path: redirects — to /auth (now showing the
        code form) if 2FA is pending, or back to / if the cached session
        was still trusted.

        Exceptions are caught and rendered as an error pill on /auth so
        the user sees what Apple said.
        """
        password = request.form.get("password", "")
        if not password:
            return (
                _render_auth(message="Password is required.", message_kind="err"),
                400,
            )

        config = _load_current_config()
        username = None
        if config:
            try:
                username = config_parser.get_username(config=config)
            except (KeyError, AttributeError, TypeError):
                # get_username walks app.credentials.username; partial
                # configs (no credentials block at all) raise. Treat as
                # missing.
                username = None
        if not username:
            return (
                _render_auth(
                    message="No app.credentials.username in config.yaml — set it and reload.",
                    message_kind="err",
                ),
                400,
            )

        try:
            # Late import so /api/health still works if icloudpy is mid-upgrade.
            import icloudpy
            from icloudpy import utils as icloudpy_utils

            api = icloudpy.ICloudPyService(
                apple_id=username,
                password=password,
                cookie_directory=DEFAULT_COOKIE_DIRECTORY,
            )
        except Exception as e:
            LOGGER.exception("Web UI auth failed during ICloudPyService instantiation")
            return (
                _render_auth(message=f"Authentication failed: {e!s}", message_kind="err"),
                400,
            )

        if api.requires_2fa:
            # PR 1 / fix/ios-26.4-auth dependency — best-effort. Catches all
            # exceptions so a missing-method or push-trigger failure doesn't
            # block the user from typing in a code they got via SMS.
            try:
                trigger = getattr(api, "trigger_2fa_push_notification", None)
                if callable(trigger):
                    trigger()
            except Exception as e:
                LOGGER.warning(f"Web UI 2FA push trigger failed (non-fatal): {e!s}")
            with _AUTH_LOCK:
                _PENDING_AUTH["api"] = api
                _PENDING_AUTH["username"] = username
                _PENDING_AUTH["password"] = password
            return redirect(url_for("auth_form"))

        # No 2FA needed — cached session still trusted. Persist the
        # password to the keyring so the sync loop can use it on the
        # next retry, then bounce back to the dashboard.
        try:
            icloudpy_utils.store_password_in_keyring(username=username, password=password)
        except Exception as e:
            LOGGER.warning(f"Web UI keyring persist failed (non-fatal): {e!s}")
        return redirect(url_for("dashboard"))

    return app


def _render_auth(message: str | None, message_kind: str | None):
    """Render auth.html with the current pending state and an optional
    error/info pill. Factored out so the POST endpoints can reuse it."""
    from flask import render_template as _render

    config = _load_current_config()
    status_payload = _build_status(config=config)
    with _AUTH_LOCK:
        pending = bool(_PENDING_AUTH)
    return _render(
        "auth.html",
        status=status_payload,
        pending=pending,
        message=message,
        message_kind=message_kind,
        active_nav="auth",
        version=os.environ.get("APP_VERSION", ""),
    )


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
