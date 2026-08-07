# Authentication Flow

This document describes how iCloud Docker authenticates with Apple's iCloud services.

## Overview

Authentication is managed by `sync.py` and delegates to iCloudPy for the actual API handshake. The system supports both password-based and 2FA flows, with keyring persistence for the password.

## Steps

1. **Password retrieval** (`_retrieve_password()`)
   - Check `ENV_ICLOUD_PASSWORD` environment variable
   - If set: store in keyring via `utils.store_password_in_keyring()`, return it
   - If not set: retrieve from keyring via `utils.get_password_from_keyring()`
   - Raises `ICloudPyNoStoredPasswordAvailableException` if neither is available

2. **API instance creation** (`get_api_instance()`)
   - Creates `ICloudPyService` with username + password
   - For China region: uses different endpoints (`icloud.com.cn`)
   - Cookie directory defaults to `/config/session_data`

3. **2FA check** (`api.requires_2sa`)
   - If False: authentication succeeded, proceed to sync
   - If True: enter 2FA handling flow

4. **2FA handling** (`_handle_2fa_required()`)
   - Send notification alert (24-hour rate limit)
   - Sleep for `retry_login_interval` seconds
   - Return to main loop to retry authentication
   - If `retry_login_interval < 0`: exit immediately (oneshot auth)

5. **Trust cookie monitoring** (`_maybe_warn_trust_expiring()`)
   - Read `X-APPLE-WEBAUTH-HSA-TRUST` cookie expiry
   - Compare against `app.trust_expiry_warn_days` threshold
   - Send warning notification once per cookie value (debounced)

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

## Cross-Cutting Concerns

- **Error handling:** All auth failures are caught and trigger retry with notification
- **Logging:** Auth events logged at INFO/ERROR level
- **Security:** Passwords never logged; stored in keyring only
- **Thread safety:** Web UI auth uses `_AUTH_LOCK` mutex

## Related Docs

- [Sync Engine](../systems/sync-engine.md)
- [Web UI](../systems/web-ui.md)
- [Configuration](../systems/configuration.md)
