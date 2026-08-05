# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [2.0.0] - 2026-08-05

### Added

- **Embedded Web UI** — optional dashboard showing sync status and on-device 2FA
  re-authentication (`app.web_ui.enabled`). Disabled by default; bind to
  `0.0.0.0` only behind a trusted reverse proxy.
- **`--dry-run` / `--check-files N`** CLI flags — verify credentials, mount
  paths, and config before running a real sync. `--check-files` walks N photos
  per library and reports `would_skip` / `size_mismatch` / `not_found` / `error`
  counts, useful for validating cross-tool migrations.
- **Per-library photo destinations** (`photos.library_destinations`) — route
  each iCloud photo library to its own subdirectory under `photos.destination`.
- **Mount marker failsafe** (`require_mount_marker`) — refuse to sync when
  bind-mounts fail silently, preventing writes into wrong directories.
- **Live Photo `.mov` auto-download** — `file_sizes` now supports
  `live_video_original`, `live_video_medium`, and `live_video_thumb` to
  optionally download the paired video for Live Photos.
- **Streaming album enumeration** (`enumeration_chunk_size`) — bounds peak
  memory for large (100K+) photo libraries by processing photos in fixed-size
  chunks.
- **Sync summary notifications** — optional per-cycle statistics via Discord,
  Telegram, Pushover, or email (`app.notifications.sync_summary`).
- **Trust expiry warnings** (`app.trust_expiry_warn_days`) — advance notice
  before Apple's ~90-day trust cookie expires.
- **CHANGELOG.md** — this file.

### Changed

- Bumped embedded web UI from initial release.
- Improved parallel download performance with configurable `max_threads`.

### Fixed

- Stale repository name references (`icloud-drive-docker` → `icloud-docker`)
  in USAGE.md and Unraid template.
- UGREEN NAS docker-compose YAML indentation bug in README.

## [1.x] - previous releases

See [GitHub Releases](https://github.com/mandarons/icloud-docker/releases) for
earlier version history.
