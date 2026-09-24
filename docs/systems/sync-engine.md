# Sync Engine

The sync engine (`src/sync.py`) is the central orchestrator that manages the entire sync lifecycle.

## Responsibilities

- Authenticate with iCloud (keyring or env password)
- Manage adaptive countdown timers for Drive and Photos
- Handle 2FA requirements with retry logic
- Execute dry-run mode for pre-flight validation
- Coordinate notifications and usage telemetry
- Support oneshot mode (single sync then exit)

## Boundaries

The sync engine does NOT perform actual file downloads — it delegates to `sync_drive.py` and `sync_photos.py`. It handles scheduling, authentication, and high-level coordination only.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `sync()` | Main loop — called from `main.py` |
| `_authenticate_and_get_api()` | Create authenticated iCloudPy session |
| `_calculate_next_sync_schedule()` | Adaptive timer algorithm |
| `_handle_2fa_required()` | 2FA retry with notification |
| `_perform_drive_sync()` | Wrap drive sync with stats collection |
| `_perform_photos_sync()` | Wrap photos sync with stats collection |
| `_perform_dry_run()` | Validate config without writing files |

## Invariants

- Config is reloaded on EVERY loop iteration (`_load_configuration()`)
- `SyncState` class encapsulates countdown timers — never pass timers as bare parameters
- Oneshot mode exits when ALL configured intervals are negative
- Mount marker checks prevent writes to unmounted directories
- Trust cookie expiry warnings use debounce (one warning per cookie value)

## Dependencies

- **Depends on:** `config_parser`, `sync_drive`, `sync_photos`, `notify`, `usage`, `web_signals`
- **Depended on by:** `main.py` (entry point)

## Tests

- `tests/test_sync.py` — comprehensive sync loop tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync.py`

## Related Docs

- [Authentication Flow](../flows/authentication.md)
- [Sync Cycle Flow](../flows/sync-cycle.md)
- [Configuration](configuration.md)
