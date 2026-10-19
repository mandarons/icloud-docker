# Web UI

The web UI (`src/web.py`) provides an optional Flask-based dashboard for monitoring sync status and completing 2FA re-authentication.

## Responsibilities

- Serve dashboard page showing sync status and config paths
- Show per-library sync state ("Syncing now", relative last-sync, or "Failed"
  with the last completion); list only libraries this container syncs. A
  library Apple is still indexing says "Apple is still indexing this library ·
  downloading, cleanup paused" until its `indexing_state` reads `FINISHED`
- Say whether an Apple ID password is stored (and that the keyring is a plain
  text file on a headless host), flag a stored copy as out of date when a
  sign-in used a different password, and offer **Remove stored password**
  (`/auth/forget-password`) — never while `ENV_ICLOUD_PASSWORD` is set, since
  the loop would write the password back
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
| `/auth/password` | POST | Submit Apple ID password for this sign-in only |
| `/auth/code` | POST | Submit 2FA verification code |
| `/auth/reset` | POST | Clear pending auth state |
| `/auth/forget-password` | POST | Delete the stored password, after checking the saved session signs in without it; refused while `ENV_ICLOUD_PASSWORD` is set |
| `/auth/refresh-trust` | POST | Re-auth from the saved session (or the stored password) without retyping it |
| `/auth/security-key` | GET | Security-key page: the signer command for a pending challenge |
| `/auth/security-key/start` | POST | Sign in with the typed password (or a stored one) and fetch Apple's WebAuthn challenge |
| `/auth/security-key` | POST | Submit the signed assertion; on success the sync loop wakes |
| `/api/status` | GET | Dashboard state as JSON: services, libraries (including indexing), sync state, auth mode |
| `/api/sync/trigger/<service>` | POST | Force immediate sync (Drive/Photos) |
| `/api/logs` | GET | Recent log lines |

## Security Model

**No built-in authentication.** The trust boundary is the network:

- `host: 127.0.0.1` (default) — loopback only, safe
- `host: 0.0.0.0` — exposes credential-accepting form to all interfaces; MUST use a reverse proxy with auth (Cloudflare Access, Authelia, Tailscale)

**CSRF protection:** State-changing endpoints require a CSRF cookie plus a matching `X-CSRF-Token` header. Scripted callers must load a page first to obtain the cookie.

**Password storage is opt-in.** No web sign-in writes the password to the keyring: `/auth/password`, `/auth/code` and both security-key routes use the typed password for that sign-in only, and never overwrite a stored copy. A password is stored only through `ENV_ICLOUD_PASSWORD` or a yes at the `icloud` command's prompt; on a headless host the keyring is a plain-text file. `/auth/forget-password` removes a stored password after checking the saved session signs in without it.

**Pending auth TTL:** A half-finished sign-in — and with it the password, in memory only — expires after 10 minutes (`_PENDING_AUTH_TTL_SECONDS`).

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
