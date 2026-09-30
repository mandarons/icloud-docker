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

import base64
import hmac
import json
import os
import re
import secrets
import shutil
import struct
import tempfile
import threading
import time
from typing import Any

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.serving import make_server

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_COOKIE_DIRECTORY,
    ENV_CONFIG_FILE_PATH_KEY,
    config_parser,
    get_logger,
    read_config,
    web_signals,
)
from src.config_utils import get_config_value_or_none

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


def _wake_sync_loop() -> None:
    """Cut short the auth-retry wait after a re-auth succeeds.

    Without this the loop serves out the rest of an interval that began
    before the problem was solved -- the user completes the sign-in and
    the dashboard keeps reporting the sync as stopped for up to
    ``retry_login_interval``.

    Best-effort: a missed nudge costs a delay, never correctness.
    """
    try:
        web_signals.record_reauth_completed()
    except Exception as e:  # noqa: BLE001 - never fail a successful sign-in
        LOGGER.debug(f"could not signal the completed re-auth: {e!s}")


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


def _clear_pending_auth_unlocked() -> None:
    """Forget the pending auth, and a security-key ceremony's private cookie
    jar with it -- it holds that ceremony's Apple session cookies, and an
    abandoned ceremony would otherwise leave them in the temp dir until the
    container restarts. Caller holds the lock."""
    _discard_ceremony_dir(_PENDING_AUTH.get("cookie_dir"))
    _PENDING_AUTH.clear()


def _expire_stale_pending_auth_unlocked() -> None:
    """If the pending auth is older than the TTL, wipe it. Caller holds the lock."""
    if _pending_auth_is_stale():
        LOGGER.info("Web UI: expiring stale _PENDING_AUTH past TTL.")
        _clear_pending_auth_unlocked()


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

    **Calling from a script / monitor.** Every state-changing endpoint
    needs BOTH the CSRF cookie and a matching token, so a bare
    ``curl -X POST /api/sync -d service=drive`` gets a 403. The cookie
    is only set by a prior page load, so fetch it first and echo it
    back in the ``X-CSRF-Token`` header::

        curl -c jar -s http://127.0.0.1:8080/ >/dev/null
        TOKEN=$(awk '/csrf_token/ {print $7}' jar)
        curl -b jar -H "X-CSRF-Token: $TOKEN" \
             -X POST http://127.0.0.1:8080/api/sync -d service=drive

    The 403 bodies name which leg failed ("CSRF cookie missing or
    stale" vs "CSRF token mismatch") so the fix is obvious.
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
    """Marker filename from ``app.mount_marker_filename`` (default ``.mounted``)."""
    return config_parser.get_mount_marker_filename(config=config)


def _get_require_mount_marker(config: dict, service: str) -> bool:
    """``{drive,photos}.require_mount_marker`` for the given service."""
    getter = getattr(config_parser, f"get_{service}_require_mount_marker")
    return bool(getter(config=config))


def _get_library_destinations(config: dict) -> dict[str, str]:
    """``photos.library_destinations`` mapping (empty dict when unset)."""
    return config_parser.get_photos_library_destinations(config=config) or {}


def _get_configured_libraries(config: dict) -> list[str]:
    """Libraries the operator named: ``photos.filters.libraries``, then any
    ``photos.library_destinations`` keys, in config order.

    Read directly rather than through ``get_photos_libraries_filter``, which
    logs "downloading all libraries" whenever the filter is unset -- once per
    dashboard load.
    """
    named = get_config_value_or_none(config=config, config_path=["photos", "filters", "libraries"]) or []
    if isinstance(named, str):
        # ``libraries: PrimarySync`` rather than a list -- iterating the
        # string would list one library per character.
        named = [named]
    named = [n for n in named if isinstance(n, str)]
    return list(dict.fromkeys(named + list(_get_library_destinations(config=config))))


def _build_service(config: dict, service: str, marker_filename: str) -> dict[str, Any]:
    """Compose a single service entry (Photos or Drive) for /api/status."""
    if service == "photos":
        # Read-only on purpose: ``prepare_*_destination`` calls
        # ``join_and_ensure_path`` (mkdir), so a plain ``GET /api/status``
        # would write to disk -- and 500 the whole dashboard on a
        # read-only destination mount. Composing the non-mutating getters
        # lets a read-only or absent destination degrade to
        # ``destination_exists: false`` instead.
        destination = os.path.join(
            config_parser.get_root_destination_path(config=config),
            config_parser.get_photos_destination_path(config=config),
        )
        interval = config_parser.get_photos_sync_interval(
            config=config,
            log_messages=False,
        )
        name = "Photos"
        library_destinations = _get_library_destinations(config=config)
    else:
        destination = os.path.join(
            config_parser.get_root_destination_path(config=config),
            config_parser.get_drive_destination_path(config=config),
        )
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
            "last_sync_relative": (web_signals.format_relative_time(completed_at) if completed_at else None),
            "files_downloaded": state.get("files_downloaded"),
            "files_skipped": state.get("files_skipped"),
            "files_removed": state.get("files_removed"),
            # Named for what it is: the last COMPLETED cycle's
            # downloaded+skipped total. The state record overwrites per
            # cycle rather than accumulating, so this is not a running
            # count of files on disk.
            "last_cycle_total": (
                (state.get("files_downloaded") or 0) + (state.get("files_skipped") or 0)
                if (state.get("files_downloaded") is not None or state.get("files_skipped") is not None)
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
        "libraries": (
            _build_libraries(_get_configured_libraries(config=config), library_destinations)
            if service == "photos"
            else []
        ),
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
    trust = web_signals.get_trust_state()
    trust_expires_at = trust.get("expires_at")
    trust_days_remaining: int | None = None
    if trust_expires_at:
        try:
            import datetime

            exp = datetime.datetime.fromisoformat(trust_expires_at)
            now = datetime.datetime.now(tz=exp.tzinfo) if exp.tzinfo else datetime.datetime.now()
            trust_days_remaining = (exp - now).days
        except (
            ValueError,
            TypeError,
        ):  # pragma: no cover -- defensive against malformed iso
            trust_days_remaining = None
    return {
        "config_loaded": True,
        "config_path": _current_config_path(),
        "username": username,
        "region": config_parser.get_region(config=config),
        "marker_filename": marker_filename,
        "services": services,
        "auth_state": _detect_auth_state(username=username),
        "auth_method": web_signals.get_auth_method(username) if username else None,
        "force_sync_pending": web_signals.pending_force_syncs(),
        "trust_expires_at": trust_expires_at,
        "trust_days_remaining": trust_days_remaining,
    }


def _build_libraries(configured: list[str], library_destinations: dict[str, str]) -> list[dict[str, Any]]:
    """One row per photo library: where it goes and how it last went.

    Only libraries this container actually syncs are listed: the ones the
    operator named in config, plus any that have completed a sync or are
    syncing right now. An account can carry libraries that never serve
    anything -- there is nothing to do with them, so they are left out
    rather than shown as a permanent failure. The log still records every
    attempt, and naming a library in config always lists it.

    Configured libraries come first, in config order.
    """
    states = web_signals.get_library_states()
    rows = []
    active = sorted(
        n
        for n, entry in states.items()
        if n not in configured and (entry.get("completed_at") or entry.get("state") == "syncing")
    )
    for name in configured + active:
        entry = states.get(name, {})
        completed_at = entry.get("completed_at")
        rows.append(
            {
                "name": name,
                "subdir": library_destinations.get(name),
                "state": entry.get("state"),
                "error": entry.get("error"),
                "completed_relative": (
                    web_signals.format_relative_time(completed_at) if completed_at else None
                ),
            },
        )
    return rows


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
            # Ask the sync loop before claiming health: every on-disk
            # signal still looks correct while an account is stuck on a
            # second factor, so "keyring populated" alone would render a
            # green dashboard over a sync that has not run for weeks.
            if web_signals.get_auth_blocked().get("blocked"):
                return "reauth_needed"
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

    # No ``static_folder``: templates are single-file with inline CSS and
    # nothing ships under src/static, so wiring it would only add a 404
    # route for /static/*.
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_dir)
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
        response.headers["Cache-Control"] = "private, no-store, no-cache, must-revalidate, max-age=0"
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
        _wake_sync_loop()
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

            _wake_sync_loop()
            return redirect(url_for("dashboard"))
        finally:
            with _AUTH_LOCK:
                _clear_pending_auth_unlocked()

    @app.route("/auth/security-key", methods=["GET"])
    def auth_security_key():
        """Start a security-key (FIDO2/WebAuthn) re-auth ceremony.

        Apple disables every other second factor once security keys are
        enrolled, so the 6-digit paths (``/auth/code``, the Telegram
        listener) can never complete for such an account -- Apple answers
        every factor endpoint with an ``fsaChallenge`` instead of pushing
        a code.

        The assertion cannot be produced by this page: WebAuthn requires
        ``rpId`` to be a registrable suffix of the page origin, and
        Apple's ``rpId`` is ``apple.com``. Browsers additionally blocklist
        FIDO devices from WebHID/WebUSB precisely to stop a page doing raw
        CTAP against another origin. So the signing step runs natively on
        whatever machine holds the key, and only the signed assertion
        comes back here.

        This handler authenticates with the keyring password, reads
        Apple's challenge, stashes the live session under ``_PENDING_AUTH``
        (same slot ``/auth/code`` uses) and renders the blob the operator
        feeds to the signer.
        """
        # A plain page load must never contact Apple. Each sign-in attempt
        # counts against a rate limit that answers 409 on /signin/init once
        # tripped, and a reload -- or a browser prefetch -- would otherwise
        # spend one. The challenge is only fetched when the operator asks
        # for it, and a pending one is re-rendered rather than replaced so
        # a command already copied stays valid.
        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            pending_challenge = _PENDING_AUTH.get("fsa_challenge")
        if pending_challenge:
            LOGGER.info("Web UI security-key: re-rendering the pending challenge.")
            return _render_auth(security_key_blob=_pack_challenge(pending_challenge))
        return redirect(url_for("auth_form"))

    @app.route("/auth/security-key/start", methods=["POST"])
    def auth_security_key_start():
        """Ask Apple for a challenge. This is the only path that signs in."""
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        # Pressing the button twice must not spend a second sign-in.
        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            pending_challenge = _PENDING_AUTH.get("fsa_challenge")
        if pending_challenge:
            LOGGER.info("Web UI security-key: reusing the pending challenge.")
            return _render_auth(security_key_blob=_pack_challenge(pending_challenge))


        config = _load_current_config()
        username = None
        if config:
            try:
                username = config_parser.get_username(config=config)
            except (KeyError, AttributeError, TypeError):
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
            LOGGER.exception("Web UI security-key: keyring lookup raised")
            return (
                _render_auth(message=f"Keyring lookup failed: {e!s}", message_kind="err"),
                500,
            )
        if not password:
            return (
                _render_auth(
                    message="No password in keyring — submit one below first.",
                    message_kind="warn",
                ),
                400,
            )

        try:
            import icloudpy

            ceremony_dir = _ceremony_cookie_dir()
            api = icloudpy.ICloudPyService(
                apple_id=username,
                password=password,
                cookie_directory=ceremony_dir,
            )
        except Exception as e:
            _discard_ceremony_dir(locals().get("ceremony_dir"))
            LOGGER.exception("Web UI security-key: ICloudPyService raised")
            if _is_signin_throttled(e):
                return (
                    _render_auth(
                        message=(
                            "Apple is rate-limiting sign-ins for this account "
                            "and will not issue a challenge yet. Nothing is "
                            "wrong with your key — wait a while before trying "
                            "again, as each attempt extends the limit."
                        ),
                        message_kind="warn",
                    ),
                    429,
                )
            return (
                _render_auth(
                    message=f"Sign-in failed: {e!s}",
                    message_kind="err",
                ),
                400,
            )

        if not api.requires_2fa:
            _wake_sync_loop()
            return redirect(url_for("dashboard"))

        fsa = api.security_key_challenge
        if not fsa:
            return (
                _render_auth(
                    message=(
                        "Apple did not offer a security-key challenge. This "
                        "account may still use 6-digit codes — use the form below."
                    ),
                    message_kind="warn",
                ),
                400,
            )

        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            _PENDING_AUTH["api"] = api
            _PENDING_AUTH["username"] = username
            _PENDING_AUTH["password"] = password
            _PENDING_AUTH["stashed_at"] = time.monotonic()
            # Keep Apple's challenge string verbatim. It is echoed back in
            # the assertion and Apple compares it byte-for-byte, so a
            # re-encode differing only in base64 padding is rejected with a
            # 409 -- the signer's encoding must never be trusted here.
            stashed = dict(fsa)
            _PENDING_AUTH["fsa_challenge"] = stashed
            _PENDING_AUTH["cookie_dir"] = ceremony_dir

        _record_auth_method(username, "security_key")
        # Render exactly what was stashed. Handing over a different
        # challenge than the one being waited on costs a physical touch to
        # discover, so the two are deliberately the same object.
        return _render_auth(security_key_blob=_pack_challenge(stashed))

    @app.route("/auth/security-key", methods=["POST"])
    def auth_security_key_submit():
        """Finish the ceremony: submit the signed assertion to Apple.

        The assertion is bound to the ``scnt``/``X-Apple-ID-Session-Id``
        of the session stashed by the GET handler, so it must be
        submitted with that same session -- which is why the signer
        never needs the password and never talks to Apple itself.
        """
        rejection = _require_csrf()
        if rejection is not None:
            return rejection

        raw = request.form.get("assertion", "").strip()
        if not raw:
            return (
                _render_auth(message="Paste the signer output.", message_kind="err"),
                400,
            )
        try:
            decoded = json.loads(base64.b64decode(raw))
        except Exception:
            return (
                _render_auth(
                    message="That does not look like signer output — copy the whole line.",
                    message_kind="err",
                ),
                400,
            )

        # The signer emits one assertion per candidate origin, because the
        # origin is fixed inside clientData at signing time and Apple rejects
        # a wrong one with the same opaque 409 it uses for everything else.
        signatures = decoded if isinstance(decoded, list) else [decoded]
        # Valid base64 JSON that is not signer output (``[]``, ``["x"]``)
        # must get the same answer as garbage, not a traceback.
        if not signatures or not all(isinstance(sig, dict) for sig in signatures):
            return (
                _render_auth(
                    message="That does not look like signer output — copy the whole line.",
                    message_kind="err",
                ),
                400,
            )

        with _AUTH_LOCK:
            _expire_stale_pending_auth_unlocked()
            api = _PENDING_AUTH.get("api")
            username = _PENDING_AUTH.get("username")
            password = _PENDING_AUTH.get("password")
            pending_fsa = _PENDING_AUTH.get("fsa_challenge") or {}
            ceremony_dir = _PENDING_AUTH.get("cookie_dir")
            issued_challenge = pending_fsa.get("challenge")
        if api is None:
            return (
                _render_auth(
                    message=("Challenge expired — start a new security-key re-auth and sign the fresh challenge."),
                    message_kind="err",
                ),
                400,
            )

        # Apple compares the echoed challenge byte-for-byte, and the signer
        # round-trips it through raw bytes, so it can come back re-encoded
        # (base64 padding Apple did not send). Compare on the decoded value
        # and submit the stashed original.
        #
        # A genuine mismatch means the signed challenge is not the one this
        # session is waiting on -- almost always a stale page, since every
        # page load starts a fresh Apple session with a fresh challenge.
        # Overwriting it here would hide that and produce an assertion whose
        # clientData disagrees with its challenge field, which Apple rejects
        # with an opaque 409. Say so instead.
        if issued_challenge:
            signed = str(signatures[0].get("challenge") or "")
            if _same_challenge(signed, issued_challenge):
                for signature in signatures:
                    signature["challenge"] = issued_challenge
            else:
                LOGGER.warning(
                    "Web UI security-key: signed challenge does not match the "
                    "pending one -- stale page.",
                )
                with _AUTH_LOCK:
                    _clear_pending_auth_unlocked()
                return (
                    _render_auth(
                        message=(
                            "That signature is for an older challenge. Each time "
                            "this page loads it starts a new one — reload, copy "
                            "the command again, and re-sign."
                        ),
                        message_kind="err",
                    ),
                    400,
                )

        try:
            if not api.confirm_security_key(assertion=signatures[0]):
                LOGGER.warning("Web UI security-key: Apple refused the assertion.")
                return (
                    _render_auth(
                        message=(
                            "Apple refused that signature. Reload to start a "
                            "fresh challenge and sign again."
                        ),
                        message_kind="err",
                    ),
                    400,
                )

            try:
                from icloudpy import utils as icloudpy_utils

                icloudpy_utils.store_password_in_keyring(
                    username=username,
                    password=password,
                )
            except Exception as e:
                LOGGER.warning(f"Web UI security-key keyring persist failed: {e!s}")

            if ceremony_dir:
                _publish_ceremony_session(ceremony_dir)
            # Apple accepting the assertion is not proof the sync loop can
            # sign in, and claiming success without checking is how a broken
            # session got reported as working before.
            if not _session_authenticates(username):
                LOGGER.warning(
                    "Web UI security-key: assertion accepted but sign-in still "
                    "wants a factor.",
                )
                return (
                    _render_auth(
                        message=(
                            "Apple accepted your key, but sign-in still asks for "
                            "a second factor. Start over and sign a fresh "
                            "challenge."
                        ),
                        message_kind="err",
                    ),
                    400,
                )
            LOGGER.info("Web UI: security-key re-auth succeeded; session trusted.")
            _wake_sync_loop()
            # The signer clears the clipboard itself once the signature is
            # read, so there is nothing left for the dashboard to do here.
            return redirect(url_for("dashboard"))
        except Exception as e:
            LOGGER.exception("Web UI security-key: assertion submit raised")
            return (
                _render_auth(message=f"Assertion submit failed: {e!s}", message_kind="err"),
                400,
            )
        finally:
            _discard_ceremony_dir(ceremony_dir)
            with _AUTH_LOCK:
                _clear_pending_auth_unlocked()

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
            _clear_pending_auth_unlocked()
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
                    message=("No password in keyring — submit one below to complete the first-time auth."),
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
                        f"Refresh trust failed: {e!s}. Your stored password may be stale — submit a new one below."
                    ),
                    message_kind="err",
                ),
                400,
            )

        if not api.requires_2fa:
            # Trust window was still alive — nothing to do, sync loop is
            # already authenticated. Bounce back to the dashboard with
            # the success state.
            _wake_sync_loop()
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

        service = (request.form.get("service") or request.args.get("service") or "").strip().lower()
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

        queued = [svc for svc in wanted if svc in configured and web_signals.request_force_sync(svc)]

        # Browser form submit gets a redirect; API consumers (curl,
        # monitors) get JSON. Distinguished by Accept header.
        if request.headers.get("Accept", "").startswith("application/json"):
            return jsonify({"queued": queued})
        return redirect(url_for("dashboard"))

    return app


_SIGNER_PATH = os.path.join(os.path.dirname(__file__), "icloud_sign.py")


def _lookup_auth_method(status_payload: dict[str, Any]) -> str | None:
    """Recorded second factor for the configured account, if we've seen one.

    Drives which route the auth page leads with: an account Apple has
    answered with an ``fsaChallenge`` can never complete the 6-digit
    form, so offering it first just wastes the operator's time.
    """
    username = status_payload.get("username") if status_payload else None
    if not username:
        return None
    try:
        from src import web_signals

        return web_signals.get_auth_method(username)
    except Exception:  # pragma: no cover - never break rendering over state
        return None


def _record_auth_method(username: str, method: str) -> None:
    """Persist the account's second factor; never fatal to the auth flow."""
    try:
        from src import web_signals

        web_signals.record_auth_method(username=username, method=method)
    except Exception as e:  # pragma: no cover - bookkeeping must not break auth
        LOGGER.warning(f"Web UI: recording auth method failed: {e!s}")


def _pack_challenge(fsa: dict[str, Any]) -> str:
    """Pack the challenge + credential handles into one short token.

    Length matters: the operator copies this inside a single shell
    command. Packing raw bytes (2-byte length prefix each) rather than
    base64-of-JSON roughly halves it, and ``rpId`` is dropped entirely
    because Apple's is always ``apple.com``.
    """

    def decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    parts = [decode(fsa["challenge"])]
    parts.extend(decode(handle) for handle in fsa["keyHandles"])
    packed = b"".join(struct.pack("!H", len(part)) + part for part in parts)
    return base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")


def _build_signer_command(blob: str) -> str:
    """The self-contained form: the signer source travels inside the command.

    Piped to ``uv run`` on stdin, so nothing is left on the operator's disk
    and the machine holding the key needs no network route back to this
    container. Always offered, because the short form below cannot reach a
    dashboard that sits behind proxy authentication.
    """
    try:
        with open(_SIGNER_PATH, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return "src/icloud_sign.py is missing from this image."
    return f"uv run --quiet - {blob} <<'ICLOUDSIGN'\n{source}ICLOUDSIGN"


_SIGNER_REPO_RAW = "https://raw.githubusercontent.com/mandarons/icloud-docker"


def _signer_source_ref() -> str | None:
    """The release tag this image was built from, e.g. ``v1.29.0``.

    Release images are built from ``v*`` tags and carry the version in
    ``APP_VERSION``. Development and PR builds (``dev``, ``pr-123``) have no
    tag to point at, so they get None.
    """
    version = os.environ.get("APP_VERSION", "").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None
    return f"v{version}"


def _build_short_signer_command(blob: str) -> str | None:
    """``uv run <signer at this release's tag> <blob>`` -- one line.

    Fetched from the public repo at the tag this image was built from:
    reachable from any machine (a dashboard behind an auth proxy, as one
    accepting an Apple ID password should be, cannot be fetched by uv), and
    readable before running. The signer declares its fido2 dependency inline
    (PEP 723), so no ``--with`` is needed.

    None for a build that is not a release; the self-contained form is then
    the only one offered.
    """
    ref = _signer_source_ref()
    if ref is None:
        return None
    return f"uv run --quiet {_SIGNER_REPO_RAW}/{ref}/src/icloud_sign.py {blob}"


def _session_authenticates(username: str) -> bool:
    """Confirm the sync loop can now sign in.

    Apple accepting the assertion is not the same as the loop being able
    to authenticate, and reporting success on the submit alone once
    announced a session that still wanted a second factor.
    """
    try:
        import icloudpy
        from icloudpy import utils as icloudpy_utils

        api = icloudpy.ICloudPyService(
            apple_id=username,
            password=icloudpy_utils.get_password_from_keyring(username),
            cookie_directory=DEFAULT_COOKIE_DIRECTORY,
        )
    except Exception as e:
        LOGGER.warning(f"Web UI: session failed to authenticate: {e!s}")
        return False
    LOGGER.info(f"Web UI: session check -> requires_2fa={api.requires_2fa}")
    return not api.requires_2fa


def _same_challenge(left: str, right: str) -> bool:
    """Compare two base64 challenge strings by value, not spelling.

    Apple emits the standard alphabet unpadded; a round-trip through raw
    bytes can come back padded, or urlsafe. Those are the same challenge.
    """

    def decode(value: str) -> bytes | None:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, TypeError):
            return None

    decoded = decode(left)
    return decoded is not None and decoded == decode(right)


def _is_signin_throttled(error: Exception) -> bool:
    """True when Apple refused to start a sign-in rather than to finish one.

    Apple answers a rate-limited account with 409 on ``/signin/init``, the
    very first SRP call, so no challenge can be issued at all. Worth
    distinguishing: it is not a bad password, a bad key, or a bad
    assertion, and retrying is what prolongs it.
    """
    text = str(error)
    return "signin/init" in text and "409" in text


def _ceremony_cookie_dir() -> str:
    """A private, empty cookie jar for one security-key ceremony.

    icloudpy loads its jar with ``ignore_expires=True``, so cookies from a
    dead session are replayed on every new sign-in -- an expired
    ``X-APPLE-WEBAUTH-TOKEN`` and friends arriving alongside a fresh SRP
    handshake. Apple's reply to that contradiction is 409 Conflict, which
    is exactly what the assertion submit kept receiving.

    The ceremony therefore runs against its own jar and publishes the
    result only once Apple has accepted it.
    """
    return tempfile.mkdtemp(prefix="icloud-securitykey-")


def _publish_ceremony_session(cookie_dir: str) -> None:
    """Move a ceremony's session files into the directory sync reads.

    Called only after Apple accepts the assertion and the session is
    trusted, so a failed attempt can never damage a working session. The
    previous files are kept alongside with a ``.bak`` suffix.
    """
    try:
        os.makedirs(DEFAULT_COOKIE_DIRECTORY, exist_ok=True)
        for name in os.listdir(cookie_dir):
            source = os.path.join(cookie_dir, name)
            target = os.path.join(DEFAULT_COOKIE_DIRECTORY, name)
            if os.path.exists(target):
                shutil.copy2(target, f"{target}.bak")
            shutil.copy2(source, target)
        LOGGER.info(f"Web UI: published ceremony session to {DEFAULT_COOKIE_DIRECTORY}.")
    except OSError:
        LOGGER.exception("Web UI: could not publish ceremony session")


def _discard_ceremony_dir(cookie_dir: str | None) -> None:
    """Remove a ceremony's private jar. Best-effort."""
    if cookie_dir:
        shutil.rmtree(cookie_dir, ignore_errors=True)


def _render_auth(
    message: str | None = None,
    message_kind: str | None = None,
    security_key_blob: str | None = None,
):
    """Render auth.html with the current pending state and an optional
    error/info pill. Factored out so the POST endpoints can reuse it.

    ``security_key_blob`` carries the base64 challenge bundle for the
    FIDO2 ceremony; when set the template shows the signer instructions
    instead of the 6-digit code form."""
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
        security_key_blob=security_key_blob,
        signer_command=_build_signer_command(security_key_blob) if security_key_blob else None,
        signer_source_ref=_signer_source_ref(),
        signer_command_short=(
            _build_short_signer_command(security_key_blob)
            if security_key_blob
            else None
        ),
        auth_method=_lookup_auth_method(status_payload),
    )


def start_in_thread(
    host: str = "127.0.0.1",
    port: int = 8080,
) -> threading.Thread:
    """Launch the Flask app on a daemon thread.

    The main sync loop owns the process; the web thread dies when the
    parent process exits. Returns the thread, or ``None`` if the port
    could not be bound (the sync loop continues regardless).

    Uses ``werkzeug.serving.make_server`` rather than ``Flask.run()``:
    binding happens synchronously here so a port conflict is reported
    as an error instead of a false "listening" line, and it avoids the
    dev-server banner. Deliberately dependency-free (no gunicorn) --
    this is a single-user, behind-a-proxy operator console (default
    host 127.0.0.1), not a public-facing API.
    """
    app = create_app()

    # Bind in the main thread so the "listening" log is truthful: a port
    # conflict raises here and is reported as a failure, instead of the
    # old optimistic log racing a background bind error.
    try:
        server = make_server(host, port, app, threaded=True)
    except OSError as e:
        LOGGER.error(f"Web UI failed to bind {host}:{port} — {e!s}")
        return None

    def _serve_bound():
        try:
            server.serve_forever()
        except Exception as e:  # noqa: BLE001 -- daemon thread, never crash the sync loop
            LOGGER.error(f"Web UI server stopped: {e!s}")

    thread = threading.Thread(target=_serve_bound, name="icloud-web-ui", daemon=True)
    thread.start()
    LOGGER.info(f"Web UI listening on http://{host}:{port}/ (host={host}, port={port})")
    return thread
