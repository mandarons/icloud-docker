# Photos Sync

The photos sync system (`src/sync_photos.py` + 6 helper modules) handles downloading photos from iCloud Photos to local storage.

## Responsibilities

- Enumerate photos from iCloud libraries (own + shared)
- Support album-based organization with `all_albums` mode
- Deduplicate across albums using hardlinks
- Filter by file extensions and album preferences
- Support multiple file sizes (original, medium, thumb, live_video)
- Handle date-based folder organization via `folder_format`
- Clean up obsolete local photos when enabled

## Module Map

| Module | Responsibility |
|--------|---------------|
| `sync_photos.py` | Entry point — `sync_photos()` orchestrates the process |
| `album_sync_orchestrator.py` | Album synchronization coordination |
| `photo_download_manager.py` | Parallel download task collection and execution |
| `photo_filter_utils.py` | Photo filtering by extensions and album preferences |
| `photo_path_utils.py` | Path normalization, folder format handling |
| `photo_file_utils.py` | File operations, metadata, 410 Gone retry |
| `photo_cleanup_utils.py` | Obsolete file removal |
| `hardlink_registry.py` | `HardlinkRegistry` class for deduplication |

## Boundaries

Photos sync is purely a download system. It writes to the local filesystem at the path configured in `photos.destination`.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `sync_photos(config, photos)` | Main entry — enumerate libraries, delegate to album sync |
| `sync_album_photos(...)` | Sync a single album's photos |
| `create_hardlink_registry(...)` | Create registry for cross-album dedup |

## File Size Variants

| Variant | Description |
|---------|-------------|
| `original` | Full-resolution image |
| `original_alt` | RAW fallback |
| `medium` | Medium-quality |
| `thumb` | Thumbnail |
| `live_video_original` | Live Photo video (full-res) |
| `live_video_medium` | Live Photo video (medium) |
| `live_video_thumb` | Live Photo video (thumb) |

## Invariants

- All file paths MUST be NFC-normalized with `unicodedata.normalize("NFC", path)`
- `use_hardlinks` mode requires `all_albums: true`
- `HardlinkRegistry` tracks hardlinks across albums to prevent duplicates
- `folder_format` uses strftime patterns (e.g., `"%Y/%m"`)
- `enumeration_chunk_size` bounds peak memory (default 1000 photos/chunk)
- HTTP 410 Gone triggers download URL refresh via `_refresh_photo_download_url()`

## Dependencies

- **Depends on:** `config_parser`, `filesystem_utils`, `icloudpy.services.photos`
- **Depended on by:** `sync.py`

## Tests

- `tests/test_sync_photos.py` — photos sync tests
- `tests/test_photo_cleanup_utils.py` — cleanup tests
- `tests/test_live_photo_extension.py` — live photo handling
- `tests/test_live_photo_pair_download.py` — live photo pairing
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync_photos.py`

## Related Docs

- [Sync Cycle Flow](../flows/sync-cycle.md)
- [Coding Standards](../standards/coding.md)
