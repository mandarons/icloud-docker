# Notifications

The notification system (`src/notify.py`) sends alerts for 2FA requirements and sync summaries across multiple providers.

## Responsibilities

- Send 2FA authentication required alerts
- Send sync summary notifications with statistics
- Support Discord, Telegram, Pushover, and SMTP providers
- Ping monitoring webhooks (Healthchecks.io style) at each sync-cycle boundary
- Rate-limit 2FA alerts to once per 24 hours per service
- Include web UI URL in notifications when available

## Boundaries

Notifications are fire-and-forget — failures are logged and swallowed so they never break the sync loop.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `send(config, username, last_send, region, dashboard_url, reply_prompt)` | Send an auth alert (rate-limited); `reply_prompt=True` (2FA handler only) swaps Telegram's copy for the reply prompt when `app.telegram.listen` is on |
| `send_sync_summary(config, summary)` | Send sync completion summary |
| `send_trust_expiring(config, username, days_remaining, dashboard_url)` | Send trust cookie warning |
| `ping_webhook(config, event)` | GET `app.webhooks.<event>` (`start`/`success`/`failure`) if configured |

## Provider Configuration

| Provider | Config Keys | Notes |
|----------|------------|-------|
| Discord | `app.discord.webhook_url`, `username` | Webhook-based |
| Telegram | `app.telegram.bot_token`, `app.telegram.chat_id` | Bot API |
| Pushover | `app.pushover.user_key`, `app.pushover.api_token` | Mobile notifications |
| SMTP | `app.smtp.email`, `app.smtp.host`, `app.smtp.port`, `password` | Email with TLS |
| Webhooks | `app.webhooks.start`, `success`, `failure` | Plain GET per cycle boundary; each key optional |

## Invariants

- 2FA alerts are throttled to 24 hours (`THROTTLE_HOURS = 24`)
- `last_send` parameter tracks when notification was last sent
- Sync summaries are NOT rate-limited — sent for every qualifying sync
- `min_downloads` threshold filters low-activity sync summaries
- All notification failures are caught and logged — never crash the sync loop
- Webhook pings are NOT rate-limited — one per cycle boundary, and one `failure` per retry while a sign-in stays broken (a monitor needs the repeat to stay red)
- A ping URL is a credential and is never logged BY THIS APP, including via the `requests` exception text — only the exception type. At `app.logger.level: debug`, `urllib3.connectionpool` logs request paths (which carry the ping UUID) to the root handlers; that is equally true of the Telegram bot token today, and silencing `urllib3` globally would cost more than it buys
- Every webhook request uses `WEBHOOK_TIMEOUT_SECONDS` (10s) and no retries
- A cycle that synced nothing — every due service skipped by the mount marker, or nothing configured — pings `failure`, not `success` (`_cycle_did_nothing`). A service that merely was not due this cycle is NOT that case
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
