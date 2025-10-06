# Example Configuration for Sync Summary Notifications

This document provides examples of how to configure sync summary notifications
for icloud-docker.

## Basic Setup

To enable sync summary notifications, add the following to your `config.yaml`:

```yaml
app:
  # ... existing configuration ...
  
  notifications:
    # Configure your notification providers (existing 2FA notifications)
    telegram:
      bot_token: "YOUR_BOT_TOKEN"
      chat_id: "YOUR_CHAT_ID"
    
    discord:
      webhook_url: "YOUR_WEBHOOK_URL"
      username: "icloud-docker"
    
    pushover:
      user_key: "YOUR_USER_KEY"
      api_token: "YOUR_API_TOKEN"
    
    smtp:
      email: "sender@example.com"
      to: "recipient@example.com"
      host: "smtp.gmail.com"
      port: 587
      password: "YOUR_PASSWORD"
    
    # NEW: Sync summary notification settings
    sync_summary:
      enabled: true  # Enable sync summary notifications (default: false)
      on_success: true  # Send summary after successful syncs (default: true)
      on_error: true  # Send summary when errors occur (default: true)
      min_downloads: 1  # Only send if at least N items downloaded (default: 1)
                        # Set to 0 to always send summaries regardless of download count
```

## Configuration Options

### `enabled` (default: `false`)
Controls whether sync summary notifications are sent at all. Must be `true` to enable the feature.

### `on_success` (default: `true`)
When `true`, sends a notification after successful sync operations (syncs with no errors).

### `on_error` (default: `true`)
When `true`, sends a notification when sync operations encounter errors.

### `min_downloads` (default: `1`)
Minimum number of downloaded items (files or photos) required to trigger a notification.
- Set to `0` to always send notifications, even if no new items were downloaded
- Set to higher values to only get notified for substantial syncs

## Example Scenarios

### Scenario 1: Only notify on errors
```yaml
sync_summary:
  enabled: true
  on_success: false  # Don't notify on successful syncs
  on_error: true     # Only notify when errors occur
  min_downloads: 0   # Notify even if no downloads (to catch errors)
```

### Scenario 2: Only notify for significant syncs
```yaml
sync_summary:
  enabled: true
  on_success: true
  on_error: true
  min_downloads: 10  # Only notify if at least 10 items were downloaded
```

### Scenario 3: Always stay informed
```yaml
sync_summary:
  enabled: true
  on_success: true
  on_error: true
  min_downloads: 0  # Notify for every sync, even if nothing changed
```

## Example Notification Messages

### Successful Sync
```
✅ iCloud Sync Complete

📁 Drive:
  • Downloaded: 15 files (2.3 GB)
  • Skipped: 234 files (up-to-date)
  • Removed: 3 obsolete files
  • Duration: 4m 32s

📷 Photos:
  • Downloaded: 42 photos (1.8 GB)
  • Hard-linked: 128 photos
  • Storage saved: 5.4 GB
  • Albums: All Photos, Favorites, Family
  • Duration: 2m 15s
```

### Sync with Errors
```
⚠️ iCloud Sync Completed with Errors

📁 Drive:
  • Downloaded: 3 files (150 MB)
  • Duration: 1m 20s
  • Errors: 2 failed

📷 Photos:
  • Downloaded: 10 photos (450 MB)
  • Duration: 45s
  • Errors: 1 failed

Failed items:
  • /Documents/Report.pdf (timeout)
  • /Photos/IMG_1234.heic (File not found)
```

## Notification Behavior

1. **No Throttling**: Unlike 2FA notifications (which are throttled to once per 24 hours), sync summary notifications are sent after each sync cycle.

2. **Multi-Provider**: Sync summaries are sent to all configured notification providers (Telegram, Discord, Pushover, SMTP).

3. **Backward Compatible**: If `sync_summary` section is not configured, the feature is disabled by default, maintaining existing behavior.

4. **Independent from 2FA**: Sync summary notifications work independently from 2FA notifications. You can receive both types of notifications.

## Troubleshooting

### Not receiving notifications?
1. Verify `enabled: true` is set in the `sync_summary` section
2. Check that `min_downloads` threshold is set appropriately
3. Ensure at least one notification provider (telegram, discord, pushover, or smtp) is properly configured
4. Check container logs for any error messages related to notifications

### Too many notifications?
- Increase `min_downloads` to reduce notification frequency
- Set `on_success: false` to only get error notifications
- Consider adjusting your sync intervals in the `drive` and `photos` sections

### Want more details?
The summary provides aggregate statistics. For detailed information about individual files, check the container logs.
