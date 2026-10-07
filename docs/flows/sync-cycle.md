# Sync Cycle Flow

This document describes the end-to-end sync cycle executed by the main loop.

## Overview

The sync cycle is the core operational loop that alternates between Drive and Photos sync based on adaptive countdown timers.

## Steps

1. **Config reload** (`_load_configuration()`)
   - Read YAML config from `ENV_CONFIG_FILE_PATH` or default path
   - Config is reloaded EVERY iteration — values can change at runtime

2. **Sync interval extraction** (`_extract_sync_intervals()`)
   - Read `drive.sync_interval` and `photos.sync_interval` from config
   - Default: 1800 seconds (30 minutes)

3. **Force-sync check** (`web_signals.consume_force_sync()`)
   - Check for sentinel files from web UI "Sync now" button
   - Zero the countdown timer if force-sync requested

4. **Authentication** (`_authenticate_and_get_api()`)
   - Retrieve password from env or keyring
   - Create iCloudPy service instance
   - If 2FA required: handle and retry

5. **Cycle-start webhook** (`notify.send_cycle_event(boundary="start")`)
   - GET `app.webhooks.start` and POST `sync_started` to `app.webhooks.url`,
     whichever is configured — signed in, about to sync
   - Skipped in dry-run mode: the dry run returns before this point. A dry
     run whose SIGN-IN fails does report, through the retry handlers below,
     exactly as the other notification channels already do

6. **Drive sync** (`_perform_drive_sync()`)
   - Check mount marker (if configured)
   - Walk local destination, count files before sync
   - Call `sync_drive.sync_drive()` to download new files
   - Calculate stats (downloaded, skipped, removed, bytes)
   - Reset drive countdown timer

7. **Photos sync** (`_perform_photos_sync()`)
   - Check mount marker (if configured)
   - Walk local destination, count files before sync
   - Call `sync_photos.sync_photos()` to download new photos
   - Calculate stats (downloaded, skipped, hardlinked, bytes)
   - Reset photos countdown timer

8. **Cycle-end webhook** (`notify.send_cycle_event(boundary="success"|"failure")`)
   - The `success` ping and `sync_succeeded`, or `failure` and `sync_failed`
     with `reason: download_errors`, when the cycle's stats carry any error --
     a monitor that went green here would stay green while downloads kept
     failing. Only `PhotoStats.errors` is ever populated in production, so a
     failed Drive download does not reach this point
   - Also `failure` when the cycle synced nothing at all: every due service
     skipped by the mount marker, or no service configured
     (`_cycle_nothing_synced_reason()`, which names which). One service
     merely not being due is the ordinary unequal-interval case and still
     reports `success`
   - The POSTed event carries the full statistics, so a webhook-only install
     needs no `app.notifications.sync_summary`
   - The retry handlers (2FA required, missing keyring password, refused
     sign-in, post-sign-in service error) report `failure` instead, once per
     retry with a `data.reason`, since the cycle never reached its end

9. **Statistics recording** (`web_signals.record_sync_completion()`)
   - Persist per-service last-sync state for web dashboard

10. **Usage telemetry** (`_send_usage_statistics()`)
   - The only `alive()` invocation in the loop — runs after a successful sync
   - Carries the daily heartbeat + the sync-cycle statistics (install registration
     happens on the first successful sync; no telemetry in dry-run mode)

11. **Sync summary notification** (`notify.send_sync_summary()`)
    - Send notification if configured and thresholds met

12. **Schedule next sync** (`_calculate_next_sync_schedule()`)
    - Sleeps until the sooner service is due and subtracts that from both timers
    - A one-shot service (`sync_interval < 0`) that has already run is never scheduled again

13. **Interruptible sleep** (`_interruptible_sleep()`)
    - Sleep in 2-second chunks
    - Poll for force-sync sentinels between chunks

## Adaptive Scheduling Algorithm

```
if both services configured:
    sleep = min of the non-negative timers (a negative one is a finished one-shot)
    subtract sleep from both timers
    sync whichever timer reached zero (both, when they were equal)
else if only drive: sleep drive_timer, sync drive
else if only photos: sleep photos_timer, sync photos
```

## Oneshot Mode

When `sync_interval` is negative (e.g., `-1`), the system runs once and exits:
- `_should_exit_oneshot_mode()` checks if ALL configured intervals are negative
- Useful for cron-style scheduling from outside the container

## Cross-Cutting Concerns

- **Error handling:** Only a 2FA prompt ends the auth attempt with a wait —
  other sign-in failures (API errors, network faults) are caught and backed
  off with a 30-minute floor instead of exiting the process; a per-service
  outage after a successful sign-in is retried on the ordinary interval, never
  charged as a sign-in failure; an unreadable `config.yaml` makes the loop
  wait for the file rather than exit (dry-run reports and exits). Notification
  failures are swallowed
- **Performance:** Parallel downloads via ThreadPoolExecutor (auto or 1-16 threads)
- **Mount safety:** Marker file checks prevent writes to unmounted directories
- **Trust monitoring:** Cookie expiry warnings sent before 90-day trust window lapses;
  the token is proactively re-minted when fewer than `app.trust_refresh_days` remain

## Related Docs

- [Sync Engine](../systems/sync-engine.md)
- [Drive Sync](../systems/drive-sync.md)
- [Photos Sync](../systems/photos-sync.md)
- [Authentication](authentication.md)
