# Notifications

The notification system (`src/notify.py`) sends alerts for 2FA requirements and sync summaries across multiple providers.

## Responsibilities

- Send 2FA authentication required alerts
- Send sync summary notifications with statistics
- Support Discord, Telegram, Pushover, and SMTP providers
- Rate-limit 2FA alerts to once per 24 hours per service
- Include web UI URL in notifications when available

## Boundaries

Notifications are fire-and-forget — failures are logged and swallowed so they never break the sync loop.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `send(config, username, last_send, region, dashboard_url)` | Send 2FA alert (rate-limited) |
| `send_sync_summary(config, summary)` | Send sync completion summary |
| `send_trust_expiring(config, username, days_remaining, dashboard_url)` | Send trust cookie warning |

## Provider Configuration

| Provider | Config Keys | Notes |
|----------|------------|-------|
| Discord | `app.discord.webhook_url`, `username` | Webhook-based |
| Telegram | `app.telegram.bot_token`, `app.telegram.chat_id` | Bot API |
| Pushover | `app.pushover.user_key`, `app.pushover.api_token` | Mobile notifications |
| SMTP | `app.smtp.email`, `app.smtp.host`, `app.smtp.port`, `password` | Email with TLS |

## Invariants

- 2FA alerts are throttled to 24 hours (`THROTTLE_HOURS = 24`)
- `last_send` parameter tracks when notification was last sent
- Sync summaries are NOT rate-limited — sent for every qualifying sync
- `min_downloads` threshold filters low-activity sync summaries
- All notification failures are caught and logged — never crash the sync loop

## Dependencies

- **Depends on:** `config_parser`, `requests`, `smtplib`
- **Depended on by:** `sync.py`

## Tests

- `tests/test_notify.py` — notification tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_notify.py`

## Related Docs

- [Configuration](configuration.md)
- [Glossary](../glossary.md)
