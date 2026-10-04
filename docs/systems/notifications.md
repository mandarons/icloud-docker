# Notifications

The notification system (`src/notify.py`) sends alerts for 2FA requirements and sync summaries across multiple providers.

## Responsibilities

- Send 2FA authentication required alerts
- Send sync summary notifications with statistics
- Support Discord, Telegram, Pushover, and SMTP providers
- Ping monitoring webhooks (Healthchecks.io style) at each sync-cycle boundary
- POST every notification and sync-cycle event as JSON to one receiver endpoint
- Rate-limit 2FA alerts to once per 24 hours per service
- Include web UI URL in notifications when available

## Boundaries

Notifications are fire-and-forget — failures are logged and swallowed so they never break the sync loop.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `send(config, username, last_send, region, dashboard_url, reply_prompt, event)` | Send an auth alert (rate-limited); `reply_prompt=True` (2FA handler only) swaps Telegram's copy for the reply prompt when `app.telegram.listen` is on; `event` names which webhook event this alert is |
| `send_sync_summary(config, summary)` | Send sync completion summary |
| `send_trust_expiring(config, username, days_remaining, dashboard_url)` | Send trust cookie warning |
| `ping_webhook(config, event)` | GET `app.webhooks.<event>` (`start`/`success`/`failure`) if configured |
| `post_event_to_webhook(config, event, message, data)` | POST one event to `app.webhooks.url` as JSON |
| `notify_webhook(config, event, message, last_send, dry_run, data)` | Throttled webhook send; called from the same dispatch as `notify_telegram` |
| `send_cycle_event(config, boundary, message, data)` | Report a cycle boundary on both webhook transports |
| `summary_event_data(summary)` | Structured form of a `SyncSummary` for a receiver |
| `warn_unknown_webhook_events(config)` | One warning at container start for misspelled `app.webhooks.events` entries |

## Provider Configuration

| Provider | Config Keys | Notes |
|----------|------------|-------|
| Discord | `app.discord.webhook_url`, `username` | Webhook-based |
| Telegram | `app.telegram.bot_token`, `app.telegram.chat_id` | Bot API |
| Pushover | `app.pushover.user_key`, `app.pushover.api_token` | Mobile notifications |
| SMTP | `app.smtp.email`, `app.smtp.host`, `app.smtp.port`, `password` | Email with TLS |
| Webhooks (ping) | `app.webhooks.start`, `success`, `failure` | Plain GET per cycle boundary; each key optional |
| Webhooks (events) | `app.webhooks.url`, `events`, `headers` | JSON POST per event; `events` filters, `headers` authenticates |

## Webhook Events

| Event | When | `data` |
|-------|------|--------|
| `sync_started` | Signed in, about to sync | — |
| `sync_succeeded` | Cycle completed clean, and a service ran | `summary_event_data()` |
| `sync_failed` | Cycle completed with errors, synced nothing, or a retry handler ran | `summary_event_data()`, plus `reason` (always present) |
| `sync_summary` | `send_sync_summary()` passed its gates | `summary_event_data()` |
| `two_factor_required` | `send()` from `_handle_2fa_required` | `username`, `dashboard_url` |
| `security_key_required` | Same, for an account Apple answers with an `fsaChallenge` | `username`, `dashboard_url` |
| `password_missing` | `send()` from `_handle_password_error` | `username`, `dashboard_url` |
| `sign_in_failed` | `send()` from `_handle_auth_transport_error`, which fires it only for `ICloudPyFailedLoginException` | `username`, `dashboard_url` |
| `trust_expiring` | `send_trust_expiring()` | `username`, `dashboard_url`, `days_remaining` |
| `trust_refreshed` | `_maybe_refresh_trust()` succeeded — no other transport reports it | `expires_at` (omitted if unreadable), `days_remaining_before` |

`sync_failed` reasons: `download_errors`, `mount_marker_missing`, `nothing_synced`, `two_factor_required`, `security_key_required`, `password_missing`, `sign_in_failed`, `sign_in_error` (the sign-in attempt did not complete: a network fault or an Apple service error), `sync_error`. `WEBHOOK_EVENTS` is the authoritative event list and the only names `app.webhooks.events` recognises.

Guidance for receivers: the alert events are throttled human notices (one per day at most), so automation that needs current state should key on `sync_failed` and its `data.reason`, which is sent every cycle and every retry.

## Invariants

- 2FA alerts are throttled to 24 hours (`THROTTLE_HOURS = 24`)
- `last_send` parameter tracks when notification was last sent
- Sync summaries are NOT rate-limited — sent for every qualifying sync
- `min_downloads` threshold filters low-activity sync summaries
- All notification failures are caught and logged — never crash the sync loop
- Webhook pings are NOT rate-limited — one per cycle boundary, and one `failure` per retry while a sign-in stays broken (a monitor needs the repeat to stay red)
- Webhook URLs and header values are credentials and are never logged BY THIS APP, including via the `requests` exception text — only the exception type. At `app.logger.level: debug`, `urllib3.connectionpool` logs request paths (which carry the ping UUID) to the root handlers; that is equally true of the Telegram bot token today, and silencing `urllib3` globally would cost more than it buys
- Every webhook request uses `WEBHOOK_TIMEOUT_SECONDS` (10s) and no retries
- The alert events ride `send()` / `send_trust_expiring()`, so they inherit the SAME 24h throttle as the other transports — `notify_webhook` must stay in that dispatch rather than becoming a parallel path
- `notify_webhook` checks for a configured URL BEFORE the throttle, so an install with no webhook gains no log line
- `_send_webhook_no_throttle` checks the URL before answering a dry run; without it a dry-run summary reports "sent" on an install with no webhook
- The payload shape (`event`, `message`, `timestamp`, `data`) is part of the config surface — changing a key is a breaking change for receivers
- A cycle that synced nothing — every due service skipped by the mount marker, or nothing configured — pings `failure`, not `success` (`_cycle_nothing_synced_reason`, which also names which). A service that merely was not due this cycle is NOT that case
- Only Photos counts failed downloads into its stats (`PhotoStats.errors`); `DriveStats.errors` is never populated in production, so a failed Drive download does not reach the cycle boundary. Documented rather than fixed here

## Dependencies

- **Depends on:** `config_parser`, `requests`, `smtplib`
- **Depended on by:** `sync.py`

## Tests

- `tests/test_notify.py` — notification tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_notify.py`

## Related Docs

- [Configuration](configuration.md)
- [Glossary](../glossary.md)
