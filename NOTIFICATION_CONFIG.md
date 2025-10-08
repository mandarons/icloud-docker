# Notification Configuration Guide

iCloud-docker supports comprehensive notification capabilities to keep you informed about sync operations, authentication status, and potential issues. This guide covers all notification features and configuration options.

## Overview

The notification system supports two main types of alerts:

1. **2FA Authentication Alerts** - Critical notifications when iCloud authentication expires
2. **Sync Summary Notifications** - Detailed reports after each sync cycle with statistics

## Notification Services

### Supported Services

| Service | Use Case | Features |
|---------|----------|----------|
| **Discord** | Team/Server notifications | Rich formatting, webhooks, persistent history |
| **Telegram** | Personal/Mobile alerts | Instant delivery, group support, multimedia |
| **Pushover** | Dedicated mobile notifications | Priority levels, custom sounds, offline delivery |
| **Email (SMTP)** | Universal compatibility | UTF-8 support, custom formatting, professional |

### Service Configuration

#### Discord
```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
    username: "icloud-sync"  # Optional: Custom bot name (default: icloud-docker)
```

**Setup Steps:**
1. Go to your Discord server settings
2. Navigate to Integrations → Webhooks
3. Create a new webhook or edit existing one
4. Copy the webhook URL
5. Optionally customize the username

#### Telegram
```yaml
app:
  telegram:
    bot_token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    chat_id: "123456789"  # Can be user ID or group chat ID
```

**Setup Steps:**
1. Message @BotFather on Telegram
2. Use `/newbot` command and follow instructions
3. Save the bot token provided
4. Add your bot to desired chat or use personal chat
5. Get your chat ID using @userinfobot or @RawDataBot

#### Pushover
```yaml
app:
  pushover:
    user_key: "your-30-char-user-key"
    api_token: "your-30-char-app-token"
```

**Setup Steps:**
1. Sign up at [Pushover.net](https://pushover.net)
2. Note your user key from the dashboard
3. Create a new application to get an API token
4. Install Pushover app on your mobile device

#### Email (SMTP)
```yaml
app:
  smtp:
    email: "icloud-sync@yourdomain.com"      # Sender address
    to: "admin@yourdomain.com"               # Recipient (optional, defaults to sender)
    username: "smtp-username"                # Optional: If different from email
    password: "your-app-password"            # App password or SMTP password
    host: "smtp.gmail.com"                   # SMTP server
    port: 587                                # SMTP port (587 for TLS, 465 for SSL, 25 for plain)
    no_tls: false                           # Set to true if TLS is not supported
```

**Popular SMTP Settings:**
- **Gmail**: `smtp.gmail.com:587` (requires app password)
- **Outlook**: `smtp-mail.outlook.com:587`
- **Yahoo**: `smtp.mail.yahoo.com:587`
- **AWS SES**: `email-smtp.region.amazonaws.com:587`

## 2FA Authentication Alerts

### Features
- **Automatic Detection**: Triggered when iCloud session expires
- **Rate Limited**: Maximum one notification per service per 24 hours
- **Multi-Service**: Sent to all configured notification channels
- **Critical Priority**: Ensures immediate attention for authentication issues

### Configuration
2FA alerts are automatically enabled when any notification service is configured. No additional settings required.

### Message Content
```
🔐 iCloud Authentication Required

Your iCloud session has expired and requires 2FA authentication.

Please run the following command to re-authenticate:
docker exec -it icloud /bin/sh -c "su-exec abc icloud --username=your@email.com --session-directory=/config/session_data"

This notification will not be sent again for 24 hours.
```

## Sync Summary Notifications

### Features
- **Detailed Statistics**: Download counts, file sizes, sync duration
- **Smart Filtering**: Configurable thresholds to reduce noise
- **Flexible Triggers**: Send on success, errors, or both
- **Storage Insights**: Hardlink savings, space usage estimates
- **No Rate Limiting**: Sent for every qualifying sync cycle

### Configuration Options

```yaml
app:
  notifications:
    sync_summary:
      enabled: true           # Enable/disable sync summaries (default: false)
      on_success: true        # Send on successful syncs (default: true when enabled)
      on_error: true         # Send when errors occur (default: true when enabled)
      min_downloads: 5       # Minimum downloads to trigger notification (default: 1)
```

#### Configuration Details

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch for sync summary notifications |
| `on_success` | boolean | `true` | Send notifications for successful syncs |
| `on_error` | boolean | `true` | Send notifications when sync errors occur |
| `min_downloads` | integer | `1` | Minimum files downloaded to trigger notification |

### Message Content

#### Successful Sync Example
```
🔄 iCloud Sync Summary

📊 Statistics:
• Drive: 15 files downloaded, 2.3 GB
• Photos: 8 photos downloaded, 450 MB
• Total Duration: 3m 42s
• Hardlinks Created: 3 (saved 120 MB)

✅ Status: Completed successfully
⏰ Next sync: Drive in 4m 18s, Photos in 6m 58s
```

#### Sync with Errors Example
```
🔄 iCloud Sync Summary

📊 Statistics:
• Drive: 12 files downloaded, 1.8 GB
• Photos: 0 photos downloaded, 0 B
• Total Duration: 2m 15s
• Errors: 3 files failed to download

❌ Status: Completed with errors
⚠️ Check logs for detailed error information

⏰ Next sync: Drive in 4m 45s, Photos in 7m 25s
```

## Advanced Configuration

### Multiple Services Setup
```yaml
app:
  # Configure multiple services for redundancy
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "icloud-sync"
  telegram:
    bot_token: "1234567890:ABC..."
    chat_id: "123456789"
  pushover:
    user_key: "user-key"
    api_token: "app-token"
  smtp:
    email: "icloud@domain.com"
    to: "admin@domain.com"
    password: "app-password"
    host: "smtp.gmail.com"
    port: 587

  notifications:
    sync_summary:
      enabled: true
      on_success: true
      on_error: true
      min_downloads: 10  # Only notify for significant syncs
```

### Environment-Based Configuration

Use environment variables for sensitive data:
```yaml
app:
  telegram:
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  smtp:
    email: "${SMTP_EMAIL}"
    password: "${SMTP_PASSWORD}"
```

### Conditional Notifications

#### Development vs Production
```yaml
# Development - minimal notifications
app:
  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Skip success notifications
      on_error: true         # Only errors
      min_downloads: 100     # High threshold

# Production - comprehensive monitoring
app:
  notifications:
    sync_summary:
      enabled: true
      on_success: true       # All syncs
      on_error: true         # All errors
      min_downloads: 1       # Every download
```

## Troubleshooting

### Common Issues

#### Discord Webhook Not Working
- Verify webhook URL is complete and includes token
- Check webhook permissions in Discord server settings
- Test webhook with curl: `curl -X POST -H "Content-Type: application/json" -d '{"content":"test"}' YOUR_WEBHOOK_URL`

#### Telegram Messages Not Received
- Verify bot token format: `XXXXXXXXX:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
- Ensure chat_id is correct (positive for users, negative for groups)
- Check that bot has permission to message the chat
- Use @userinfobot to verify your chat ID

#### Email/SMTP Issues
- For Gmail: Use app passwords, not regular password
- Check port settings: 587 (TLS), 465 (SSL), 25 (plain)
- Some providers require "less secure apps" or specific settings
- Test SMTP settings with tools like `telnet` or online SMTP testers

#### Pushover Not Delivering
- Verify user key and API token are 30 characters each
- Check Pushover app settings on your device
- Ensure your Pushover subscription is active

### Testing Configuration

#### Dry Run Mode
Use dry run to test notifications without sending:
```bash
# This will test notification configuration without actually sending
docker exec -it icloud /bin/sh -c "su-exec abc python src/main.py --dry-run"
```

#### Manual Testing
Test individual notification services:
```python
# In Python console within container
from src import notify, read_config
config = read_config()

# Test Discord
notify._send_discord_no_throttle(config, "Test message", dry_run=False)

# Test Telegram
notify._send_telegram_no_throttle(config, "Test message", dry_run=False)
```

### Log Analysis

Monitor notification activity in logs:
```bash
# Follow live logs
docker logs -f icloud

# Search for notification events
docker logs icloud 2>&1 | grep -i "notification\|2fa\|sync summary"

# Check for errors
docker logs icloud 2>&1 | grep -i "error\|failed"
```

### Performance Impact

#### Notification Overhead
- **2FA Alerts**: Minimal impact due to 24-hour throttling
- **Sync Summaries**: Low impact, sent after sync completion
- **Multiple Services**: Parallel processing minimizes delays
- **Network Issues**: Won't block sync operations

#### Optimization Tips
- Use `min_downloads` to reduce notification frequency
- Disable `on_success` for very frequent syncs
- Configure only needed notification services
- Monitor log levels to avoid verbose notification logging

## Security Considerations

### Sensitive Information
- **Webhook URLs**: Treat as passwords, do not share publicly
- **Bot Tokens**: Keep private, can be regenerated if compromised
- **Email Passwords**: Use app passwords when possible
- **API Keys**: Store in environment variables or secure configs

### Message Content
- Notifications include file counts and sizes, not filenames
- No personal data or iCloud credentials are transmitted
- Error messages are generic and don't expose system details
- Authentication messages are informational only

### Network Security
- All HTTPS/TLS connections are verified
- SMTP can use TLS encryption
- No credential storage in notification messages
- Rate limiting prevents notification spam

## Examples

### Home Lab Setup
```yaml
app:
  # Single Discord channel for all notifications
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "HomeServer-iCloud"

  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Too noisy for home use
      on_error: true         # Important to know about failures
      min_downloads: 10      # Only significant changes
```

### Business/Server Setup
```yaml
app:
  # Multiple notification channels for redundancy
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "Production-iCloud"
  email:
    email: "icloud-monitor@company.com"
    to: "sysadmin@company.com"
    # ... SMTP settings

  notifications:
    sync_summary:
      enabled: true
      on_success: true       # Monitor all activity
      on_error: true         # Critical for business continuity
      min_downloads: 1       # Track every change
```

### Mobile-Focused Setup
```yaml
app:
  # Pushover for instant mobile notifications
  pushover:
    user_key: "user-key"
    api_token: "app-token"

  # Telegram as backup
  telegram:
    bot_token: "bot-token"
    chat_id: "chat-id"

  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Reduce mobile notification noise
      on_error: true         # Always know about issues
      min_downloads: 25      # Only significant syncs
```

This comprehensive notification system ensures you stay informed about your iCloud sync operations while providing flexibility to customize alerts based on your specific needs and environment.