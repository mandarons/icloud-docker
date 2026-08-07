# Drive Sync

The drive sync system (`src/sync_drive.py` + 7 helper modules) handles downloading files from iCloud Drive to local storage.

## Responsibilities

- Walk iCloud Drive directory tree recursively
- Download files with parallel threads (ThreadPoolExecutor)
- Filter files/folders by glob patterns and extensions
- Detect and auto-extract ZIP packages and gzip streams
- Remove obsolete local files when `remove_obsolete` is enabled
- Handle file existence checks to avoid re-downloading

## Module Map

| Module | Responsibility |
|--------|---------------|
| `sync_drive.py` | Entry point — `sync_drive()` orchestrates the process |
| `drive_parallel_download.py` | ThreadPoolExecutor coordination, file collection |
| `drive_file_download.py` | Individual file download with atomic temp→final move |
| `drive_filtering.py` | Glob-based file/folder filtering |
| `drive_file_existence.py` | Check if file exists with correct size |
| `drive_cleanup.py` | Remove local files not on server |
| `drive_package_processing.py` | ZIP auto-extraction, gzip handling |
| `drive_folder_processing.py` | Directory traversal |
| `drive_sync_directory.py` | Directory sync orchestration |
| `drive_thread_config.py` | Thread count resolution (auto/int) |

## Boundaries

Drive sync is purely a download system — it does NOT upload files to iCloud. It writes to the local filesystem at the path configured in `drive.destination`.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `sync_drive(config, drive)` | Main entry — prepare destination, delegate to `sync_directory` |
| `sync_directory(...)` | Recursive directory walker with parallel download |
| `download_file(...)` | Atomic file download (temp path → final path) |
| `collect_file_for_download(...)` | Queue file for parallel download |
| `get_max_threads(config)` | Resolve thread count from config |

## Invariants

- All file paths MUST be NFC-normalized with `unicodedata.normalize("NFC", path)`
- Files are downloaded to temp paths, then moved atomically to final location
- ZIP packages are auto-extracted when detected via `python-magic`
- Thread count is capped at `min(CPU_COUNT, 8)`, max 16
- `files_lock` protects shared `files` set in parallel workers

## Dependencies

- **Depends on:** `config_parser`, `filesystem_utils`, `icloudpy.services.drive`
- **Depended on by:** `sync.py`

## Tests

- `tests/test_sync_drive.py` — drive sync tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync_drive.py`

## Related Docs

- [Sync Cycle Flow](../flows/sync-cycle.md)
- [Coding Standards](../standards/coding.md)
