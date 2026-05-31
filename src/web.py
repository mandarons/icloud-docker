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

import hmac
import os
import secrets
import threading
import time
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_COOKIE_DIRECTORY,
    ENV_CONFIG_FILE_PATH_KEY,
    config_parser,
    get_logger,
    read_config,
    web_signals,
)

LOGGER = get_logger()

# Module-level holder for the live icloudpy session created during
# POST /auth/password, so POST /auth/code can call validate_2fa_code on
# the SAME session. Cleared after a successful trust_session or via
# POST /auth/reset.
_PENDING_AUTH: dict[str, Any] = {}
_AUTH_LOCK = threading.Lock()

# Drop stale pending auth after this many seconds. The submitted Apple ID
# password sits in process memory (in ``_PENDING_AUTH["password"]``) while
# waiting for the user to enter their 2FA code; without an expiry it would
# linger indefinitely if the user closed the browser tab mid-flow. 10 min
# is generous for typing a code -- and short enough that a forgotten
# session evaporates before the next sync cycle picks up the keyring.
_PENDING_AUTH_TTL_SECONDS = 600


def _pending_auth_is_stale() -> bool:
    """True when the in-memory password is older than the TTL.

    Caller must hold ``_AUTH_LOCK``. Returns False for an empty dict
    (nothing to expire) and for entries that pre-date stashed_at
    bookkeeping (defensive — we never penalise a fresh stash).
    """
    if not _PENDING_AUTH:
        return False
    stashed_at = _PENDING_AUTH.get("stashed_at")
    if stashed_at is None:
        return False
    return (time.monotonic() - stashed_at) > _PENDING_AUTH_TTL_SECONDS


def _expire_stale_pending_auth_unlocked() -> None:
    """If the pending auth is older than the TTL, wipe it. Caller holds the lock."""
    if _pending_auth_is_stale():
        LOGGER.info("Web UI: expiring stale _PENDING_AUTH past TTL.")
        _PENDING_AUTH.clear()


# CSRF defence. Threat model: even with the default host pinned to
# 127.0.0.1, a user who opts into LAN exposure (host: 0.0.0.0) AND lacks
# a proper auth proxy in front would otherwise be vulnerable to a
# same-network attacker who tricks them into loading a page that posts
# to ``/auth/refresh-trust`` or ``/api/sync``. Double-submit cookie
# pattern: per-process random token, set as a SameSite=Strict cookie,
# required on every state-changing POST as either a form field
# ``csrf_token`` or an ``X-CSRF-Token`` header. SameSite=Strict alone
# already blocks the cross-site cookie send in modern browsers; the
# server-side compare is belt-and-braces for older clients.
_CSRF_TOKEN = secrets.token_urlsafe(32)
_CSRF_COOKIE_NAME = "csrf_token"


def _get_csrf_token() -> str:
    """Expose the token to templates (so forms can embed it) and to
    tests (so they can post it). Process-lifetime, regenerated on
    restart -- enough for a single-user operator console."""
    return _CSRF_TOKEN


def _require_csrf() -> tuple[Any, int] | None:
    """Validate CSRF token on the current request. Returns ``None``
    when the request is allowed, or a ``(response, status)`` tuple
    when it should be rejected. Use at the top of every state-
    changing endpoint:

        rejection = _require_csrf()
        if rejection is not None:
            return rejection
    """
    cookie = request.cookies.get(_CSRF_COOKIE_NAME)
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    # The cookie must match this process's token AND the submitted value
    # must match the cookie. Browsers won't include a SameSite=Strict
    # cookie on a cross-site POST, so the cookie absence alone is the
    # primary signal; the form/header echo is the belt-and-braces leg.
    if not cookie or not hmac.compare_digest(cookie, _CSRF_TOKEN):
        return jsonify({"error": "CSRF cookie missing or stale"}), 403
    if not submitted or not hmac.compare_digest(submitted, cookie):
        return jsonify({"error": "CSRF token mismatch"}), 403
    return None


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
    except Exception as e:
        # Broad on purpose: ``/api/health`` exists for external monitors
        # and must be robust against any config-loading failure (YAML
        # parse errors, permission denied, missing credentials block,
        # ruamel internals raising). A 500 on /api/health blinds the
        # monitor; rendering a "config error" state lets the user fix
        # it via the UI.
        LOGGER.warning(f"Web UI: read_config failed: {e!s}")
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


def _get_library_destinations(config: dict) -> dict[str, str]:
    """``photos.library_destinations`` mapping (PR 3 helper) — best-effort
    standalone-safe getter so PR 9 works on vanilla mandarons too."""
    getter = getattr(config_parser, "get_photos_library_destinations", None)
    if getter is None:
        # Direct read fallback so the dashboard still surfaces the mapping
        # even without PR 3's helper merged.
        try:
            raw = config.get("photos", {}).get("library_destinations", {}) or {}
            return {str(k): str(v) for k, v in raw.items()}
        except AttributeError:
            return {}
    try:
        return getter(config=config) or {}
    except Exception:
        return {}


def _build_service(config: dict, service: str, marker_filename: str) -> dict[str, Any]:
    """Compose a single service entry (Photos or Drive) for /api/status."""
    if service == "photos":
        destination = config_parser.prepare_photos_destination(config=config)
        interval = config_parser.get_photos_sync_interval(
            config=config,
            log_messages=False,
        )
        name = "Photos"
        library_destinations = _get_library_destinations(config=config)
    else:
        destination = config_parser.prepare_drive_destination(config=config)
        interval = config_parser.get_drive_sync_interval(
            config=config,
            log_messages=False,
        )
        name = "Drive"
        library_destinations = {}

    marker_path = os.path.join(destination, marker_filename)
    state = web_signals.get_sync_state(service=service)
    stats = None
    if state:
        completed_at = state.get("completed_at")
        stats = {
            "last_sync_relative": (
                web_signals.format_relative_time(completed_at) if completed_at else None
            ),
            "files_downloaded": state.get("files_downloaded"),
            "files_skipped": state.get("files_skipped"),
            "files_removed": state.get("files_removed"),
            "files_on_disk": (
                (state.get("files_downloaded") or 0) + (state.get("files_skipped") or 0)
                if (
                    state.get("files_downloaded") is not None
                    or state.get("files_skipped") is not None
                )
                else None
            ),
            "errors": state.get("errors", 0),
            "duration_seconds": state.get("duration_seconds"),
        }
    return {
        "name": name,
        "destination": destination,
        "destination_exists": os.path.isdir(destination),
        "sync_interval_s": interval,
        "require_mount_marker": _get_require_mount_marker(
            config=config,
            service=service,
        ),
        "marker_present": os.path.isfile(marker_path),
        "marker_path": marker_path,
        "library_destinations": library_destinations,
        "stats": stats,
        "force_sync_pending": service in web_signals.pending_force_syncs(),
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
        services.append(
            _build_service(
                config=config,
                service="photos",
                marker_filename=marker_filename,
            ),
        )
    if "drive" in config:
        services.append(
            _build_service(
                config=config,
                service="drive",
                marker_filename=marker_filename,
            ),
        )

    username = config_parser.get_username(config=config)
    return {
        "config_loaded": True,
        "config_path": _current_config_path(),
        "username": username,
        "region": config_parser.get_region(config=config),
        "marker_filename": marker_filename,
        "services": services,
        "auth_state": _detect_auth_state(username=username),
        "force_sync_pending": web_signals.pending_force_syncs(),
    }


def _detect_auth_state(username: str | None) -> str:
    """Best-effort check of whether the sync loop can actually authenticate.

    Returns one of:
      - ``not_configured`` — no ``app.credentials.username`` in config.
      - ``setup_needed`` — username set, but the keyring has no password
        cached. The container's first 2FA flow hasn't been completed.
      - ``ready`` — username set + keyring entry present. Sync loop can
        resume the session on the next retry.

    Distinct from a *live* iCloud session check (which would require
    hitting Apple). This is the cheap on-disk signal users see today
    when sync.py's loop prints ``Password is not stored in keyring``.
    """
    if not username:
        return "not_configured"
    try:
        from icloudpy import utils as icloudpy_utils

        if icloudpy_utils.password_exists_in_keyring(username):
            return "ready"
    except Exception as e:
        LOGGER.debug(f"Web UI auth-state check raised: {e!s}")
    return "setup_needed"


def create_app(testing: bool = False) -> Flask:
    """Construct the Flask app.

    Splitting this out keeps ``tests/`` able to build the app under
    ``TESTING=True`` without spawning a thread.
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["TESTING"] = testing

    # Trust X-Forwarded-* from a single reverse-proxy hop (Cloudflare Tunnel,
    # Authelia / Traefik). Lets ``url_for`` produce ``https://`` URLs and
    # prevents Flask from mis-detecting the scheme when behind a TLS-
    # terminating proxy. One hop is correct here — Cloudflare → backend.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    @app.after_request
    def _no_cache(response):
        """Defense against intermediaries (browser back/forward cache,
        Cloudflare's auto-minify, mobile carrier proxies) serving stale
        dashboard or auth payloads. The dashboard is always live data —
        a cached snapshot would hide a missing mount marker or an
        expired session."""
        response.headers["Cache-Control"] = (
            "private, no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # CSRF defence: set the SameSite=Strict token cookie on every
        # response so forms rendered server-side can read it (via the
        # template) and same-site fetches automatically include it.
        # ``secure=False`` because the default deployment is loopback
        # over plain HTTP; users behind a TLS proxy benefit from the
        # proxy's transport security, and SameSite=Strict is the load-
        # bearing protection here regardless of TLS.
        response.set_cookie(
            _CSRF_COOKIE_NAME,
            _CSRF_TOKEN,
            samesite="Strict",
            httponly=False,
            secure=False,
            path="/",
        )
        return response

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
            csrf_token=_get_csrf_token(),
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
        return jsonify(
            {"lines": _tail_log_file(path=_logger_filename(config=config), lines=200)},
        )

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
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

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
            except (KeyError, AttributeError, TypeError):  # pragma: no cover
                # Defensive: get_username walks app.credentials.username;
                # partial configs (no credentials block) raise. Treat as
                # missing. Rare in practice — coverage-pragma'd because
                # mocking get_username globally breaks _render_auth.
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
                _render_auth(
                    message=f"Authentication failed: {e!s}",
                    message_kind="err",
                ),
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
                _expire_stale_pending_auth_unlocked()
                _PENDING_AUTH["api"] = api
                _PENDING_AUTH["username"] = username
                _PENDING_AUTH["password"] = password
                _PENDING_AUTH["stashed_at"] = time.monotonic()
            return redirect(url_for("auth_form"))

        # No 2FA needed — cached session still trusted. Persist the
        # password to the keyring so the sync loop can use it on the
        # next retry, then bounce back to the dashboard.
        try:
            icloudpy_utils.store_password_in_keyring(
                username=username,
                password=password,
            )
        except Exception as e:
            LOGGER.warning(f"Web UI keyring persist failed (non-fatal): {e!s}")
        return redirect(url_for("dashboard"))

    @app.route("/auth/code", methods=["POST"])
    def auth_code():
        """Step 2: validate the 6-digit code on the in-flight session,
        trust the browser, persist the password, clear pending, redirect.

        - 400 if the code field is empty or no pending auth exists.
        - 400 + 'Code rejected' if Apple says no — pending kept so the
          user can retry without re-entering the password.
        - On success: validate_2fa_code -> trust_session (failures here
          are logged but non-fatal — the code already worked) ->
          store_password_in_keyring -> clear pending -> redirect to /.
        """
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        code = request.form.get("code", "").strip()
        if not code:
            return (
                _render_auth(message="Enter the 6-digit code.", message_kind="err"),
                400,
            )

        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            api = _PENDING_AUTH.get("api")
            username = _PENDING_AUTH.get("username")
            password = _PENDING_AUTH.get("password")
        if api is None:
            return (
                _render_auth(
                    message="No pending auth — submit your password first.",
                    message_kind="err",
                ),
                400,
            )

        # All exit paths from here clear ``_PENDING_AUTH`` -- including
        # failed validate_2fa_code, rejected codes, and trust_session
        # failures. Without the ``finally`` the previous code only cleared
        # on the success path, leaving the password sitting in process
        # memory if Apple raised. On rejection the user retries via
        # /auth/refresh-trust or by re-entering the password; we'd rather
        # they take that path than leave a stale credential in memory.
        try:
            try:
                accepted = api.validate_2fa_code(code)
            except Exception as e:
                LOGGER.exception("Web UI: validate_2fa_code raised")
                return (
                    _render_auth(
                        message=f"2FA validation error: {e!s}",
                        message_kind="err",
                    ),
                    400,
                )

            if not accepted:
                return (
                    _render_auth(
                        message="Code rejected by Apple. Try again — make sure you copy the latest code.",
                        message_kind="err",
                    ),
                    400,
                )

            # Code worked. Best-effort trust so the next session resume skips
            # 2FA; if that fails (e.g. cookie store write error) just log it
            # — the user's auth still succeeded for this session.
            try:
                api.trust_session()
            except Exception as e:
                LOGGER.warning(f"Web UI trust_session failed (non-fatal): {e!s}")

            # Persist password to keyring so the sync-loop's next retry
            # picks up the trusted session without prompting.
            try:
                from icloudpy import utils as icloudpy_utils

                icloudpy_utils.store_password_in_keyring(
                    username=username,
                    password=password,
                )
            except Exception as e:
                LOGGER.warning(f"Web UI keyring persist failed (non-fatal): {e!s}")

            return redirect(url_for("dashboard"))
        finally:
            with _AUTH_LOCK:
                _PENDING_AUTH.clear()

    @app.route("/auth/reset", methods=["POST"])
    def auth_reset():
        """Escape hatch — clear any in-flight pending-auth state.

        Useful when the user closed the tab mid-2FA and wants to start
        over without waiting for the in-memory state to expire.
        """
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        with _AUTH_LOCK:
            _PENDING_AUTH.clear()
        return redirect(url_for("auth_form"))

    @app.route("/auth/refresh-trust", methods=["POST"])
    def auth_refresh_trust():
        """One-tap re-auth using the keyring-cached password.

        When Apple's trusted-session lifetime is winding down (or has
        already expired since the last sync attempt), this lets the user
        kick off a fresh 2FA push without having to retype their
        password. Useful for "reset the clock" workflows where the
        password didn't change — only the trust window did.

        Flow:
          1. Look up keyring password by username from config.
          2. If absent → bounce to /auth so the user enters a new one.
          3. If present → spin up a transient ICloudPyService, fire the
             2FA push if needed, stash the live session under the same
             _PENDING_AUTH dict /auth/code already consumes.
          4. Redirect to /auth — UI is now in "enter 6-digit code" mode.
        """
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        config = _load_current_config()
        username = None
        if config:
            try:
                username = config_parser.get_username(config=config)
            except (
                KeyError,
                AttributeError,
                TypeError,
            ):  # pragma: no cover — defensive for hand-malformed configs
                username = None
        if not username:
            return (
                _render_auth(
                    message="No app.credentials.username in config.yaml — set it first.",
                    message_kind="err",
                ),
                400,
            )

        try:
            from icloudpy import utils as icloudpy_utils

            password = icloudpy_utils.get_password_from_keyring(username)
        except Exception as e:
            LOGGER.exception("Web UI: keyring lookup raised")
            return (
                _render_auth(
                    message=f"Keyring lookup failed: {e!s}",
                    message_kind="err",
                ),
                500,
            )
        if not password:
            return (
                _render_auth(
                    message=(
                        "No password in keyring — submit one below to "
                        "complete the first-time auth."
                    ),
                    message_kind="warn",
                ),
                400,
            )

        try:
            import icloudpy

            api = icloudpy.ICloudPyService(
                apple_id=username,
                password=password,
                cookie_directory=DEFAULT_COOKIE_DIRECTORY,
            )
        except Exception as e:
            LOGGER.exception("Web UI refresh-trust: ICloudPyService raised")
            return (
                _render_auth(
                    message=(
                        f"Refresh trust failed: {e!s}. Your stored "
                        "password may be stale — submit a new one below."
                    ),
                    message_kind="err",
                ),
                400,
            )

        if not api.requires_2fa:
            # Trust window was still alive — nothing to do, sync loop is
            # already authenticated. Bounce back to the dashboard with
            # the success state.
            return redirect(url_for("dashboard"))

        try:
            trigger = getattr(api, "trigger_2fa_push_notification", None)
            if callable(trigger):
                trigger()
        except Exception as e:
            LOGGER.warning(f"Web UI refresh-trust 2FA push failed: {e!s}")

        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            _PENDING_AUTH["api"] = api
            _PENDING_AUTH["username"] = username
            _PENDING_AUTH["password"] = password
            _PENDING_AUTH["stashed_at"] = time.monotonic()
        return redirect(url_for("auth_form"))

    @app.route("/api/sync", methods=["POST"])
    def api_sync():
        """Queue an immediate sync run for one or both services.

        ``service=drive`` / ``service=photos`` / ``service=all``. The
        web thread can't run sync.sync() directly — it would race with
        the existing loop. Instead this touches a sentinel file in
        ICLOUD_DOCKER_CONFIG_DIR; ``src.sync`` checks for it at the top
        of each loop iteration and resets the countdown when present.

        Idempotent: tapping repeatedly while a request is still queued
        is a no-op (the sentinel just gets re-touched).
        """
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        service = (
            (request.form.get("service") or request.args.get("service") or "")
            .strip()
            .lower()
        )
        if service == "all":
            wanted = ("drive", "photos")
        elif service in ("drive", "photos"):
            wanted = (service,)
        else:
            return (
                jsonify({"error": "service must be one of: drive, photos, all"}),
                400,
            )

        # Honour the user's config — only queue services that are
        # actually configured. Avoids touching a photos sentinel on a
        # drive-only install.
        config = _load_current_config()
        configured = {svc for svc in ("drive", "photos") if config and svc in config}
        if not configured:
            return jsonify({"error": "no services configured"}), 400

        queued = [
            svc
            for svc in wanted
            if svc in configured and web_signals.request_force_sync(svc)
        ]

        # Browser form submit gets a redirect; API consumers (curl,
        # monitors) get JSON. Distinguished by Accept header.
        if request.headers.get("Accept", "").startswith("application/json"):
            return jsonify({"queued": queued})
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
        csrf_token=_get_csrf_token(),
    )


def start_in_thread(
    host: str = "127.0.0.1",
    port: int = 8080,
) -> threading.Thread:
    """Launch the Flask app on a daemon thread.

    The main sync loop owns the process; the web thread dies when the
    parent process exits.
    """
    app = create_app()

    def _serve():
        # NOTE on the server: ``Flask.app.run()`` uses Werkzeug's dev
        # server. Choice is intentional -- this UI is a single-user,
        # behind-a-proxy operator console (default host 127.0.0.1, no
        # CSRF, no authn of its own), not a public-facing API. Zero
        # extra runtime deps (no gunicorn) keeps the docker image
        # small. ``threaded=True`` lets Cloudflare's edge health-checks
        # overlap with the user's tab. Werkzeug will emit its
        # "WARNING: This is a development server" banner at startup --
        # that's expected, leaving it visible so anyone repurposing
        # this for unattended public exposure sees it.
        try:
            app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except OSError as e:
            LOGGER.error(f"Web UI failed to bind {host}:{port} — {e!s}")

    thread = threading.Thread(target=_serve, name="icloud-web-ui", daemon=True)
    thread.start()
    LOGGER.info(f"Web UI listening on http://{host}:{port}/")
    return thread
