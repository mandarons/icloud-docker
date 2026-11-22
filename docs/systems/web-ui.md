# Web UI

The web UI (`src/web.py`) provides an optional Flask-based dashboard for monitoring sync status, completing 2FA re-authentication, and changing a few settings from a browser.

## Responsibilities

- Serve the dashboard: one headline, then the account's row with each service
  under it — a sentence describing its state, an optional detail, and at most
  one action (**Sign in**, **Sign in again**, **Refresh trust**) shown only when
  something needs it
- Report a pass that is still running ("Syncing now · started 5 min ago") rather
  than only the previous pass's completion, and refresh the page every 30
  seconds while a pass runs and the tab is visible; a hidden tab skips the tick
  and reloads as soon as it becomes visible again
- Show per-library sync state ("Syncing now", relative last-sync, or "Failed"
  with the last completion); list only libraries this container syncs. A
  library Apple is still indexing says "Apple is still indexing this library ·
  downloading, cleanup paused" until its `indexing_state` reads `FINISHED`
- Summarise the log: count recent errors and name the most common one, skipping
  only config defaults and the default notices on every pass
- Present the account as a card: signed in or not, trusted until when, whether
  an Apple ID password is stored (and that the keyring is a plain text file on
  a headless host), and **Sign in again**; flag a stored copy as out of date
  when a sign-in used a different password, and offer **Remove stored password**
  (`/auth/forget-password`) — never while `ENV_ICLOUD_PASSWORD` is set, since
  the loop would write the password back
- Offer a Settings page (`/settings`): common settings first with a label on the
  left and the value on the right, the rest under Advanced, and the *source* of
  each value — `config.yaml`, a default, or the environment. Secrets are
  reported as set or not, never shown. Switches save in place; editable values
  post with CSRF and land back on the page
- Surface `reauth_needed` published by the loop when sync is stopped, instead
  of deriving health from on-disk signals alone
- End the sign-in retry wait as soon as any auth path completes a re-auth
  (the force-sync sentinel is deliberately separate — completing a sign-in
  does not queue a full re-enumeration)
- Handle Apple ID password submission and 2FA code entry, plus security-key
  (WebAuthn) relay for Apple IDs with a key enrolled. Every password form
  carries the Apple ID in a read-only `autocomplete="username"` field so
  password managers can save it; pasting a security-key signature submits it,
  and where the clipboard is readable (https or localhost) a
  **Paste & complete sign-in** button does both
- Follow the system's light or dark appearance, keep the header on one line on
  phones, and centre pages in one column on wide screens
- Provide CSRF protection via cookie + token matching
- Display recent log lines
- Signal the sync loop for immediate force-sync via `web_signals.py`
- Show trust cookie expiry status

## Boundaries

The web UI runs in a daemon thread alongside the sync loop. It shares state through the filesystem (keyring, session cookies, log file, and the state file `web_signals` owns). The UI itself adds no database.

It does **write** in two places. `web_signals.py` writes the state file under a
re-entrant lock, each save to a temp file named by process and thread. The
Settings page writes `config.yaml` — see below.

### What a settings write does

`src/settings_view.py` reads the file with ruamel, so a save keeps the file's
comments. `_save_document` then:

1. copies the current file to `config.yaml.bak-<YYYYmmdd-HHMMSS-microseconds>`;
2. prunes older backups, keeping the newest **five** that match that stamp
   pattern (a hand-made backup has a different name and is never touched);
3. writes the new document to a temp file in the same directory, reads it back
   with the app's own reader (`read_config`), and only then `os.replace`s it
   into place, preserving the original mode.

A document the app could not read never lands. **Seven of the settings are
editable:** `drive.sync_interval`, `photos.sync_interval`,
`photos.use_hardlinks`, and `app.notifications.sync_summary.{enabled,on_success,on_error,min_downloads}`.
Everything else is display-only and says so.

## Key Entry Points

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Dashboard — headline, per-service state, log summary |
| `/api/health` | GET | `200 {"state": "ok"}` when the config file is readable, `503 {"state": "config_missing"}` when it is not. A `2fa_required` session is still `200`: the dashboard must stay reachable to re-auth |
| `/api/status` | GET | Dashboard state as JSON: services, libraries (including indexing), sync state, auth mode |
| `/api/logs` | GET | Recent log lines |
| `/api/sync` | POST | Queue an immediate sync for `service=drive`, `photos` or `all` (touches a sentinel; repeated taps while queued are a no-op) |
| `/auth` | GET | Account card — sign-in state, trust expiry, stored password, sign-in form |
| `/auth/password` | POST | Submit Apple ID password for this sign-in only |
| `/auth/code` | POST | Submit 2FA verification code |
| `/auth/reset` | POST | Clear pending auth state |
| `/auth/forget-password` | POST | Delete the stored password, after checking the saved session signs in without it; refused while `ENV_ICLOUD_PASSWORD` is set |
| `/auth/refresh-trust` | POST | Re-auth from the saved session (or the stored password) without retyping it |
| `/auth/security-key` | GET | Security-key page: the signer command for a pending challenge |
| `/auth/security-key/start` | POST | Sign in with the typed password (or a stored one) and fetch Apple's WebAuthn challenge |
| `/auth/security-key` | POST | Submit the signed assertion; on success the sync loop wakes |
| `/settings` | GET | Settings page |
| `/settings` | POST | Save one editable setting (CSRF required) |

## Security Model

**No built-in authentication.** The trust boundary is the network:

- `host: 127.0.0.1` (default) — loopback only, safe
- `host: 0.0.0.0` — exposes credential-accepting form to all interfaces; MUST use a reverse proxy with auth (Cloudflare Access, Authelia, Tailscale)

**CSRF protection:** State-changing endpoints require a CSRF cookie plus a matching `X-CSRF-Token` header. Scripted callers must load a page first to obtain the cookie.

**Settings writes are bounded but not harmless.** Anyone who can reach the UI can change the seven editable keys — both sync intervals, photo hardlinking, and the notification summary options. They cannot set a credential, a password, or a destination. The network trust boundary above therefore governs *writes* as well as sign-ins.

**Password storage is opt-in.** No web sign-in writes the password to the keyring: `/auth/password`, `/auth/code` and both security-key routes use the typed password for that sign-in only, and never overwrite a stored copy. A password is stored only through `ENV_ICLOUD_PASSWORD` or a yes at the `icloud` command's prompt; on a headless host the keyring is a plain-text file. `/auth/forget-password` removes a stored password after checking the saved session signs in without it.

**Pending auth TTL:** A half-finished sign-in — and with it the password, in memory only — expires after 10 minutes (`_PENDING_AUTH_TTL_SECONDS`).

**China region:** both web sign-in paths and the sync loop build their endpoints from one constant pair in `src/__init__.py`, so `app.region: china` is honoured consistently. A handler that built its own service without them signed a China-region Apple ID against the global hosts and failed with `KeyError: 'webservices'`.

## Invariants

- The web UI thread is a daemon — it dies when the main process exits
- `_PENDING_AUTH` holds a half-finished sign-in (and with it the password) in process memory only while a code or key is pending; no sign-in from the web UI ever writes the password to the keyring
- `_AUTH_LOCK` protects concurrent access to pending auth state
- `web_signals.py` uses sentinel files for cross-thread communication, and its
  writers hold one re-entrant lock across load, change and save
- `public_url` in config is embedded in notification links for mobile re-auth

## Dependencies

- **Depends on:** `config_parser`, `web_signals`, `settings_view`, `src` (constants)
- **Depended on by:** `main.py` (spawns web thread), `sync.py` (reads signals)

## Tests

- `tests/test_web.py` — web UI route tests
- `tests/test_web_signals.py` — cross-thread signalling tests
- `tests/test_settings_view.py` — settings list, write path and page
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_web.py`

## Related Docs

- [Authentication Flow](../flows/authentication.md)
- [Configuration](configuration.md)
