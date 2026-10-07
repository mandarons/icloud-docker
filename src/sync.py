"""Sync module."""

__author__ = "Mandar Patil <mandarons@pm.me>"
import datetime
import os
import re
import secrets
from time import sleep

import requests
from icloudpy import ICloudPyService, exceptions, utils

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_RETRY_LOGIN_INTERVAL_SEC,
    ENV_CONFIG_FILE_PATH_KEY,
    ENV_ICLOUD_PASSWORD_KEY,
    PHOTOS_INDEXING_RETRY_SEC,
    config_parser,
    configure_icloudpy_logging,
    get_logger,
    notify,
    read_config,
    sync_drive,
    sync_photos,
)
from src.sync_stats import SyncSummary
from src.usage import alive

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


_TRUST_COOKIE_NAME = "X-APPLE-WEBAUTH-HSA-TRUST"


def _detect_security_key_account(api, username: str) -> bool:
    """True when Apple answers this account's second factor with an fsaChallenge.

    Once security keys are enrolled Apple stops issuing 6-digit codes
    altogether, so requesting a push sends nothing and listening for a
    replied code waits for something that cannot arrive -- the loop did
    both, every cycle, and told the user over Telegram to "reply the
    6-digit code here". Detecting it here rather than waiting for someone
    to open the dashboard is what lets the very first notification tell
    the truth.

    Recording the method also means ``notify`` picks the security-key
    wording on this same pass, since it reads the same signal.

    Best-effort in both directions: icloudpy without security-key support
    has no such attribute, and no probe failure may break the retry loop.
    """
    try:
        challenge = getattr(api, "security_key_challenge", None)
    except Exception as e:  # noqa: BLE001 - a probe must never break the loop
        LOGGER.debug(f"security-key probe failed: {e!s}")
        return False
    # Shape, not truthiness. icloudpy returns a mapping carrying "challenge"
    # and "keyHandles", or None -- anything else (a stub, a changed API, a
    # sentinel) must not be mistaken for Apple demanding a key, because the
    # cost of a false positive is suppressing the real code flow.
    if not (isinstance(challenge, dict) and challenge.get("challenge")):
        return False
    try:
        from src import web_signals

        web_signals.record_auth_method(username=username, method="security_key")
    except Exception as e:  # noqa: BLE001 - wording is not worth an outage
        LOGGER.debug(f"could not record auth method: {e!s}")
    return True


def _log_trust_revocation_hint(api) -> None:
    """Say so when Apple rejected a trust token that has not expired.

    Expiry and revocation are indistinguishable from the logs -- both
    surface as 421 and both end with a 2FA prompt -- but they mean
    opposite things for what to do next. A refresh schedule prevents the
    first and can do nothing about the second: Apple drops trust on
    security events, typically a new trusted device, a password change,
    or a change to security keys.

    Without this, the obvious reading of "valid trust token, 2FA demanded
    anyway" is that the refresh logic is broken, and the time goes into
    auditing code that behaved correctly.

    Best-effort: never raises into the retry path.
    """
    try:
        expires_at = _read_trust_cookie_expiry(api)
        if expires_at is None:
            return
        remaining = (
            expires_at - datetime.datetime.now(tz=datetime.timezone.utc)
        ).days
        if remaining <= 0:
            return
        LOGGER.error(
            f"The trust token had not expired -- it is valid for {remaining} "
            f"more days (until {expires_at.date()}). Apple revoked it "
            f"server-side, which typically follows a new trusted device, a "
            f"password change, or a change to security keys.",
        )
    except Exception as e:  # noqa: BLE001 - diagnostics never break the retry
        LOGGER.debug(f"trust revocation hint failed: {e!s}")


def _read_trust_cookie_expiry(api) -> datetime.datetime | None:
    """Return the expiry datetime of Apple's HSA trust cookie, or None.

    The trust window is carried by ``X-APPLE-WEBAUTH-HSA-TRUST`` in
    icloudpy's cookie jar (persisted to ``session_data/<username>`` as
    LWPCookieJar). Reading it directly avoids hardcoding Apple's trust
    duration -- the cookie's own ``expires`` field is the source of
    truth, set per-cookie by Apple's server. Returns None if the cookie
    isn't present (e.g. account never auth'd with 2FA, or trust cookie
    cleared).
    """
    try:
        cookies = api.session.cookies
    except AttributeError:
        return None
    for cookie in cookies:
        if cookie.name == _TRUST_COOKIE_NAME and cookie.expires:
            return datetime.datetime.fromtimestamp(
                cookie.expires,
                tz=datetime.timezone.utc,
            )
    return None


# Set once the missing-public_url guidance has been logged (see
# ``_resolve_dashboard_url``) so the advice appears once per process,
# not once per sync-loop iteration.
_WEB_UI_PUBLIC_URL_WARNED = False

# Minimum wait after a failed sign-in. Apple answers a throttled account
# with 409 on /signin/init; retrying sooner just extends the lockout.
_AUTH_BACKOFF_FLOOR_SEC = 1800


def _resolve_dashboard_url(config) -> str | None:
    """Compute the web UI URL to embed in notifications, or None.

    Returns ``None`` when ``app.web_ui.enabled`` is False -- callers
    fall back to the legacy docker-exec instruction. Otherwise prefers
    the explicit ``app.web_ui.public_url`` (e.g. the reverse-proxy
    URL); falls back to ``http://{host}:{port}`` with a warning logged
    once at startup if the public URL isn't set.
    """
    if not config_parser.get_web_ui_enabled(config=config):
        return None
    public_url = config_parser.get_web_ui_public_url(config=config)
    if public_url:
        return public_url
    host = config_parser.get_web_ui_host(config=config)
    port = config_parser.get_web_ui_port(config=config)
    # Latch: this resolves on every sync-loop iteration, and while the
    # container sits 2FA-pending (default 600s retry) that is ~144x/day
    # of identical guidance in the exact scenario the user is watching
    # the logs. The advice only needs saying once per process.
    global _WEB_UI_PUBLIC_URL_WARNED
    if not _WEB_UI_PUBLIC_URL_WARNED:
        LOGGER.warning(
            "app.web_ui.public_url not set -- notification URLs will use "
            "http://%s:%s/, which won't work from outside the container. "
            "Set app.web_ui.public_url to your reverse-proxy URL.",
            host,
            port,
        )
        _WEB_UI_PUBLIC_URL_WARNED = True
    return f"http://{host}:{port}"


def _publish_auth_blocked(blocked: bool, reason: str | None = None) -> None:
    """Tell the web UI whether the loop can authenticate.

    Only this loop knows: every on-disk signal the dashboard can check by
    itself (username configured, password in the keyring) still looks
    healthy while an account sits stuck on a second factor.

    Best-effort -- signalling must never break syncing.
    """
    try:
        from src import web_signals

        web_signals.record_auth_blocked(blocked=blocked, reason=reason)
    except Exception as e:  # pragma: no cover - signalling is advisory
        LOGGER.warning(f"Could not publish auth state: {e!s}")


def _maybe_refresh_trust(config, api) -> None:
    """Re-trust the session before its token ages out.

    ``trust_session`` asks Apple for a new ``X-Apple-TwoSV-Trust-Token``
    and icloudpy persists it to ``session_data``. Calling it while the
    session is still healthy therefore rolls the window forward, so a
    restart at any later point finds a young token and resumes without
    prompting for a second factor.

    This matters most for accounts where the second factor is expensive
    or impossible to satisfy headlessly (hardware security keys, where
    Apple refuses to send a 6-digit code at all).

    Best-effort: never raises into the sync loop.
    """
    try:
        threshold = config_parser.get_trust_refresh_days(config=config)
        if threshold <= 0:
            return
        expires_at = _read_trust_cookie_expiry(api)
        if expires_at is None:
            return
        days_remaining = (
            expires_at - datetime.datetime.now(tz=datetime.timezone.utc)
        ).days
        if days_remaining > threshold:
            return
        LOGGER.info(
            f"Trust token has {days_remaining}d left (threshold {threshold}d) -- refreshing.",
        )
        if api.trust_session():
            refreshed = _read_trust_cookie_expiry(api)
            expires_at_iso = refreshed.isoformat() if refreshed else None
            LOGGER.info(
                f"Trust refreshed; now expires {expires_at_iso or 'unknown'}.",
            )
            # Webhook-only: no other transport reports a refresh, and a
            # receiver tracking the trust window needs the new expiry as
            # much as it needs the warning that preceded it.
            refresh_data = {"days_remaining_before": days_remaining}
            if expires_at_iso:
                # Omitted rather than null when the cookie is unreadable.
                refresh_data["expires_at"] = expires_at_iso
            notify.post_event_to_webhook(
                config,
                "trust_refreshed",
                f"iCloud trust token refreshed; now expires {expires_at_iso or 'unknown'}",
                refresh_data,
            )
        else:
            LOGGER.warning(
                "Proactive trust refresh was declined by Apple -- a second "
                "factor will be needed at the next cold start.",
            )
    except Exception as e:  # pragma: no cover - never break sync over a refresh
        LOGGER.warning(f"trust refresh failed: {e!s}")


def _maybe_warn_trust_expiring(config, api, username: str) -> None:
    """Fire the trust-expiring notification once when crossing threshold.

    Reads the live trust cookie expiry, compares against
    ``app.trust_expiry_warn_days``, and -- if days_remaining is below
    the threshold AND we haven't already warned for THIS cookie value --
    fans the warning out through ``notify.send_trust_expiring``.

    Debounce key is the cookie expiry ISO string itself. When Apple
    refreshes the trust cookie (new expires_at), the stored
    ``warned_for_expires_at`` no longer matches and warning eligibility
    rearms automatically -- no manual reset needed.

    Best-effort: any exception is logged and swallowed so a notification
    bug never breaks the sync loop.
    """
    try:
        from src import notify, web_signals

        expires_at = _read_trust_cookie_expiry(api)
        expires_at_iso = expires_at.isoformat() if expires_at else None
        prior = web_signals.get_trust_state()
        web_signals.record_trust_state(
            expires_at_iso=expires_at_iso,
            warned_for_expires_at=prior.get("warned_for_expires_at"),
        )
        if expires_at is None:
            return
        days_remaining = (
            expires_at - datetime.datetime.now(tz=datetime.timezone.utc)
        ).days
        threshold = config_parser.get_trust_expiry_warn_days(config=config)
        if days_remaining >= threshold:
            return
        if prior.get("warned_for_expires_at") == expires_at_iso:
            return  # already warned for this cookie value
        notify.send_trust_expiring(
            config=config,
            username=username,
            days_remaining=days_remaining,
            dashboard_url=_resolve_dashboard_url(config),
        )
        web_signals.record_trust_state(
            expires_at_iso=expires_at_iso,
            warned_for_expires_at=expires_at_iso,
        )
    except Exception as e:  # pragma: no cover - guarded so notify bugs don't break sync
        LOGGER.warning(f"trust-expiring check failed: {e!s}")


_SESSION_ONLY_HELP = (
    "Store an Apple ID password to let the container re-authenticate on its "
    "own, or create a new session by signing in from the web dashboard or "
    "with the documented `icloud --username=... --session-directory=...` "
    "command."
)

# Apple answers a session it will no longer accept with one of these, and
# icloudpy surfaces the status as the exception's ``code``. Anything else --
# a 500, a 503, a bad gateway -- is an outage that says nothing about the
# session, so it belongs to the loop's transport handler rather than being
# reported to the user as "sign in again". (icloudpy itself lumps 500 in
# with the re-auth statuses when it rewrites the reason; that conflation
# must not reach the user as an instruction.)
_SESSION_REJECTED_CODES = frozenset({401, 421, 450})

# icloudpy reads the keyring for a ``None`` password -- the very lookup
# session-only mode exists to avoid -- and, given ``""``, its log filter
# rewrites every log line with asterisks between each character. A random
# placeholder avoids both; ``SessionOnlyICloudPyService`` never sends it.
_SESSION_ONLY_PLACEHOLDER_PASSWORD = secrets.token_urlsafe(32)


class SessionOnlyICloudPyService(ICloudPyService):
    """An iCloud client allowed to resume a saved session and nothing else.

    icloudpy's ``authenticate()`` tries the saved session token first and
    falls back to a full SRP sign-in when it does not validate. With no
    password that fallback cannot succeed, and letting it run would post a
    placeholder credential to Apple's sign-in endpoint on every retry --
    the fastest way to get an Apple ID throttled or locked. So this
    override stops after the session check and reports the missing
    password instead, which the loop's existing handler already turns into
    a notification and a backoff.
    """

    def authenticate(self, force_refresh=False, service=None):
        """Validate the saved session; never sign in with credentials.

        Raises ``ICloudPyNoStoredPasswordAvailableException`` when the
        session is missing or Apple has rejected it; any other API error
        propagates untouched, since an outage is not an expired session.

        ``force_refresh`` is refused as defence in depth rather than
        because anything here asks for it: icloudpy's only caller is its
        Find My 450 handler, which this app never reaches. Honouring it
        would mean a credential sign-in, which is the one thing this class
        exists to prevent, so it is refused wherever it came from.
        """
        if force_refresh or not self.session_data.get("session_token"):
            msg = f"No Apple ID password is stored and there is no saved session to resume. {_SESSION_ONLY_HELP}"
            raise exceptions.ICloudPyNoStoredPasswordAvailableException(msg)

        try:
            self.data = self._validate_token()
        except exceptions.ICloudPyAPIResponseException as error:
            if error.code not in _SESSION_REJECTED_CODES:
                # An outage leaves the session perfectly good; reporting it as
                # expired would send the user off to re-authenticate for
                # nothing. Let the loop's transport handler have it.
                raise
            msg = f"No Apple ID password is stored and the saved session is no longer valid. {_SESSION_ONLY_HELP}"
            raise exceptions.ICloudPyNoStoredPasswordAvailableException(msg) from error

        if "webservices" not in self.data:
            # icloudpy returns the response untouched when a failed /validate
            # carries no recognised error field, so ``self.data`` can be an
            # error body. Upstream would raise KeyError here and kill the
            # process -- with `restart: unless-stopped` that is a restart loop
            # hitting Apple on every boot.
            msg = f"No Apple ID password is stored and Apple did not accept the saved session. {_SESSION_ONLY_HELP}"
            raise exceptions.ICloudPyNoStoredPasswordAvailableException(msg)

        self._webservices = self.data["webservices"]
        LOGGER.debug("Resumed the saved session without a password")


def get_api_instance(
    username: str,
    password: str | None,
    cookie_directory: str | None = None,
    server_region: str = "global",
) -> ICloudPyService:
    """
    Create and return an iCloud API client instance.

    Args:
        username: iCloud username/Apple ID
        password: iCloud password, or ``None`` to run in session-only
            mode -- the client then resumes the saved session in
            ``cookie_directory`` and refuses to sign in with credentials
            (see ``SessionOnlyICloudPyService``).
        cookie_directory: Directory to store authentication cookies.
            When ``None`` (the default), resolved late from
            ``src.DEFAULT_COOKIE_DIRECTORY`` so test fixtures that
            redirect the constant at runtime take effect — the previous
            ``= DEFAULT_COOKIE_DIRECTORY`` default-arg capture made the
            constant unmockable post-import.
        server_region: Server region ("china" or "global")

    Returns:
        Configured ICloudPyService instance
    """
    if cookie_directory is None:
        # Read through the src module so monkey-patches of
        # ``src.DEFAULT_COOKIE_DIRECTORY`` (e.g. by tests/conftest.py)
        # are honoured. ``src`` is this function's parent package and
        # already imported; using ``sys.modules`` avoids a per-call
        # ``import src`` and makes the data flow explicit.
        import sys

        cookie_directory = sys.modules["src"].DEFAULT_COOKIE_DIRECTORY
    service_class = ICloudPyService
    if password is None:
        service_class = SessionOnlyICloudPyService
        password = _SESSION_ONLY_PLACEHOLDER_PASSWORD
    return (
        service_class(
            apple_id=username,
            password=password,
            cookie_directory=cookie_directory,
            home_endpoint="https://www.icloud.com.cn",
            setup_endpoint="https://setup.icloud.com.cn/setup/ws/1",
        )
        if server_region == "china"
        else service_class(
            apple_id=username,
            password=password,
            cookie_directory=cookie_directory,
        )
    )


class SyncState:
    """
    Maintains synchronization state for drive and photos.

    This class encapsulates the countdown timers and sync flags to avoid
    passing multiple variables between functions.
    """

    def __init__(self):
        """Initialize sync state with default values."""
        self.drive_time_remaining = 0
        self.photos_time_remaining = 0
        self.enable_sync_drive = True
        self.enable_sync_photos = True
        self.last_send = None
        # Whether a 2FA push has already been requested for the current
        # re-auth episode. Reset to False on each successful authentication so
        # a fresh episode triggers exactly one push (see _handle_2fa_required).
        self.two_fa_triggered = False
        # Whether this cycle is running without a stored password, i.e. off
        # the saved session alone. Set by _authenticate_and_get_api; the error
        # handlers need it because nothing in that mode can be fixed by
        # retrying with a password the container does not have.
        self.session_only = False
        # Set when this cycle skipped Photos because Apple is still indexing
        # it, so the cycle's webhook can say so rather than blame the mount.
        self.photos_indexing = False


def _load_configuration():
    """
    Load configuration from file or environment.

    Returns:
        Configuration dictionary
    """
    config_path = os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)
    return read_config(config_path=config_path)


def _extract_sync_intervals(config, log_messages: bool = False):
    """
    Extract drive and photos sync intervals from configuration.

    Args:
        config: Configuration dictionary
        log_messages: Whether to log informational messages (default: False for loop usage)

    Returns:
        tuple: (drive_sync_interval, photos_sync_interval)
    """
    drive_sync_interval = 0
    photos_sync_interval = 0

    if config and "drive" in config:
        drive_sync_interval = config_parser.get_drive_sync_interval(
            config=config,
            log_messages=log_messages,
        )
    if config and "photos" in config:
        photos_sync_interval = config_parser.get_photos_sync_interval(
            config=config,
            log_messages=log_messages,
        )

    return drive_sync_interval, photos_sync_interval


def _retrieve_password(username: str):
    """
    Retrieve password from environment or keyring.

    Args:
        username: iCloud username

    Returns:
        Password string or None if not found

    Raises:
        ICloudPyNoStoredPasswordAvailableException: If password not available
    """
    # A blank value counts as no password. Compose substitutes "" for an
    # unset ${VAR}, and storing it would also overwrite a real keyring
    # entry; returning it would skip session-only mode and send an empty
    # password to Apple's sign-in on every retry.
    password = os.environ.get(ENV_ICLOUD_PASSWORD_KEY)
    if password:
        utils.store_password_in_keyring(username=username, password=password)
        return password
    password = utils.get_password_from_keyring(username=username)
    if not password:
        msg = f"The stored password for {username} is empty."
        raise exceptions.ICloudPyNoStoredPasswordAvailableException(msg)
    return password


def _authenticate_and_get_api(config, username: str, sync_state: SyncState | None = None):
    """
    Authenticate user and return iCloud API instance.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state, whose ``session_only`` flag is set
            here so the error handlers can tell the two modes apart

    Returns:
        ICloudPyService instance

    Raises:
        ICloudPyNoStoredPasswordAvailableException: If no password is
            configured *and* the saved session cannot be resumed.
    """
    server_region = config_parser.get_region(config=config)
    try:
        password = _retrieve_password(username)
    except exceptions.ICloudPyNoStoredPasswordAvailableException:
        # No password anywhere is a choice, not necessarily a misconfiguration:
        # an operator who would rather not keep an Apple ID password on disk
        # can run unattended off the saved session alone until Apple's trust
        # window closes. Resuming it is worth attempting before declaring
        # failure -- the loop used to report "password is not stored" without
        # ever looking at a perfectly valid session.
        LOGGER.debug(
            "No Apple ID password is configured -- resuming the saved session.",
        )
        password = None
    if sync_state is not None:
        # Set before the client is built, so it is already right if building
        # it is what fails.
        sync_state.session_only = password is None
    return get_api_instance(
        username=username,
        password=password,
        server_region=server_region,
    )


def _check_mount_marker(
    destinations: list[str],
    marker_filename: str,
    required: bool,
    service_name: str,
) -> bool:
    """Verify the failsafe marker file is present in every write destination.

    Mirrors boredazfcuk/docker-icloudpd's ``.mounted`` pattern: protects
    against silent bind-mount failures (typo in the host path, missing
    share, wrong permissions) that would otherwise dump iCloud data into
    an empty container-internal directory.

    Takes a list of destinations because a single sync may write to more
    than one bind-mounted directory; the marker is required in EACH write
    destination because any one of them could be the failed mount.

    Returns True when it is safe to proceed (marker not required, or
    marker required and present in every destination). Returns False when
    the marker is required and is missing from at least one destination —
    in which case the caller should skip this sync cycle without
    advancing the countdown so the next interval re-checks. Every
    missing-marker failure is logged so the user can fix all of them in
    one pass rather than discovering them one cycle at a time.

    Args:
        destinations: List of sync destination directories to check. Each
            directory is checked independently. An empty list returns
            True (nothing to check).
        marker_filename: Filename to look for inside each destination
            (e.g. ``.mounted``).
        required: Whether the marker is required at all. When False this
            is a no-op that always returns True.
        service_name: Human-readable label used in the error log
            (``Drive`` / ``Photos``).

    Returns:
        True if it is safe to proceed; False to skip this sync cycle.
    """
    if not required:
        return True
    all_present = True
    for destination_path in destinations:
        marker_path = os.path.join(destination_path, marker_filename)
        if not os.path.isfile(marker_path):
            LOGGER.error(
                f"{service_name} mount marker missing: {marker_path} not found — "
                f"refusing to sync. Create the marker file (`touch {marker_path}`) "
                f"after confirming the destination is correctly mounted, then the "
                f"next sync cycle will proceed.",
            )
            all_present = False
    return all_present


def _perform_drive_sync(config, api, sync_state: SyncState, drive_sync_interval: int):
    """
    Execute drive synchronization if enabled.

    Args:
        config: Configuration dictionary
        api: iCloud API instance
        sync_state: Current sync state
        drive_sync_interval: Drive sync interval in seconds

    Returns:
        DriveStats object if sync was performed, None otherwise
    """
    if config and "drive" in config and sync_state.enable_sync_drive:
        import time

        from src.sync_stats import DriveStats

        start_time = time.time()
        stats = DriveStats()

        destination_path = config_parser.prepare_drive_destination(config=config)

        # Mount-marker failsafe (see _check_mount_marker). Skip this
        # cycle when the marker isn't present. Reset the countdown to
        # the full interval so ``_calculate_next_sync_schedule`` waits
        # before re-checking -- without the reset, on startup
        # ``drive_time_remaining`` is 0 and the next iteration spins
        # at zero sleep into a tight busy loop that floods logs and
        # burns CPU until the user touches the marker.
        if not _check_mount_marker(
            destinations=[destination_path],
            marker_filename=config_parser.get_mount_marker_filename(config=config),
            required=config_parser.get_drive_require_mount_marker(config=config),
            service_name="Drive",
        ):
            sync_state.drive_time_remaining = drive_sync_interval
            return None

        # Count files before sync
        files_before = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_before.add(os.path.join(root, file))
            except Exception:
                pass

        LOGGER.info("Syncing drive...")
        files_after = sync_drive.sync_drive(config=config, drive=api.drive)
        LOGGER.info("Drive synced")

        # Calculate statistics
        stats.duration_seconds = time.time() - start_time

        # Handle case where sync_drive returns None (e.g., in tests)
        if files_after is not None:
            # Count newly downloaded files
            new_files = files_after - files_before
            stats.files_downloaded = len(new_files)

            # Count skipped files
            stats.files_skipped = len(files_before & files_after)

            # Count removed files
            if config_parser.get_drive_remove_obsolete(config=config):
                stats.files_removed = len(files_before - files_after)

            # Calculate bytes downloaded
            try:
                for file_path in new_files:
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        stats.bytes_downloaded += os.path.getsize(file_path)
            except Exception:
                pass

        # Reset countdown timer to the configured interval
        sync_state.drive_time_remaining = drive_sync_interval
        return stats
    return None


def _perform_photos_sync(config, api, sync_state: SyncState, photos_sync_interval: int):
    """
    Execute photos synchronization if enabled.

    Args:
        config: Configuration dictionary
        api: iCloud API instance
        sync_state: Current sync state
        photos_sync_interval: Photos sync interval in seconds

    Returns:
        PhotoStats object if sync was performed, None otherwise
    """
    if config and "photos" in config and sync_state.enable_sync_photos:
        import time

        from src.sync_stats import PhotoStats

        start_time = time.time()
        stats = PhotoStats()

        destination_path = config_parser.prepare_photos_destination(config=config)

        # Mount-marker failsafe (see _check_mount_marker). Skip this cycle
        # without advancing the countdown so the next interval re-checks
        # once the user fixes the mount + touches the marker file.
        if not _check_mount_marker(
            destinations=[destination_path],
            marker_filename=config_parser.get_mount_marker_filename(config=config),
            required=config_parser.get_photos_require_mount_marker(config=config),
            service_name="Photos",
        ):
            # Same busy-loop guard as the Drive branch above: reset the
            # countdown so the next cycle waits the configured interval
            # before re-checking the marker.
            sync_state.photos_time_remaining = photos_sync_interval
            return None

        # Count files before sync
        files_before = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_before.add(os.path.join(root, file))
            except Exception:
                pass

        LOGGER.info("Syncing photos...")
        try:
            sync_result = sync_photos.sync_photos(config=config, photos=api.photos)
        except exceptions.ICloudPyServiceNotActivatedException as e:
            # With no interval there is no next cycle to wait for -- a
            # one-shot run must still report this through the normal error
            # path rather than schedule a retry it will never take.
            if not sync_photos.is_photos_indexing(e) or photos_sync_interval <= 0:
                raise
            _wait_for_photos_indexing(sync_state, photos_sync_interval)
            return None
        LOGGER.info("Photos synced")
        _signal_photos_indexing(waiting=False)

        # Count files after sync
        files_after = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_after.add(os.path.join(root, file))
            except Exception:
                pass

        # Calculate statistics
        stats.duration_seconds = time.time() - start_time

        # Count newly downloaded files
        new_files = files_after - files_before
        stats.photos_downloaded = len(new_files)

        # Estimate hardlinked photos (approximate)
        use_hardlinks = config_parser.get_photos_use_hardlinks(
            config=config,
            log_messages=False,
        )
        if use_hardlinks:
            stats.photos_hardlinked = max(
                0,
                len(files_after) - len(files_before) - stats.photos_downloaded,
            )

        # Count skipped photos
        stats.photos_skipped = len(files_before & files_after)

        # Calculate bytes downloaded
        try:
            for file_path in new_files:
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    stats.bytes_downloaded += os.path.getsize(file_path)

            # Estimate bytes saved by hardlinks
            if use_hardlinks and stats.photos_hardlinked > 0:
                for file_path in files_after:
                    if file_path not in new_files and os.path.isfile(file_path):
                        stats.bytes_saved_by_hardlinks += os.path.getsize(file_path)
        except Exception:
            pass

        # Track failed downloads so notifications reflect errors
        if isinstance(sync_result, tuple):
            _, failed_downloads = sync_result
            if failed_downloads > 0:
                stats.errors.append(f"{failed_downloads} photo download(s) failed")

        # Get list of synced albums (simple approximation based on directories)
        try:
            for item in os.listdir(destination_path):
                item_path = os.path.join(destination_path, item)
                if os.path.isdir(item_path):
                    stats.albums_synced.append(item)
        except Exception:
            pass

        # Reset countdown timer to the configured interval
        sync_state.photos_time_remaining = photos_sync_interval
        return stats
    return None


def _wait_for_photos_indexing(sync_state: SyncState, photos_sync_interval: int) -> None:
    """Skip Photos this cycle because Apple has not finished indexing it.

    Nothing could be listed, so nothing may be cleaned up either -- an
    empty listing and an unreadable one look identical to obsolete-file
    cleanup. Drive is unaffected and carries on.

    The retry only ever shortens the wait (``min`` with the configured
    interval). It is not a login retry: the session is resumed per cycle
    like any other, and ``retry_login_interval`` is not involved.
    """
    retry = min(PHOTOS_INDEXING_RETRY_SEC, photos_sync_interval)
    again = f"{retry // 60} minutes" if retry >= 120 else f"{retry} seconds"
    LOGGER.warning(
        "Apple has not finished indexing this iCloud Photos library, so it cannot "
        f"be read yet. Nothing on disk was changed. Trying Photos again in {again}.",
    )
    sync_state.photos_time_remaining = retry
    sync_state.photos_indexing = True
    _signal_photos_indexing(waiting=True)


def _signal_photos_indexing(*, waiting: bool) -> None:
    """Publish (or clear) the dashboard's "waiting for Apple" note.

    Recorded against the Photos service, not a library: no library can be
    read while this is true, so no library row could carry it.
    """
    try:
        from src import web_signals as _ws

        _ws.record_photos_indexing(waiting=waiting)
        if waiting:
            # The library being opened when this surfaced is still marked
            # "syncing now" and never got started. Left alone it reads as
            # a library syncing forever, next to a note saying Photos
            # cannot be read at all.
            _ws.clear_stale_library_states()
    except Exception as e:  # noqa: BLE001 -- dashboard state must never break sync
        LOGGER.debug(f"web_signals: record_photos_indexing raised: {e!s}")


def _perform_dry_run(config, api, check_files: int | None = None) -> None:
    """Authenticate-and-enumerate path used when ``--dry-run`` is passed.

    Verifies that the configured credentials, mount paths, and iCloud-side
    state are all in working order WITHOUT writing or downloading any
    files. Designed as the safety check users run before letting the real
    sync loop loose on a new install.

    Logs (at INFO level):
      - Drive destination path + root-level item count (when Drive is configured)
      - Photos destination path + library names (when Photos is configured)
      - When ``check_files`` is not None: per-library would-skip /
        size-mismatch / not-found counts (see ``migration_check``).

    Args:
        config: Configuration dictionary
        api: Authenticated iCloud API instance
        check_files: When set (``--check-files=N``), additionally walks
            up to N photos per library and reports what a real sync
            would do per file. ``0`` walks every photo. ``None`` skips
            this check (cheap default for ``--dry-run`` alone).

    Notifications, usage statistics, file writes, file deletions, and the
    sync loop itself are all skipped.
    """
    LOGGER.info("DRY RUN: authentication succeeded — verifying configured services.")

    if config and "drive" in config:
        try:
            # Resolved absolute path (root + destination), computed without
            # creating anything, so users can verify the mount point. Mirrors
            # how migration_check builds its base path.
            drive_destination = os.path.join(
                config_parser.get_root_destination_path(config=config),
                config_parser.get_drive_destination_path(config=config),
            )
            LOGGER.info(f"DRY RUN: Drive destination: {drive_destination}")
            root_items = list(api.drive.dir())
            LOGGER.info(
                f"DRY RUN: Drive root contains {len(root_items)} item(s) — "
                "real sync would walk this tree per `drive.filters`.",
            )
        except Exception as e:
            LOGGER.warning(f"DRY RUN: Drive enumeration failed: {e!s}")
    else:
        LOGGER.info(
            "DRY RUN: no `drive:` section in config — Drive sync would be skipped.",
        )

    if config and "photos" in config:
        try:
            photos_destination = os.path.join(
                config_parser.get_root_destination_path(config=config),
                config_parser.get_photos_destination_path(config=config),
            )
            LOGGER.info(f"DRY RUN: Photos destination: {photos_destination}")
            libraries = (
                list(api.photos.libraries.keys())
                if hasattr(api.photos, "libraries")
                else []
            )
            if libraries:
                LOGGER.info(
                    f"DRY RUN: Photos libraries available: {', '.join(libraries)}",
                )
            else:
                LOGGER.info("DRY RUN: Photos libraries: (none reported by iCloud)")
        except Exception as e:
            LOGGER.warning(f"DRY RUN: Photos enumeration failed: {e!s}")
    else:
        LOGGER.info(
            "DRY RUN: no `photos:` section in config — Photos sync would be skipped.",
        )

    if check_files is not None:
        from src import migration_check

        # Photos walker — per-library counts using mandarons' real path/size
        # logic so the report mirrors what a real sync would skip vs download.
        if config and "photos" in config:
            try:
                LOGGER.info(
                    f"DRY RUN: walking photos for file-existence check "
                    f"(--check-files={'all' if check_files == 0 else check_files} per library) ...",
                )
                results = migration_check.check_migration(
                    api=api,
                    config=config,
                    sample=check_files,
                )
                for library_name, result in results.items():
                    stats = result["stats"]
                    LOGGER.info(
                        f"DRY RUN: {library_name} (dest {result['library_dest']}): "
                        f"sampled={result['checked']} "
                        f"would_skip={stats['would_skip']} "
                        f"size_mismatch={stats['size_mismatch']} "
                        f"not_found={stats['not_found']} "
                        f"errors={stats['error']}",
                    )
                    for status, items in result["samples"].items():
                        for item in items:
                            if status == "size_mismatch":
                                path, expected, actual = item
                                LOGGER.info(
                                    f"DRY RUN:   sample {status}: {path} (have {actual:,}b, want {expected:,}b)",
                                )
                            else:
                                path, expected = item
                                LOGGER.info(
                                    f"DRY RUN:   sample {status}: {path} ({expected:,}b)",
                                )
            except Exception as e:
                LOGGER.warning(f"DRY RUN: photos check-files walk failed: {e!s}")

        # Drive walker — same per-file would_skip/size_mismatch/not_found
        # report, but walking the Drive tree (no library_destinations,
        # mirror-tree layout). Catches misconfigured drive.destination.
        if config and "drive" in config:
            try:
                drive_result = migration_check.check_drive_migration(
                    api=api,
                    config=config,
                    sample=check_files,
                )
                if drive_result is not None:
                    stats = drive_result["stats"]
                    LOGGER.info(
                        f"DRY RUN: Drive (dest {drive_result['drive_destination']}): "
                        f"sampled={drive_result['checked']} "
                        f"would_skip={stats['would_skip']} "
                        f"size_mismatch={stats['size_mismatch']} "
                        f"not_found={stats['not_found']} "
                        f"errors={stats['error']}",
                    )
                    for status, items in drive_result["samples"].items():
                        for item in items:
                            if status == "size_mismatch":
                                path, expected, actual = item
                                LOGGER.info(
                                    f"DRY RUN:   sample {status}: {path} (have {actual:,}b, want {expected:,}b)",
                                )
                            else:
                                path, expected = item
                                LOGGER.info(
                                    f"DRY RUN:   sample {status}: {path} ({expected:,}b)",
                                )
            except Exception as e:
                LOGGER.warning(f"DRY RUN: drive check-files walk failed: {e!s}")

    LOGGER.info(
        "DRY RUN complete — no files were written. Re-run without --dry-run to sync.",
    )


def _check_services_configured(config):
    """
    Check if any sync services are configured.

    Args:
        config: Configuration dictionary

    Returns:
        bool: True if at least one service is configured
    """

    return "drive" in config or "photos" in config


def _cycle_nothing_synced_reason(config, drive_stats, photos_stats, photos_indexing=False) -> str | None:
    """Why this cycle synced no service at all, or None if one did.

    Such a cycle is indistinguishable from a clean one by its stats -- no
    errors, no counts -- so reporting it as a success is how a monitor stays
    green while nothing whatsoever is being downloaded. It happens two ways:
    nothing is configured to sync, or every service that was due got skipped
    -- by the mount-marker failsafe, or (Photos) because Apple has not
    finished indexing the library.

    Not to be confused with a service that simply was not due. With unequal
    intervals ``_calculate_next_sync_schedule`` enables only the service
    whose timer expired, so one of the two returning None is the ordinary
    case -- hence "no stats at all" rather than "any stats missing".

    Args:
        config: Configuration dictionary
        drive_stats: Result of ``_perform_drive_sync``
        photos_stats: Result of ``_perform_photos_sync``
        photos_indexing: Whether this cycle skipped Photos for indexing

    Returns:
        ``nothing_synced``, ``photos_indexing``, ``mount_marker_missing``,
        or None if a service ran
    """
    if not _check_services_configured(config):
        return "nothing_synced"
    if drive_stats is None and photos_stats is None:
        return "photos_indexing" if photos_indexing else "mount_marker_missing"
    return None


def _cycle_end_message(has_errors: bool, nothing_reason: str | None) -> str:
    """The human text for the end-of-cycle event.

    Kept out of ``sync()`` only because the branch it sits in is already four
    levels deep.
    """
    if nothing_reason == "nothing_synced":
        return "iCloud sync cycle synced nothing: no drive or photos section is configured"
    if nothing_reason == "photos_indexing":
        return "iCloud sync cycle synced nothing: Apple has not finished indexing Photos"
    if nothing_reason:
        return "iCloud sync cycle synced nothing: the mount marker is missing"
    if has_errors:
        return "iCloud sync cycle completed with errors"
    return "iCloud sync cycle completed"


def _send_usage_statistics(config, summary: SyncSummary) -> None:
    """Send anonymized usage statistics.

    Args:
        config: Configuration dictionary
        summary: Sync summary with statistics
    """

    # Create anonymized usage data
    usage_data = {
        "sync_duration": (
            (summary.sync_end_time - summary.sync_start_time).total_seconds()
            if summary.sync_end_time
            else 0
        ),
        "has_drive_activity": bool(
            summary.drive_stats and summary.drive_stats.has_activity(),
        ),
        "has_photos_activity": bool(
            summary.photo_stats and summary.photo_stats.has_activity(),
        ),
        "has_errors": summary.has_errors(),
        "timestamp": (
            summary.sync_end_time.isoformat() if summary.sync_end_time else None
        ),
    }

    # Add aggregated statistics (no personal data)
    if summary.drive_stats:
        usage_data["drive"] = {
            "files_count": summary.drive_stats.files_downloaded,
            "bytes_count": summary.drive_stats.bytes_downloaded,
            "has_errors": summary.drive_stats.has_errors(),
        }

    if summary.photo_stats:
        usage_data["photos"] = {
            "photos_count": summary.photo_stats.photos_downloaded,
            "bytes_count": summary.photo_stats.bytes_downloaded,
            "hardlinks_count": summary.photo_stats.photos_hardlinked,
            "has_errors": summary.photo_stats.has_errors(),
        }

    # Send to usage tracking
    alive(config=config, data=usage_data)


def _auth_retry_sleep(total_seconds: int) -> None:
    """Wait between sign-in attempts, ending early on a completed re-auth.

    The loop backs off for ``retry_login_interval`` between attempts and
    cannot otherwise see that the session was fixed underneath it, so
    someone who signs in through the web UI watches the dashboard keep
    saying the sync is stopped until an interval that began *before* the
    problem was solved finally runs out.

    Polls only the re-auth signal, not the force-sync sentinel behind
    "Sync now": that button means "sync everything now", and a re-auth
    should end a wait without also queueing a full re-enumeration.
    """
    _CHUNK = 2
    try:
        from src import web_signals as _ws
    except ImportError:  # pragma: no cover - module is optional
        sleep(total_seconds)
        return

    if total_seconds <= _CHUNK:
        sleep(total_seconds)
        return

    remaining = total_seconds
    while remaining > 0:
        chunk = min(_CHUNK, remaining)
        sleep(chunk)
        remaining -= chunk
        if _ws.consume_reauth_completed():
            LOGGER.info("Re-auth completed -- ending the retry wait early.")
            return


def _request_2fa_push_once(api, sync_state: SyncState) -> None:
    """Ask Apple to push a 2FA code to the trusted devices, once per episode.

    Without this call the loop notified the user that re-auth was needed but
    never requested a code, so nothing was ever sent.

    The latch is set only when Apple accepts the request.
    ``trigger_2fa_push_notification`` returns False rather than raising for
    most failures, and latching regardless meant one transient error
    forfeited the push for the whole episode -- the user told "2FA is
    required" while no code ever arrived, which is the bug this exists to
    fix. Retrying on the next cycle is bounded by ``retry_login_interval``
    (600s by default), far below anything that trips Apple's limits.

    Best-effort: a failure here never stops the retry loop.
    """
    if sync_state.two_fa_triggered:
        return
    try:
        pushed = api.trigger_2fa_push_notification()
    except Exception as e:  # noqa: BLE001
        LOGGER.warning(f"Failed to request 2FA push notification; will retry next cycle: {e!s}")
        return
    if pushed:
        LOGGER.info("Requested a 2FA push notification to your trusted devices.")
        sync_state.two_fa_triggered = True
    else:
        LOGGER.warning("Apple did not accept the 2FA push request; will retry next cycle.")


def _handle_2fa_required(config, username: str, sync_state: SyncState, api):
    """
    Handle 2FA authentication requirement.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state
        api: Live ``ICloudPyService`` still in its 2FA-required state. Used to
            request a push notification to the user's trusted devices. When
            ``app.telegram.listen`` is true, the retry sleep is replaced with a
            Telegram poll: the user replies the auth keyword to have Apple push a
            code, then replies the 6 digits -- completing re-authentication from a
            phone, headless, with no web UI.

    Returns:
        bool: True if should continue (retry), False if should exit
    """
    LOGGER.error("Error: 2FA is required. Please log in.")
    _publish_auth_blocked(True, reason="2fa_required")
    # Decided before anything is sent: it selects the notification wording,
    # the reason a receiver sees, and suppresses two steps that cannot
    # succeed on such an account.
    security_key = _detect_security_key_account(api, username)
    notify.send_cycle_event(
        config=config,
        boundary="failure",
        message="iCloud sync cycle aborted: 2FA is required",
        data={"reason": "security_key_required" if security_key else "two_factor_required"},
    )
    if security_key:
        LOGGER.error(
            "This account signs in with a security key, so Apple will not "
            "send a 6-digit code. Complete the ceremony on the dashboard "
            "(/auth); the push request and the code listener are skipped.",
        )
    # Ask Apple to push a code before anything else -- including the exit
    # below: retry_login_interval < 0 is the mode where an operator is about
    # to intervene by hand, and a code on their devices is what they need.
    # Not for a security-key account: Apple sends those no code at all.
    if not security_key:
        _request_2fa_push_once(api, sync_state)

    sleep_for = config_parser.get_retry_login_interval(config=config)

    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False

    _log_retry_time(sleep_for)
    server_region = config_parser.get_region(config=config)
    # notify.send is throttled (once per 24h) and listen-aware: in listen mode the
    # Telegram channel gets the actionable reply prompt, other channels the standard
    # alert. Throttling here is what prevents a "reply auth" message every retry cycle.
    sync_state.last_send = notify.send(
        config=config,
        username=username,
        last_send=sync_state.last_send,
        region=server_region,
        dashboard_url=_resolve_dashboard_url(config),
        # A security-key account cannot finish sign-in from a Telegram code,
        # so it gets the standard alert pointing at the dashboard.
        reply_prompt=not security_key,
        event="security_key_required" if security_key else "two_factor_required",
    )
    if not security_key and config_parser.get_telegram_listen_enabled(config=config):
        _wait_for_telegram_code(config=config, api=api, timeout_seconds=sleep_for)
    else:
        _auth_retry_sleep(sleep_for)
    return True


def _wait_for_telegram_code(config, api, timeout_seconds: int) -> bool:
    """Drive 2FA over Telegram with a manual, user-initiated trigger.

    The reply prompt itself is sent by ``notify.send`` (throttled); this function
    drains any stale replies, then polls for the user's actions:
      1. On the auth keyword -> ``api.trigger_2fa_push_notification()`` so Apple
         actually pushes a code to the trusted devices. (The headless path
         previously waited for a code it never requested -- this missing trigger
         is the core bug this fixes.)
      2. On a 6-digit reply (spaces/dashes tolerated) -> ``validate_2fa_code``
         + ``trust_session``.

    Returns True once a code validates and trust succeeds within
    ``timeout_seconds``, or once the web UI completes the re-auth first;
    False on timeout. Best-effort throughout. The Telegram
    ``getUpdates`` offset is held in-memory for the duration of this wait.
    """
    from src import web_signals

    poll_interval = 5
    bot_token = config_parser.get_telegram_bot_token(config=config)
    chat_id = config_parser.get_telegram_chat_id(config=config)
    auth_keyword = config_parser.get_telegram_auth_keyword(config=config)
    if not bot_token or not chat_id:
        LOGGER.warning(
            "Telegram listen enabled but bot_token/chat_id not configured; falling back to plain sleep.",
        )
        sleep(timeout_seconds)
        return False

    # Drain any messages already pending so a stale reply from a previous
    # session does not get acted on; start listening for genuinely new replies.
    # Deliberate trade-off: a code typed while the loop is between wait
    # windows is dropped too. Acting on an old code is worse than asking for
    # a fresh one, and the window is the whole retry interval (600s default).
    _, offset = notify.poll_telegram_for_text(
        bot_token=bot_token, chat_id=chat_id, offset=0,
    )
    while True:
        _, drained = notify.poll_telegram_for_text(
            bot_token=bot_token, chat_id=chat_id, offset=offset,
        )
        if drained == offset:
            break
        offset = drained

    LOGGER.info(
        f"Listening on Telegram for '{auth_keyword}' trigger or 6-digit code (timeout {timeout_seconds}s).",
    )
    elapsed = 0
    while elapsed < timeout_seconds:
        chunk = min(poll_interval, timeout_seconds - elapsed)
        sleep(chunk)
        elapsed += chunk
        # The web UI and Telegram can both complete a re-auth. If the web UI
        # got there first, stop listening -- otherwise the loop sits out the
        # rest of the window holding a session that is already fixed.
        if web_signals.consume_reauth_completed():
            LOGGER.info("Re-auth completed in the web UI -- ending the Telegram wait.")
            return True
        text, offset = notify.poll_telegram_for_text(
            bot_token=bot_token,
            chat_id=chat_id,
            offset=offset,
        )
        if not text:
            continue
        norm = text.strip().lower()
        if norm == auth_keyword:
            LOGGER.info("Telegram auth trigger received -- requesting 2FA push.")
            try:
                pushed = api.trigger_2fa_push_notification()
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"trigger_2fa_push_notification raised: {e!s}")
                pushed = False
            notify.post_message_to_telegram(
                bot_token,
                chat_id,
                (
                    "✅ 2FA code sent to your Apple devices -- reply the 6-digit code here."
                    if pushed
                    else "⚠️ Couldn't request a code (no trusted device, or auth state off). Try again shortly."
                ),
            )
            continue
        code = norm.replace(" ", "").replace("-", "")
        if re.fullmatch(r"\d{6}", code):
            LOGGER.info("Received 6-digit code via Telegram -- validating.")
            try:
                accepted = api.validate_2fa_code(code)
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(
                    f"validate_2fa_code raised: {e!s} -- waiting for another code.",
                )
                continue
            if not accepted:
                notify.post_message_to_telegram(
                    bot_token,
                    chat_id,
                    "❌ Apple rejected that code -- reply a fresh one.",
                )
                LOGGER.warning(
                    "Apple rejected the Telegram-supplied code -- waiting for another.",
                )
                continue
            try:
                api.trust_session()
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"trust_session raised (non-fatal): {e!s}")
            notify.post_message_to_telegram(
                bot_token,
                chat_id,
                "✅ Re-authenticated. iCloud sync resumed.",
            )
            LOGGER.info("Telegram-driven 2FA succeeded; resuming sync.")
            return True
    LOGGER.info("Telegram listen timeout reached with no usable code; retrying auth.")
    return False


def _needs_a_human(sync_state: SyncState, error) -> bool:
    """Whether a sign-in failure warrants the "re-auth required" alert.

    A rejected password always does: retrying cannot fix it.

    In session-only mode one more case does, because it cannot be told
    apart from a rejected session. icloudpy keeps the HTTP status on the
    exception only for a non-JSON body or its own re-auth statuses
    (``_SESSION_REJECTED_CODES``), so a JSON-bodied 401 arrives with
    ``code`` as ``None``. Those are the ones that would otherwise leave a
    container only a human can revive retrying in silence forever.

    Everything else is an outage -- a 5xx that kept its status, a dropped
    connection, a DNS failure -- and says nothing about the session. Those
    are logged and retried. Waking someone daily to re-authenticate over
    Apple having a bad hour is the alert this function exists to withhold.
    """
    if isinstance(error, exceptions.ICloudPyFailedLoginException):
        return True
    return (
        sync_state.session_only
        and isinstance(error, exceptions.ICloudPyAPIResponseException)
        and error.code is None
    )


def _handle_auth_transport_error(config, username: str, sync_state: SyncState, error):
    """Back off after a sign-in failure Apple did not express as a 2FA prompt.

    Uses at least ``_AUTH_BACKOFF_FLOOR_SEC`` regardless of the configured
    retry interval: the errors that land here (notably Apple's 409 on
    ``/signin/init``) mean "you are trying too often", so honouring a short
    interval would make it worse.

    Returns True to keep looping, False to exit.
    """
    LOGGER.error(f"Sign-in failed and will be retried: {error!s}")
    # Only a refusal from Apple's sign-in is sign_in_failed, matching the
    # alert below. A network fault or an Apple service error means the
    # attempt never completed, which needs no one to intervene.
    rejected = isinstance(error, exceptions.ICloudPyFailedLoginException)
    notify.send_cycle_event(
        config=config,
        boundary="failure",
        message=(
            "iCloud sync cycle aborted: sign-in failed"
            if rejected
            else "iCloud sync cycle aborted: sign-in did not complete"
        ),
        data={"reason": "sign_in_failed" if rejected else "sign_in_error"},
    )
    sleep_for = config_parser.get_retry_login_interval(config=config)
    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False
    sleep_for = max(sleep_for, _AUTH_BACKOFF_FLOOR_SEC)
    _log_retry_time(sleep_for)
    if sync_state.session_only:
        # The loop is not syncing and only a human can change that, so the
        # dashboard is told -- its wording for this reason allows for an
        # outage and asks for nothing.
        _publish_auth_blocked(True, reason="sign_in_failed")
    if _needs_a_human(sync_state, error):
        # notify.send's text is "iCloud re-auth required", so it is reserved
        # for the cases where that is actually true: a rejected password,
        # which never heals by retrying, and -- in session-only mode -- a
        # failure that cannot be told apart from a rejected session. It is
        # throttled, so this is not a message per retry.
        sync_state.last_send = notify.send(
            config=config,
            username=username,
            last_send=sync_state.last_send,
            region=config_parser.get_region(config=config),
            dashboard_url=_resolve_dashboard_url(config),
            event="sign_in_failed",
        )
    # Ends early on a completed web-UI re-auth, but not on "Sync now":
    # nothing a button does may shorten a throttle backoff.
    _auth_retry_sleep(sleep_for)
    return True


def _handle_sync_error(config, error, drive_sync_interval, photos_sync_interval):
    """Back off after a failure that happened *after* a successful sign-in.

    Anything raised once ``api`` exists is a service problem, not an auth
    problem: a zone that is unavailable, a 5xx on a download, a connection
    dropped mid-transfer. Reporting those as sign-in failures sends the user
    to re-authenticate for no reason.

    The interval matters as much as the wording. Every handler here ends in
    ``continue``, which skips ``_calculate_next_sync_schedule`` -- so the
    countdown timers never advance and both services stay enabled. Retrying
    on the short login interval therefore re-enumerates the whole library
    every few minutes. Wait at least as long as the shortest configured sync
    interval instead: never poll a broken service faster than a working one.

    Returns True to keep looping, False to exit.
    """
    LOGGER.error(f"Sync failed and will be retried: {error!s}")
    notify.send_cycle_event(
        config=config,
        boundary="failure",
        message="iCloud sync cycle failed and will be retried",
        data={"reason": "sync_error"},
    )
    # log_messages=False: this is not a login retry, and the getter's
    # "Retrying login every N seconds." would say otherwise.
    sleep_for = config_parser.get_retry_login_interval(config=config, log_messages=False)
    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False
    configured = [i for i in (drive_sync_interval, photos_sync_interval) if i > 0]
    if configured:
        sleep_for = max(sleep_for, min(configured))
    _log_retry_time(sleep_for, what="sync")
    # This can be a whole sync interval; the "Sync now" button must still
    # cut it short, as it does on the normal scheduling path.
    _interruptible_sleep(sleep_for)
    return True


def _handle_password_error(config, username: str, sync_state: SyncState, error):
    """
    Handle password not available error.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state
        error: The raised exception, whose message names which way
            session-only mode failed -- no session at all, or a session
            Apple no longer accepts.

    Returns:
        bool: True if should continue (retry), False if should exit
    """
    LOGGER.error(str(error))
    # The dashboard's own on-disk check reads an empty keyring as "setup
    # needed", which is the wrong instruction here: the session, not the
    # password, is what has to be replaced.
    _publish_auth_blocked(True, reason="session_unusable")
    notify.send_cycle_event(
        config=config,
        boundary="failure",
        message="iCloud sync cycle aborted: no stored password and no usable saved session",
        data={"reason": "password_missing"},
    )
    sleep_for = config_parser.get_retry_login_interval(config=config)

    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False

    _log_retry_time(sleep_for)
    server_region = config_parser.get_region(config=config)
    sync_state.last_send = notify.send(
        config=config,
        username=username,
        last_send=sync_state.last_send,
        region=server_region,
        dashboard_url=_resolve_dashboard_url(config),
        event="password_missing",
    )
    _auth_retry_sleep(sleep_for)
    return True


def _log_retry_time(sleep_for: int, what: str = "login"):
    """
    Log the next retry time.

    Args:
        sleep_for: Sleep duration in seconds
        what: What is being retried; a failed sync is not a failed login
    """
    next_sync = (
        datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
    ).strftime("%c")
    LOGGER.info(f"Retrying {what} at {next_sync} ...")


def _calculate_next_sync_schedule(config, sync_state: SyncState):
    """
    Calculate next sync schedule and update sync state.

    This function implements the adaptive scheduling algorithm that determines
    which service should sync next based on countdown timers.

    Args:
        config: Configuration dictionary
        sync_state: Current sync state

    Returns:
        int: Sleep duration in seconds
    """
    has_drive = config and "drive" in config
    has_photos = config and "photos" in config

    if not has_drive and has_photos:
        sleep_for = sync_state.photos_time_remaining
        sync_state.enable_sync_drive = False
        sync_state.enable_sync_photos = True
    elif has_drive and not has_photos:
        sleep_for = sync_state.drive_time_remaining
        sync_state.enable_sync_drive = True
        sync_state.enable_sync_photos = False
    else:
        # Sleep until the sooner of the two is due, and take that time off
        # both countdowns. Whichever reaches zero syncs next; equal timers
        # sync together. A negative countdown is a one-shot service
        # (sync_interval < 0) that has already run: it is never due again,
        # so it takes no part, and must never become a negative sleep.
        pending = [t for t in (sync_state.drive_time_remaining, sync_state.photos_time_remaining) if t >= 0]
        sleep_for = min(pending) if pending else 0
        if sync_state.drive_time_remaining >= 0:
            sync_state.drive_time_remaining -= sleep_for
        if sync_state.photos_time_remaining >= 0:
            sync_state.photos_time_remaining -= sleep_for
        sync_state.enable_sync_drive = sync_state.drive_time_remaining == 0
        sync_state.enable_sync_photos = sync_state.photos_time_remaining == 0

    return sleep_for


def _log_next_sync_time(sleep_for: int):
    """
    Log the next scheduled sync time.

    Args:
        sleep_for: Sleep duration in seconds
    """
    next_sync = (
        datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
    ).strftime("%c")
    LOGGER.info(f"Resyncing at {next_sync} ...")


def _log_sync_intervals_at_startup(config):
    """
    Log sync intervals once at startup.

    Args:
        config: Configuration dictionary
    """
    if config and "drive" in config:
        config_parser.get_drive_sync_interval(config=config, log_messages=True)
    if config and "photos" in config:
        config_parser.get_photos_sync_interval(config=config, log_messages=True)


def _should_exit_oneshot_mode(config):
    """
    Check if should exit in oneshot mode.

    Oneshot mode exits when ALL configured sync intervals are negative.

    Args:
        config: Configuration dictionary

    Returns:
        bool: True if should exit
    """

    should_exit_drive = ("drive" not in config) or (
        config_parser.get_drive_sync_interval(config=config, log_messages=False) < 0
    )
    should_exit_photos = ("photos" not in config) or (
        config_parser.get_photos_sync_interval(config=config, log_messages=False) < 0
    )

    return should_exit_drive and should_exit_photos


def sync(dry_run: bool = False, check_files: int | None = None):
    """
    Main synchronization loop.

    Orchestrates the entire sync process by delegating specific responsibilities
    to focused helper functions. This function coordinates the high-level flow
    while each helper handles a single concern.

    Args:
        dry_run: When True, authenticate and summarise what would be synced,
            then exit without writing files, sending notifications, or
            entering the sync loop. Useful for verifying credentials, mount
            paths, and config before the real loop starts downloading.
        check_files: Optional sample size for the per-photo file-existence
            check during dry-run. Only meaningful with ``dry_run=True``.
            ``None`` skips the check (cheap default). ``0`` walks every
            photo (slow on large libraries). Positive N walks N
            stride-sampled photos per library.
    """
    sync_state = SyncState()
    startup_logged = False

    while True:
        # A config that cannot be read must not kill the daemon. On a NAS the
        # volume holding config.yaml can lag behind container start or go away
        # mid-run, and a half-written file (the user editing it live) raises
        # out of the YAML parser. Either way the traceback escapes the loop,
        # and `restart: unless-stopped` turns that into a restart loop.
        try:
            config = _load_configuration()
        except Exception as e:  # noqa: BLE001 -- any parse fault must not be fatal
            LOGGER.error(f"Config file could not be read, retrying: {e!s}")
            config = None
        if config is None:
            if dry_run:
                # A dry run is a one-shot check with nothing to wait for.
                LOGGER.error("DRY RUN: no readable config, nothing to check.")
                return
            sleep(DEFAULT_RETRY_LOGIN_INTERVAL_SEC)
            continue

        # Log sync intervals once at startup
        if not startup_logged:
            _log_sync_intervals_at_startup(config)
            notify.warn_unknown_webhook_events(config)
            # The state file outlives the container, so a restart mid-library
            # would leave the dashboard showing it as still syncing. Nothing
            # can legitimately be in flight here.
            try:
                from src import web_signals as _ws

                _ws.clear_stale_library_states()
            except Exception as e:  # noqa: BLE001 -- never block startup
                LOGGER.debug(f"web_signals: clear_stale_library_states raised: {e!s}")
            startup_logged = True

        drive_sync_interval, photos_sync_interval = _extract_sync_intervals(
            config,
            log_messages=False,
        )
        username = config_parser.get_username(config=config) if config else None

        # Web UI "Sync now" requests: ``src.web_signals`` writes a
        # sentinel file when the user taps the button; we delete it and
        # zero the countdown so the next pass through the sync calls
        # runs immediately. Best-effort import so vanilla mandarons
        # builds without the web-UI module still work.
        try:
            from src import web_signals as _ws

            if _ws.consume_force_sync("drive"):
                LOGGER.info("Force-sync requested for Drive — running immediately")
                sync_state.drive_time_remaining = 0
            if _ws.consume_force_sync("photos"):
                LOGGER.info("Force-sync requested for Photos — running immediately")
                sync_state.photos_time_remaining = 0
        except (
            ImportError
        ):  # pragma: no cover — best-effort fallback for builds without web_signals
            pass

        if username:
            authenticated = False
            try:
                api = _authenticate_and_get_api(config, username, sync_state)
                authenticated = True

                # Dry-run path: authenticate, enumerate, log, exit.
                # Skips the entire sync + notification + retry pipeline.
                if dry_run:
                    if api.requires_2sa:
                        LOGGER.info(
                            "DRY RUN: 2FA required — finish interactive auth first "
                            "(see README), then re-run with --dry-run.",
                        )
                    else:
                        _perform_dry_run(config, api, check_files=check_files)
                    return

                _publish_auth_blocked(False)
                if not api.requires_2sa:
                    # Trust-window check: record current cookie expiry and
                    # fire a pre-emptive warning once if it's about to lapse.
                    # Best-effort: any failure is logged + swallowed inside.
                    _maybe_refresh_trust(config, api)
                    _maybe_warn_trust_expiring(config, api, username)

                    # Authenticated: clear the 2FA trigger latch so a future
                    # re-auth episode requests a fresh push exactly once.
                    sync_state.two_fa_triggered = False

                    # Signed in and about to sync: open the cycle on any
                    # configured webhook. Fire-and-forget, and a no-op when
                    # none is configured (see notify.send_cycle_event).
                    notify.send_cycle_event(
                        config=config,
                        boundary="start",
                        message="iCloud sync cycle started",
                    )

                    # Create summary for this sync cycle
                    summary = SyncSummary()

                    # Perform syncs and collect statistics
                    sync_state.photos_indexing = False
                    drive_stats = _perform_drive_sync(
                        config,
                        api,
                        sync_state,
                        drive_sync_interval,
                    )
                    photos_stats = _perform_photos_sync(
                        config,
                        api,
                        sync_state,
                        photos_sync_interval,
                    )

                    # Populate summary with statistics
                    summary.drive_stats = drive_stats
                    summary.photo_stats = photos_stats
                    summary.sync_end_time = datetime.datetime.now()

                    # Close the cycle on the webhooks. Failed downloads
                    # counted in the stats make this a failure even though
                    # the cycle itself ran to completion -- a monitor that
                    # reported success here would stay green while the
                    # library silently fell behind. So does a cycle that
                    # synced nothing at all. The statistics ride along, so a
                    # POST receiver sees them without app.notifications.
                    has_errors = summary.has_errors()
                    nothing_reason = _cycle_nothing_synced_reason(
                        config,
                        drive_stats,
                        photos_stats,
                        sync_state.photos_indexing,
                    )
                    # Every sync_failed names a reason, including this one: a
                    # receiver should never have to infer why from the
                    # statistics. (Only Photos counts failed downloads, so
                    # has_errors never means a Drive failure today.)
                    reason = nothing_reason or ("download_errors" if has_errors else None)
                    cycle_data = notify.summary_event_data(summary)
                    if reason:
                        cycle_data["reason"] = reason
                    notify.send_cycle_event(
                        config=config,
                        boundary="failure" if reason else "success",
                        message=_cycle_end_message(has_errors, nothing_reason),
                        data=cycle_data,
                    )

                    # Persist per-service last-sync state for the web
                    # dashboard. Best-effort — if the JSON write fails
                    # the sync itself is unaffected.
                    try:
                        from src import web_signals as _ws

                        if drive_stats is not None:
                            _ws.record_sync_completion(
                                service="drive",
                                files_downloaded=drive_stats.files_downloaded,
                                files_skipped=drive_stats.files_skipped,
                                files_removed=drive_stats.files_removed,
                                errors=len(drive_stats.errors),
                                duration_seconds=drive_stats.duration_seconds,
                            )
                        if photos_stats is not None:
                            _ws.record_sync_completion(
                                service="photos",
                                files_downloaded=photos_stats.photos_downloaded,
                                files_skipped=photos_stats.photos_skipped,
                                errors=len(photos_stats.errors),
                                duration_seconds=photos_stats.duration_seconds,
                            )
                    except (
                        ImportError
                    ):  # pragma: no cover — best-effort fallback for builds without web_signals
                        pass
                    except Exception as e:
                        LOGGER.debug(
                            f"web_signals: record_sync_completion raised: {e!s}",
                        )

                    # Send usage statistics (anonymized summary data)
                    try:
                        _send_usage_statistics(config, summary)
                    except Exception as e:
                        LOGGER.debug(f"Failed to send usage statistics: {e!s}")

                    # Send sync summary notification if configured
                    # Only send notification when both enabled services have synced in this cycle
                    # Gracefully handle notification failures to not break sync
                    has_drive_config = config and "drive" in config
                    has_photos_config = config and "photos" in config

                    should_send_notification = False
                    if has_drive_config and has_photos_config:
                        # Both services configured - send notification only when both have synced
                        should_send_notification = (
                            drive_stats is not None and photos_stats is not None
                        )
                    elif has_drive_config and not has_photos_config:
                        # Only drive configured - send when drive synced
                        should_send_notification = drive_stats is not None
                    elif has_photos_config and not has_drive_config:
                        # Only photos configured - send when photos synced
                        should_send_notification = photos_stats is not None

                    if should_send_notification:
                        try:
                            notify.send_sync_summary(config=config, summary=summary)
                        except Exception as e:
                            LOGGER.debug(
                                f"Failed to send sync summary notification: {e!s}",
                            )

                    if not _check_services_configured(config):
                        LOGGER.warning(
                            "Nothing to sync. Please add drive: and/or photos: section in config.yaml file.",
                        )
                else:
                    _log_trust_revocation_hint(api)
                    if not _handle_2fa_required(config, username, sync_state, api):
                        break
                    continue

            except exceptions.ICloudPyNoStoredPasswordAvailableException as e:
                if not _handle_password_error(config, username, sync_state, e):
                    break
                continue
            except exceptions.ICloudPyFailedLoginException as e:
                # icloudpy catches most sign-in errors -- a 409 or 401 with a
                # reason, any 5xx -- and re-raises them as this, which
                # subclasses ICloudPyException directly and so is not caught by
                # the API-response clause below. It only arises while signing
                # in, so it always takes the auth backoff.
                if not _handle_auth_transport_error(config, username, sync_state, e):
                    break
                continue
            except exceptions.ICloudPyServiceNotActivatedException as e:
                # A zone or service being unavailable says nothing about the
                # sign-in whenever it surfaces, so it never earns the
                # rate-limit backoff. Listed ahead of the broader catch
                # below because it subclasses it.
                if not _handle_sync_error(
                    config,
                    e,
                    drive_sync_interval,
                    photos_sync_interval,
                ):
                    break
                continue
            except (
                exceptions.ICloudPyAPIResponseException,
                requests.exceptions.RequestException,
            ) as e:
                # Any other failure raised after the sign-in succeeded is a
                # service problem, not an auth problem -- and must not earn
                # the backoff meant for "you are trying too often" either.
                if authenticated:
                    if not _handle_sync_error(
                        config,
                        e,
                        drive_sync_interval,
                        photos_sync_interval,
                    ):
                        break
                    continue
                # Apple refuses sign-in for reasons other than "2FA needed":
                # 409 when it is throttling the account, 5xx when it is
                # having a bad day, plus ordinary network faults. None of
                # these are fatal, but letting them escape kills the process
                # -- and with `restart: unless-stopped` that becomes a crash
                # loop that re-authenticates every few seconds, which is the
                # fastest possible way to deepen a throttle.
                if not _handle_auth_transport_error(config, username, sync_state, e):
                    break
                continue

        sleep_for = _calculate_next_sync_schedule(config, sync_state)
        _log_next_sync_time(sleep_for)

        if _should_exit_oneshot_mode(config):
            LOGGER.info(
                "All configured sync intervals are negative, exiting oneshot mode...",
            )
            break

        # Interruptible sleep -- poll the web-signal force-sync sentinels
        # every few seconds so the "Sync now" button stays responsive even
        # mid-long-interval. Without this, a user tap during a multi-hour
        # drive sleep would wait the full remaining duration.
        _interruptible_sleep(sleep_for)


def _interruptible_sleep(total_seconds: int) -> None:
    """Sleep up to ``total_seconds`` in short chunks, returning early
    when ``web_signals.pending_force_syncs()`` reports any sentinel.

    The ``import src.web_signals`` is best-effort so a vanilla mandarons
    build without the web-UI module still runs (it falls back to a
    single ``sleep(total_seconds)``).
    """
    _CHUNK = 2  # seconds — tradeoff: shorter = more responsive, more wakeups
    try:
        from src import web_signals as _ws
    except ImportError:  # pragma: no cover — vanilla-mandarons fallback
        sleep(total_seconds)
        return

    # Short intervals (<= one chunk) sleep in a single call so the
    # existing tests that count sleep invocations still match. The
    # chunking only matters for long intervals where the user might
    # tap "Sync now" mid-sleep -- those become multiple short sleeps
    # with a sentinel poll between each.
    if total_seconds <= _CHUNK:
        sleep(total_seconds)
        return

    remaining = total_seconds
    while remaining > 0:
        chunk = min(_CHUNK, remaining)
        sleep(chunk)
        remaining -= chunk
        if _ws.pending_force_syncs():
            return
