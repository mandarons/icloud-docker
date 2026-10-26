# Photos Sync

The photos sync system (`src/sync_photos.py` + 6 helper modules) handles downloading photos from iCloud Photos to local storage.

## Responsibilities

- Enumerate photos from iCloud libraries (own + shared)
- Support album-based organization with `all_albums` mode
- Deduplicate across albums using hardlinks
- Filter by file extensions and album preferences
- Support multiple file sizes (original, full/adjusted, medium, thumb, live_video, original_alt)
- Handle date-based folder organization via `folder_format`
- Name files via `photos.filename_format` (metadata/simple) or a single
  `photos.file_format` template; optionally preserve originals of edited
  photos as `*.original.bak` (`photos.preserve_originals_as_bak`)
- Clean up obsolete local photos when enabled
- Bound download streams with `photos.request_timeout` (default 30s)

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
| `remove_obsolete_files(destination, tracked, ...)` | Delete local files absent from the run's tracked set; refuses above `obsolete_delete_limit_percent` |

## File Size Variants

| Variant | Description |
|---------|-------------|
| `original` | Full-resolution image, as uploaded |
| `full` (alias `adjusted`) | Apple's rendered **edit** (crop, filters, portrait, markup), `resJPEGFull*` on the `CPLAsset` record (`resVidFull*` for an edited video). Edited assets only; usually HEIC and JPEG for older edits, whatever the original was, and QuickTime/MPEG-4 for a video — the extension comes from the version's MIME type. A `full` that only the `CPLMaster` record carries is Apple's display render for a format it does not show natively (PNG, RAW, GIF, some MP4), not an edit, and is ignored |
| `original_alt` (alias `alternative`) | RAW/JPEG pair alternate (`resOriginalAltRes`) — **not** an edit |
| `medium` | Medium-quality; on an edited asset it describes the edit |
| `thumb` | Thumbnail; on an edited asset it describes the edit |
| `live_video_original` | Live Photo video (full-res) |
| `live_video_medium` | Live Photo video (medium) |
| `live_video_thumb` | Live Photo video (thumb) |

## Invariants

- All file paths MUST be NFC-normalized with `unicodedata.normalize("NFC", path)`
- `use_hardlinks` mode requires `all_albums: true`
- `HardlinkRegistry` tracks hardlinks across albums to prevent duplicates
- `folder_format` uses strftime patterns (e.g., `"%Y/%m"`)
- `enumeration_chunk_size` bounds peak memory (default 1000 photos/chunk). The download buffer also drains once its oldest task is `BUFFERED_DOWNLOAD_MAX_AGE_SEC` old (10 minutes, checked between photos, so best effort; the URL refresh covers what still expires), because download URLs expire ~30-40 minutes after the listing that returned them and, on a mostly backed-up library, pending downloads trickle in across the whole walk
- HTTP 410 Gone triggers download URL refresh via `_refresh_photo_download_url()`, which looks the records up in their own `zoneID` (from the master record), falling back to the service's zone. It looks up **both** the `CPLMaster` record and — when the asset record carries a rendition — the `CPLAsset` record: the edit's URL (`resJPEGFull*`) lives on the asset record, whose `recordName` differs from the master's. Refreshing only the master leaves an edited photo looping on 410. icloudpy gives every asset the photos service, whose zone is the primary library, so a Shared Library asset looked up there is never found
- `photos.filters.fallback_to_original` substitutes `original` when an asset has no copy of a requested size; `live_video_*` requests never fall back, because the still image's bytes under a `.mov` name are not a video
- Downloads stream to a `.part` file and are size-verified against the CloudKit
  version size before being moved into place — a partial or wrong-body transfer
  never occupies the photo's path and never destroys the previous good copy
- Photo renames (Live Photo self-heal, legacy migration) log what moved; a
  rename that replaces an existing file logs a warning, and no rename may
  start from the path the still legitimately occupies
- Failed libraries are isolated (one unreadable library does not stop the
  others) and are excluded from obsolete cleanup, which would otherwise read
  their files as "server dropped these"
- A library Apple is still indexing is opened anyway (`photos_require_finished_index=False`) and synced: Apple can report a library as indexing for weeks while listing it in full. Until its `indexing_state` reads `FINISHED` its listing may be incomplete, so it is kept out of obsolete-file cleanup exactly like a library that failed, and with a single shared destination nothing is cleaned while any library indexes. A warning names each such library every cycle
- URL refresh MUST use CloudKit `records/lookup`, not `records/query` — `CPLMaster`
  is not a query-indexable type and querying it always fails with
  `Type is not marked indexable: CPLMaster (BAD_REQUEST)`
- Repeated consecutive refresh failures escalate from DEBUG to WARNING, so a
  systematically broken refresh path is visible without debug logging
- Obsolete-file cleanup refuses to delete more than
  `obsolete_delete_limit_percent` of a destination in one run (default 25,
  0 disables). Cleanup infers deletions from absence in the run's
  tracked-file set, so a bug that leaves paths untracked reads as "the
  server dropped these"; above the limit the run reports and deletes nothing
- With `app.recycle_bin.enabled`, cleanup moves what it would delete to
  `<root>/Recently Deleted/photos/<date>/` (`src/recycle_bin.py`), under the
  library's folder when `library_destinations` is set (its name when the
  mapping points outside the destination), so two libraries' identical
  paths never collide. The bin decides only how, never what: the limit and the failed-library exclusions
  apply unchanged, and files already in the bin are neither cleaned up nor
  counted toward the limit

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
