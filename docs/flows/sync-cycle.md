# Sync Cycle Flow

This document describes the end-to-end sync cycle executed by the main loop.

## Overview

The sync cycle is the core operational loop that alternates between Drive and Photos sync based on adaptive countdown timers.

## Steps

1. **Config reload** (`_load_configuration()`)
   - Read YAML config from `ENV_CONFIG_FILE_PATH` or default path
   - Config is reloaded EVERY iteration — values can change at runtime

2. **Telemetry heartbeat** (`alive()`)
   - Send anonymized usage stats (skipped in dry-run mode)

3. **Sync interval extraction** (`_extract_sync_intervals()`)
   - Read `drive.sync_interval` and `photos.sync_interval` from config
   - Default: 1800 seconds (30 minutes)

4. **Force-sync check** (`web_signals.consume_force_sync()`)
   - Check for sentinel files from web UI "Sync now" button
   - Zero the countdown timer if force-sync requested

5. **Authentication** (`_authenticate_and_get_api()`)
   - Retrieve password from env or keyring
   - Create iCloudPy service instance
   - If 2FA required: handle and retry

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

8. **Statistics recording** (`web_signals.record_sync_completion()`)
   - Persist per-service last-sync state for web dashboard

9. **Usage telemetry** (`_send_usage_statistics()`)
   - Send anonymized sync summary data

10. **Sync summary notification** (`notify.send_sync_summary()`)
    - Send notification if configured and thresholds met

11. **Schedule next sync** (`_calculate_next_sync_schedule()`)
    - Adaptive algorithm determines which service syncs next
    - Subtracts elapsed time from other service's timer

12. **Interruptible sleep** (`_interruptible_sleep()`)
    - Sleep in 2-second chunks
    - Poll for force-sync sentinels between chunks

## Adaptive Scheduling Algorithm

```
if both services configured:
    if drive_timer <= photos_timer:
        if timers equal and > 10s: wait full interval, sync both
        else: sync drive, subtract drive_time from photos_timer
    else:
        sync photos, subtract photos_time from drive_timer
else if only drive: sync drive
else if only photos: sync photos
```

## Oneshot Mode

When `sync_interval` is negative (e.g., `-1`), the system runs once and exits:
- `_should_exit_oneshot_mode()` checks if ALL configured intervals are negative
- Useful for cron-style scheduling from outside the container

## Cross-Cutting Concerns

- **Error handling:** Auth failures trigger retry; notification failures are swallowed
- **Performance:** Parallel downloads via ThreadPoolExecutor (auto or 1-16 threads)
- **Mount safety:** Marker file checks prevent writes to unmounted directories
- **Trust monitoring:** Cookie expiry warnings sent before 90-day trust window lapses

## Related Docs

- [Sync Engine](../systems/sync-engine.md)
- [Drive Sync](../systems/drive-sync.md)
- [Photos Sync](../systems/photos-sync.md)
- [Authentication](authentication.md)
