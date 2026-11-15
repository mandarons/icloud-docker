"""Signing a household member's Apple ID in, from a browser at the dashboard.

The operator opens the member's page and taps Sign in here (or hands the
member their laptop): the member types their password and the code from
their phone, and the account's session is saved in its own folder
(``src.accounts.cookie_directory``). The password is not saved anywhere.

The pages live under ``/sign-in`` on the dashboard and carry their own
short session cookie, which says which account this browser is signing in.
``start_session`` begins one; nothing else does.
"""

import hashlib
import hmac
import os
import re
import secrets
import shutil
import threading
import time
from typing import Any

from flask import Blueprint, Flask, redirect, render_template, request, session, url_for

from src import accounts, config_parser, get_logger

LOGGER = get_logger()

_SESSION_SECONDS = 30 * 60
_PENDING_SECONDS = 10 * 60
# Failed passwords allowed per account per hour. Apple locks an Apple ID
# after repeated failures; this page must not be a way to do that.
_MAX_PASSWORD_FAILURES = 3
_FAILURE_WINDOW_SECONDS = 60 * 60
_MAX_CODE_TRIES = 3

_LOCK = threading.Lock()
_PENDING: dict[str, dict[str, Any]] = {}
# When each account last finished a code check, so a duplicate submit that
# arrives just after (the first already took the pending entry) still lands
# on the done page instead of "That took too long".
_FINISHED: dict[str, float] = {}
_FINISHED_SECONDS = 60
_FAILURES: dict[str, list[float]] = {}



def _secret_path() -> str:
    return os.path.join(accounts.config_dir(), ".web-secret")


def _secret() -> bytes:
    """The signing secret, made on first use and readable only by this user."""
    path = _secret_path()
    with _LOCK:
        try:
            with open(path, encoding="utf-8") as f:
                return bytes.fromhex(f.read().strip())
        except FileNotFoundError:
            pass
        value = secrets.token_bytes(32)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(value.hex())
        # The create mode alone isn't enough where an inherited ACL or
        # umask-ignoring share widens new files (Synology volumes do).
        os.chmod(path, 0o600)
        return value


def _failures_in_window(account_id: str, now: float) -> list[float]:
    recent = [t for t in _FAILURES.get(account_id, []) if now - t < _FAILURE_WINDOW_SECONDS]
    _FAILURES[account_id] = recent
    return recent


def _record_failure(account_id: str) -> None:
    with _LOCK:
        _failures_in_window(account_id, time.time()).append(time.time())


def _locked_out(account_id: str) -> bool:
    with _LOCK:
        return len(_failures_in_window(account_id, time.time())) >= _MAX_PASSWORD_FAILURES


def _pending(account_id: str) -> dict[str, Any] | None:
    with _LOCK:
        entry = _PENDING.get(account_id)
        if entry and time.monotonic() - entry["at"] > _PENDING_SECONDS:
            _PENDING.pop(account_id, None)
            entry = None
        return entry


def _load_config() -> dict | None:
    from src import web

    return web._load_current_config()  # noqa: SLF001 - same reader as the dashboard


def _current_account() -> accounts.Account | None:
    """The account this browser's session is for, if still valid."""
    account_id = session.get("account")
    if not account_id or session.get("expires", 0) < time.time():
        return None
    return accounts.get_account(_load_config(), account_id)


def _csrf_ok() -> bool:
    expected = session.get("csrf")
    submitted = request.form.get("csrf_token", "")
    return bool(expected) and hmac.compare_digest(expected, submitted)


def session_key() -> bytes:
    """Key that signs the sign-in session cookie."""
    return hmac.new(_secret(), b"sign-in-session", hashlib.sha256).digest()


def _review_first(account) -> bool:
    """Whether the operator looks at a report before this member's first backup."""
    config = _load_config()
    if not account or not config:
        return False
    return bool(config_parser.get_photos_adopt(config=accounts.member_config(config, account)))


def _with_drive(account) -> bool:
    """Whether this member's iCloud Drive is backed up too, so the page says so."""
    config = _load_config()
    return bool(account and config and accounts.drive_enabled(config, account))


def _page(account, *, state, message=None, kind=None, status=200, refused=False, username=""):
    own_page = bool(session.get("own_page"))
    return (
        render_template(
            "signin.html",
            state=state,
            apple_id=account.username if account and account.username else None,
            ask_username=bool(account) and not account.username,
            message=message,
            kind=kind,
            review_first=state == "done" and _review_first(account),
            own_page=own_page,
            back_to=session.get("back_to") or "/",
            refused=refused,
            what="photos and iCloud Drive files" if _with_drive(account) else "photos",
            csrf_token=session.get("csrf", ""),
            username=username,
        ),
        status,
    )


blueprint = Blueprint("signin", __name__)


@blueprint.after_request
def _headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def start_session(account_id: str, *, own_page: bool = False, back_to: str = "/") -> None:
    """Start this browser's sign-in for an account.

    ``own_page`` means whoever is here may see the Apple ID in full (the
    operator at the dashboard, or a member on their own page); ``back_to``
    is where the done page leads.
    """
    session.clear()
    session.permanent = False
    session["account"] = account_id
    session["expires"] = time.time() + _SESSION_SECONDS
    session["csrf"] = secrets.token_urlsafe(24)
    if own_page:
        session["own_page"] = True
        session["back_to"] = back_to


@blueprint.route("/sign-in", methods=["GET"])
def page():
    account = _current_account()
    if account is None:
        return _page(None, state="invalid", status=403)
    if session.get("done"):
        return _page(account, state="done")
    if _pending(account.id):
        return _page(account, state="code")
    return _page(account, state="password")


_APPLE_ID = re.compile(r"^[^@]+@[^@]+\.[a-z]{2,}$")
# Pasted or autofilled addresses can carry spaces and invisible characters
# that Apple reads as part of the Apple ID.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))


def _apple_error_codes(error: Exception) -> str:
    """Apple's serviceErrors codes from a failed response, for the log (no personal data)."""
    try:
        errors = error.response.json().get("serviceErrors") or []
    except Exception:  # noqa: BLE001 - no body, or not JSON
        return ""
    codes = ",".join(str(e.get("code")) for e in errors if isinstance(e, dict))
    return f"(Apple codes: {codes})" if codes else ""


def _clean_apple_id(raw: str) -> str:
    return "".join(raw.translate(_INVISIBLE).split()).lower()


def _entered_username(account, config) -> tuple[str | None, str | None]:
    """The Apple ID to sign in: the pinned one, or what the member typed.

    Returns ``(username, error)``.
    """
    if account.username:
        return account.username, None
    typed = clean_apple_id(request.form.get("username") or "")
    if typed is None:
        return None, "Enter your Apple ID (the email you sign in to iCloud with)."
    if apple_id_taken(typed, account.id, config):
        return None, "That Apple ID is already backed up here."
    return typed, None


def apple_id_taken(apple_id: str, account_id: str, config) -> bool:
    """True when the main account or another member already backs up this Apple ID."""
    main = (config_parser.get_username(config=config) or "").lower() if config else ""
    if apple_id.lower() == main:
        return True
    return any(
        a.id != account_id and (a.username or "").lower() == apple_id.lower() for a in accounts.get_accounts(config)
    )


def clean_apple_id(raw: str) -> str | None:
    """The Apple ID with stray spaces dropped, or None when it isn't an email."""
    typed = _clean_apple_id(raw)
    return typed if _APPLE_ID.match(typed) and len(typed) <= 254 else None


@blueprint.route("/sign-in/password", methods=["POST"])
def submit_password():
    account = _current_account()
    if account is None or not _csrf_ok():
        return _page(None, state="invalid", status=403)
    if _locked_out(account.id):
        return _page(
            account,
            state="locked",
            message="Too many tries, so this page waits an hour; that keeps Apple from locking your Apple ID.",
            kind="err",
            status=429,
            refused=True,
        )
    username, error = _entered_username(account, _load_config())
    password = request.form.get("password", "")
    if error or not password:
        if error:
            LOGGER.info(
                f"Member sign-in: account {account.id} entered an Apple ID the page turned back: {error.split(' ')[0]}",
            )
        message = error or "Enter your Apple ID password."
        typed = username or (request.form.get("username") or "").strip()
        return _page(account, state="password", message=message, kind="err", status=400, username=typed)

    from icloudpy import ICloudPyService, exceptions

    # Sign in beside the saved session, not into it: a refused password or
    # an unfinished code would otherwise leave files that read as signed in.
    directory = _staging(account.id)
    shutil.rmtree(directory, ignore_errors=True)
    os.makedirs(directory, mode=0o700)
    try:
        api = ICloudPyService(apple_id=username, password=password, cookie_directory=directory)
    except exceptions.ICloudPyFailedLoginException as e:
        shutil.rmtree(directory, ignore_errors=True)
        _record_failure(account.id)
        step = e.args[0] if e.args else ""
        LOGGER.warning(
            f"Member sign-in: Apple refused the sign-in for account {account.id}: {step} {_apple_error_codes(e.__cause__ or e)}",
        )
        return _page(
            account,
            state="password",
            message="Apple didn't accept that Apple ID and password.",
            kind="err",
            status=400,
            refused=True,
            username=username,
        )
    except Exception as e:  # noqa: BLE001 - the page reports, the member retries later
        shutil.rmtree(directory, ignore_errors=True)
        LOGGER.warning(f"Member sign-in: sign-in for account {account.id} failed: {e!s} {_apple_error_codes(e)}")
        # Apple answering 4xx before the password check (a mistyped Apple ID
        # fails signin/init with 400) is a refusal, not an outage. Never 502:
        # proxies such as Cloudflare swap a 502 page for their own error.
        status = getattr(getattr(e, "response", None), "status_code", None)
        if isinstance(status, int) and 400 <= status < 500:
            return _page(
                account,
                state="password",
                message="Apple didn't accept that Apple ID and password.",
                kind="err",
                status=400,
                refused=True,
                username=username,
            )
        return _page(
            account,
            state="password",
            message="Couldn't reach Apple just now. Try again in a few minutes.",
            kind="err",
            status=503,
            username=username,
        )

    if api.requires_2fa:
        _send_code(account, api)
        with _LOCK:
            _PENDING[account.id] = {
                "api": api,
                "at": time.monotonic(),
                "tries": 0,
                "username": username,
                "lock": threading.Lock(),
                "finished": False,
            }
        return redirect(url_for("signin.page"))

    _finish(account, username)
    return redirect(url_for("signin.page"))


def _staging(account_id: str) -> str:
    """Where a sign-in in progress keeps its session until it completes."""
    return accounts.cookie_directory(account_id) + ".signing-in"


def _finish(account, username: str) -> None:
    """Record a completed sign-in: its session replaces the saved one, and
    the Apple ID is pinned to this account."""
    saved = accounts.cookie_directory(account.id)
    shutil.rmtree(saved, ignore_errors=True)
    os.replace(_staging(account.id), saved)
    if not account.username:
        accounts.pin_username(account.id, username)
    session["done"] = True
    LOGGER.info(f"Member sign-in: account {account.id} signed in")
    from src import member_sync

    member_sync.wake()


def _send_code(account, api) -> None:
    """Ask Apple to show a code on the member's devices."""
    try:
        trigger = getattr(api, "trigger_2fa_push_notification", None)
        if callable(trigger):
            trigger()
    except Exception as e:  # noqa: BLE001 - a code can still arrive another way
        LOGGER.warning(f"Member sign-in: 2FA push for account {account.id} failed: {e!s}")


@blueprint.route("/sign-in/resend", methods=["POST"])
def resend():
    account = _current_account()
    if account is None or not _csrf_ok():
        return _page(None, state="invalid", status=403)
    entry = _pending(account.id)
    if entry is None:
        return _page(account, state="password", message="That took too long. Start again.", kind="err", status=400)
    _send_code(account, entry["api"])
    with _LOCK:
        entry["at"] = time.monotonic()
    return _page(account, state="code", message="New code sent.", kind="ok")


@blueprint.route("/sign-in/code", methods=["POST"])
def submit_code():
    account = _current_account()
    if account is None or not _csrf_ok():
        return _page(None, state="invalid", status=403)
    entry = _pending(account.id)
    if entry is None:
        with _LOCK:
            finished = time.monotonic() - _FINISHED.get(account.id, -_FINISHED_SECONDS) < _FINISHED_SECONDS
        if finished:
            session["done"] = True
            return redirect(url_for("signin.page"))
        return _page(
            account,
            state="password",
            message="That took too long. Start again.",
            kind="err",
            status=400,
        )
    code = re.sub(r"\D", "", request.form.get("code", ""))
    if len(code) != 6:
        return _page(account, state="code", message="Enter the 6-digit code.", kind="err", status=400)
    # Apple takes seconds to check a code, and a second tap (or autofill
    # submitting as well) used to land mid-check and report the code wrong
    # after it had worked. One check at a time; a late one sees it finished.
    with entry["lock"]:
        if entry["finished"]:
            session["done"] = True
            return redirect(url_for("signin.page"))
        return _check_code(account, entry, code)


def _check_code(account, entry, code):
    try:
        accepted = entry["api"].validate_2fa_code(code)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning(f"Member sign-in: code check for account {account.id} failed: {e!s}")
        accepted = False
    if not accepted:
        with _LOCK:
            entry["tries"] += 1
            if entry["tries"] >= _MAX_CODE_TRIES:
                _PENDING.pop(account.id, None)
                return _page(
                    account,
                    state="password",
                    message="That code didn't work. Start again with your password.",
                    kind="err",
                    status=400,
                )
        return _page(
            account,
            state="code",
            message="That code didn't work. Try the newest one.",
            kind="err",
            status=400,
        )
    try:
        entry["api"].trust_session()
    except Exception as e:  # noqa: BLE001 - the sign-in itself worked
        LOGGER.warning(f"Member sign-in: trusting the session for account {account.id} failed: {e!s}")
    _finish(account, entry["username"])
    entry["finished"] = True
    # Record the finish before dropping the pending entry: a second submit
    # in between would otherwise find neither and say it took too long.
    with _LOCK:
        _FINISHED[account.id] = time.monotonic()
        _PENDING.pop(account.id, None)
    return redirect(url_for("signin.page"))


def configure_session(app: Flask, secure_cookie: bool = False) -> None:
    """Give an app the session cookie the sign-in pages rely on."""
    app.secret_key = session_key()
    app.config.update(
        SESSION_COOKIE_NAME="sign_in_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookie,
    )
