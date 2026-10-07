# Authentication Flow

This document describes how iCloud Docker authenticates with Apple's iCloud services.

## Overview

Authentication is managed by `sync.py` and delegates to iCloudPy for the actual API handshake. The system supports both password-based and 2FA flows, with keyring persistence for the password.

## Two modes

Whether a password is configured decides how the container behaves months later. There is no flag for this; the absence of a password *is* the switch.

| | password stored | no password (session-only) |
|---|---|---|
| Unattended for | indefinitely | until Apple stops accepting the saved session |
| On session expiry | signs in again itself; a human supplies the second factor | sync stops and waits for a human to sign in |
| Credential at rest | Apple ID password, cleartext on a headless host (`keyrings.alt.file.PlaintextKeyring`) | the session in `/config/session_data` only |
| Client class | `ICloudPyService` | `SessionOnlyICloudPyService` |

Switching an existing container to session-only takes both halves: unset `ENV_ICLOUD_PASSWORD` *and* delete the keyring entry, because `_retrieve_password` copies the environment variable into the keyring on every cycle it is set. The README has the one-liner.

`/auth/refresh-trust` and `_maybe_refresh_trust` both work in session-only mode — `trust_session` and the 2FA push are session-token operations, no password involved — so the dashboard's "Refresh trust" button is still the cheapest way to roll the window forward. That the refresh keeps a password-free container alive indefinitely is untested against Apple over a full trust lifetime; the mechanism needs no password, which is a different claim.

## Steps

1. **Password retrieval** (`_retrieve_password()`)
   - Check `ENV_ICLOUD_PASSWORD` environment variable
   - If set: store in keyring via `utils.store_password_in_keyring()`, return it
   - If not set: retrieve from keyring via `utils.get_password_from_keyring()`
   - Raises `ICloudPyNoStoredPasswordAvailableException` if neither is available. `_authenticate_and_get_api()` catches that and passes `password=None`, which selects session-only mode rather than failing the cycle

2. **API instance creation** (`get_api_instance()`)
   - Creates `ICloudPyService` with username + password
   - For China region: uses different endpoints (`icloud.com.cn`)
   - Cookie directory defaults to `/config/session_data`
   - With `password=None`, creates `SessionOnlyICloudPyService` instead. Its `authenticate()` validates the saved session token and stops there: icloudpy's own fallback would attempt a full SRP sign-in, which cannot succeed without a password and would post a placeholder credential to Apple's sign-in endpoint on every retry. A missing session, a session Apple rejects (401/421/450) or a forced refresh raises `ICloudPyNoStoredPasswordAvailableException` instead, so it lands in the handler below. Any other API error propagates untouched — a 503 leaves the session perfectly good, and reporting an outage as an expired session would send the user off to re-authenticate for nothing

3. **2FA check** (`api.requires_2sa`)
   - If False: authentication succeeded, proceed to sync
   - If True: enter 2FA handling flow

4. **2FA handling** (`_handle_2fa_required()`)
   - Request Apple's 2FA code push (best-effort, once per re-auth episode —
     latched so retries don't re-push and trip rate limits)
   - Send notification alert (24-hour rate limit), including the webhook
     event `two_factor_required` (or `security_key_required`) when
     `app.webhooks.url` is set — the webhook is a transport in the same
     dispatch, so it shares that rate limit
   - Sleep for `retry_login_interval` seconds
   - Return to main loop to retry authentication
   - If `retry_login_interval < 0`: exit immediately (oneshot auth)
   - Security-key accounts (`_detect_security_key_account()`: Apple answers with an `fsaChallenge`): no 2FA push, no Telegram code listener, and the notification points at `/auth`, since Apple sends such an account no code

5. **No usable credential** (`_handle_password_error()`)
   - Reached only when no password is configured *and* the saved session cannot be resumed. Logs which of the two it was, marks the web UI's auth state blocked, sends the notification, and waits `retry_login_interval` — the same backoff as the 2FA path, so Apple's sign-in is never hammered
   - Recovery: `docker exec -it icloud /bin/sh -c "su-exec abc icloud --username=… --session-directory=/config/session_data"`, answering **no** to `Save password in keyring?` to stay password-free. The dashboard's `/auth` form works too but always persists the password to the keyring, which switches the container to the other mode
   - `retry_login_interval < 0` exits instead of retrying, as elsewhere
   - Sign-in failures that reach `_handle_auth_transport_error` in session-only mode are split by `_needs_a_human`. icloudpy keeps the HTTP status on the exception only for a non-JSON body or its own re-auth statuses, so an `ICloudPyAPIResponseException` with `code` of `None` (a JSON-bodied 401, say) cannot be told apart from a rejected session: that one gets the "re-auth required" notification, throttled to one message a day, because only a human can revive such a container. A 5xx that kept its status, a dropped connection or a timeout is an outage and gets no such notification — waking someone daily to re-authenticate over Apple having a bad hour is exactly what the split avoids
   - Either way the loop publishes `sign_in_failed` so the dashboard stops claiming health; its wording for that reason ("this can be an outage; the loop keeps retrying") allows for both and asks for nothing

6. **Trust cookie monitoring** (`_maybe_warn_trust_expiring()`)
   - Read `X-APPLE-WEBAUTH-HSA-TRUST` cookie expiry
   - Compare against `app.trust_expiry_warn_days` threshold
   - Send warning notification once per cookie value (debounced)
   - The notification distinguishes a *revoked* trust token (Apple dropped
     trust on a security event — new device, password/key change — where a
     refresh schedule cannot help) from an ordinary expiry

7. **Proactive trust refresh** (`_maybe_refresh_trust()`)
   - When the trust cookie has fewer than `app.trust_refresh_days` days left
     (default 14, 0 disables, must exceed `trust_expiry_warn_days`), call
     `trust_session` on the live session so icloudpy persists a fresh token
   - Best-effort: a failed or declined refresh is logged and sync continues —
     the session in hand is still valid
   - Goal: a container restart after months of uptime resumes without a
     second factor

## China Region

For China server users, the API uses different endpoints:
- Home: `https://www.icloud.com.cn`
- Setup: `https://setup.icloud.com.cn/setup/ws/1`

Set `app.region: china` in config to enable.

## Web UI Authentication

The web UI provides an alternative auth flow:
1. User visits `/auth` page
2. Submits Apple ID password via `POST /auth/password`
3. Password stored in `_PENDING_AUTH` (in-memory, 10-min TTL)
4. 2FA code submitted via `POST /auth/code`
5. On success: trust session established, keyring updated

Note the last step: the dashboard always persists the password to the keyring, so using it to recover a session-only container switches that container to password-stored mode. `icloud --delete-from-keyring` undoes it; the `docker exec … icloud …` flow avoids it in the first place by letting you decline the "Save password in keyring?" prompt.

For an Apple ID with security keys enrolled, Apple returns a WebAuthn challenge instead of a code:
1. `POST /auth/security-key/start` signs in and packs Apple's challenge into one base64 blob
2. The page offers `uv run …/src/icloud_sign.py <blob>` for the machine holding the key (WebAuthn redirection: the challenge travels to the key, only the signed assertion travels back)
3. `src/icloud_sign.py` prints what it will sign, asks for a touch, and copies the assertion
4. `POST /auth/security-key` hands the assertion to icloudpy (`confirm_security_key`), trusts the session, and wakes the sync loop

## Cross-Cutting Concerns

- **Error handling:** All auth failures are caught and trigger retry with notification
- **Logging:** Auth events logged at INFO/ERROR level
- **Security:** Passwords never logged; stored in keyring only
- **Thread safety:** Web UI auth uses `_AUTH_LOCK` mutex

## Related Docs

- [Sync Engine](../systems/sync-engine.md)
- [Web UI](../systems/web-ui.md)
- [Configuration](../systems/configuration.md)
