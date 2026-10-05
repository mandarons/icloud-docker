# Drive Sync

The drive sync system (`src/sync_drive.py` + 7 helper modules) handles downloading files from iCloud Drive to local storage.

## Responsibilities

- Walk iCloud Drive directory tree recursively
- Download files with parallel threads (ThreadPoolExecutor)
- Filter files/folders by glob patterns and extensions
- Detect and auto-extract ZIP packages and gzip streams (or keep them as
  single files when `drive.flatten_packages` is enabled)
- Remove obsolete local files when `remove_obsolete` is enabled — or, with
  `app.recycle_bin.enabled`, move them to `<root>/Recently Deleted/drive/<date>/`
- Handle file existence checks to avoid re-downloading
- Bound download streams with `drive.request_timeout` (default 30s) so a
  stalled connection cannot freeze a worker forever

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
- ZIP packages are auto-extracted when `zipfile.is_zipfile()` accepts them; `python-magic`
  is consulted only for the gzip branch. Do not gate ZIP handling on the libmagic MIME
  string — it reports `application/octet-stream` for many of Apple's packageDownload
  zips, and a failed unpack leaves the raw archive on disk under the package's name
- Package freshness is decided by `date_modified` **only**. `item.size` is the size of
  the remote zip while the local package is an unpacked directory, so the two are never
  comparable. For flat single-file bundles (unrecognised MIME or
  `drive.flatten_packages`) the on-disk size is the archive size, so freshness
  falls back to the mtime `download_file` stamps (`package_bundle_unchanged()`)
- A package and its contents keep the names they were extracted with (NFC, like
  every other Drive path) and are recorded as they are on disk. Nothing is renamed
  afterwards, so no mtime re-stamp is needed: `download_file` is the last writer of
  the package's mtime, and the `glob` that records its contents only reads
- Bare-rooted package zips (iWork-style entries) extract into their own bundle
  subdirectory; self-prefixed zips (`.band`-style) extract into the parent.
  `_zip_entries_self_prefixed()` must recognise `../bundle/` traversal too
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
