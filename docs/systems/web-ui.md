# Web UI

The web UI (`src/web.py`) provides an optional Flask-based dashboard for monitoring sync status and completing 2FA re-authentication.

## Responsibilities

- Serve dashboard page showing sync status and config paths
- Show per-library sync state ("Syncing now", relative last-sync, or "Failed"
  with the last completion); list only libraries this container syncs
- Surface `reauth_needed` published by the loop when sync is stopped, instead
  of deriving health from on-disk signals alone
- End the sign-in retry wait as soon as any auth path completes a re-auth
  (the force-sync sentinel is deliberately separate — completing a sign-in
  does not queue a full re-enumeration)
- Handle Apple ID password submission and 2FA code entry, plus security-key
  (WebAuthn) relay for Apple IDs with a key enrolled
- Provide CSRF protection via cookie + token matching
- Display recent log lines
- Signal the sync loop for immediate force-sync via `web_signals.py`
- Show trust cookie expiry status

## Boundaries

The web UI runs in a daemon thread alongside the sync loop. It shares state through the filesystem (keyring, session cookies, log file). No new persistence layer — it reads config and log files directly.

## Key Entry Points

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Dashboard — sync status, config, last sync |
| `/auth` | GET | Authentication page — password + 2FA form |
| `/auth/password` | POST | Submit Apple ID password |
| `/auth/code` | POST | Submit 2FA verification code |
| `/auth/reset` | POST | Clear pending auth state |
| `/auth/forget-password` | POST | Delete the stored password, after checking the saved session signs in without it; refused while `ENV_ICLOUD_PASSWORD` is set |
| `/auth/security-key` | GET | Security-key page: the signer command for a pending challenge |
| `/auth/security-key/start` | POST | Sign in with the typed password (or a stored one) and fetch Apple's WebAuthn challenge |
| `/auth/security-key` | POST | Submit the signed assertion; on success the sync loop wakes |
| `/api/sync/trigger/<service>` | POST | Force immediate sync (Drive/Photos) |
| `/api/logs` | GET | Recent log lines |

## Security Model

**No built-in authentication.** The trust boundary is the network:

- `host: 127.0.0.1` (default) — loopback only, safe
- `host: 0.0.0.0` — exposes credential-accepting form to all interfaces; MUST use a reverse proxy with auth (Cloudflare Access, Authelia, Tailscale)

**CSRF protection:** State-changing endpoints require a CSRF cookie plus a matching `X-CSRF-Token` header. Scripted callers must load a page first to obtain the cookie.

**Pending auth TTL:** In-memory password expires after 10 minutes (`_PENDING_AUTH_TTL_SECONDS`).

## Invariants

- The web UI thread is a daemon — it dies when the main process exits
- `_PENDING_AUTH` holds a half-finished sign-in (and with it the password) in process memory only while a code or key is pending; no sign-in from the web UI ever writes the password to the keyring
- `_AUTH_LOCK` protects concurrent access to pending auth state
- `web_signals.py` uses sentinel files for cross-thread communication
- `public_url` in config is embedded in notification links for mobile re-auth

## Dependencies

- **Depends on:** `config_parser`, `web_signals`, `src` (constants)
- **Depended on by:** `main.py` (spawns web thread), `sync.py` (reads signals)

## Tests

- `tests/test_web.py` — web UI route tests
- `tests/test_web_signals.py` — cross-thread signalling tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_web.py`

## Related Docs

- [Authentication Flow](../flows/authentication.md)
- [Configuration](configuration.md)
