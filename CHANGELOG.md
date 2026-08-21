# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Drive packages (`.key`, `.pxm`, `.band`, `.framework`, `.app`, …) are no longer
  re-downloaded on every sync. `package_exists()` compared the summed size of the
  *unpacked* directory against `item.size`, which is the size of the remote *zip* —
  never equal, so the up-to-date branch was unreachable
  ([#525](https://github.com/mandarons/icloud-docker/issues/525))
- Package extraction is gated on `zipfile.is_zipfile()` rather than the libmagic MIME
  string, which reports `application/octet-stream` for many of Apple's packageDownload
  zips. Previously those packages were never unpacked and the raw zip was left on disk
  under the package's own name ([#525](https://github.com/mandarons/icloud-docker/issues/525))

- Expired download URL (HTTP 410) recovery now uses CloudKit `records/lookup` instead
  of `records/query`. `CPLMaster` is not a query-indexable type, so every refresh
  attempt failed with `Type is not marked indexable: CPLMaster (BAD_REQUEST)`, which
  could stop large albums syncing entirely ([#521](https://github.com/mandarons/icloud-docker/issues/521))

### Changed

- Repeated consecutive download URL refresh failures are logged at WARNING rather than
  only DEBUG, so a systematically broken refresh path is visible by default

## [1.28.0] - 2026-07-27

### Added

- Optional `require_mount_marker` — refuse to sync without a failsafe marker file

### Changed

- Stream album enumeration in fixed-size chunks to bound peak RSS on large libraries

### Fixed

- Re-fetch master record on 410 instead of clearing cached versions

## [1.27.0] - 2026-07-22

### Added

- Live Photo .mov download via explicit `file_sizes` (`live_video_original`)
- `--dry-run` CLI flag (authenticate, summarize, exit without writing)

### Fixed

- Resolve keyring disconnect from PR #460 causing 'Password not stored in keyring'

## [1.26.0] - 2026-07-17

### Added

- Persist python-keyring at `/config/python_keyring` so it survives container recreate
- Update icloudpy version to 0.9.0 (fixes 2FA authentication prompt not appearing)

### Changed

- CI: green the suite on non-container dev hosts (macOS, sandboxes, etc.)

### Fixed

- Timezone-sensitivity bug causing full re-sync on `TZ` env var changes

## [1.25.0] - 2026-05-28

### Added

- Manual on-demand Docker image build workflow for PRs

### Changed

- Allow user to specify priority for Pushover notifications
- Skip `is_package()` network call for already-synced Drive files

### Fixed

- Make `is_package()` read timeout configurable, default 30s
- Fix `binascii.Error` crash when iCloud photo has invalid base64-encoded filename
- Handle HTTP 410 errors during photo downloads by refreshing expired URLs

## [1.24.0] - 2025-10-25

### Added

- Usage tracking system with opt-out mechanism (`app.usage_tracking.enabled: false`)
- Network resilience with retry logic and exponential backoff for usage tracking
- URL decoding using `urllib.parse.unquote()` for drive files, folders, and photos

### Changed

- Updated to iCloudPy version 0.8.0
- Refactored usage tracking module with 100% code coverage
- Enhanced error logging for file download operations
- Changed from local time to UTC for heartbeat throttling

### Fixed

- Fixed Error 500 for files with special characters (URL-encoded characters)
- Fixed immediate re-sync issue when drive and photos intervals are equal

## [1.23.0] - 2025-10-08

### Added

- Enhanced notifications with sync summaries and status updates

### Fixed

- `sync_interval` not being honored properly

## [1.22.0] - 2025-10-02

### Added

- Parallel downloads for faster sync
- Hard link deduplication for photos
- Simplified container architecture (dumb-init replaces s6-overlay)

### Changed

- UGREEN NAS setup guide
- Clarified `remove_obsolete` config option

### Fixed

- Fixed oneshot mode logic

## [1.21.0] - 2025-02-11

### Added

- Pushover notification support

## [1.20.2] - 2024-12-07

### Changed

- Load logger configuration from path defined in `ENV_CONFIG_FILE_PATH`

### Fixed

- China login failure
- Authentication failures (icloudpy version bump to 0.7.0)

## [1.20.1] - 2024-08-09

### Changed

- icloudpy upgraded to 0.6.0
- Unraid template updated to set `ENV_ICLOUD_PASSWORD` as optional

### Fixed

- Incorrect command in notification message
- Incorrect session directory creation
- Removed unused VOLUME and EXPOSE layers from Dockerfile
- Updated svc-icd type to oneshot to respect `*_interval < 0` in config.yaml
- `retry_login_interval < 0` for empty keyring

## [1.20.0] - 2024-06-25

### Added

- Support for `original_alt` version extensions
- Added username to notifications
- Added Unraid app template

### Changed

- **Breaking:** Container paths changed — `/app/icloud` → `/icloud`, `/app/config.yaml` → `/config/config.yaml`, `/app/session_data` → `/config/session_data`
- `ENV_CONFIG_FILE_PATH` environment variable is now required
- Documentation update
- Base image changed to lsio, now properly implements PGID and PUID

### Removed

- Support for `arm/v7` and `linux/386` due to incompatibility with base image

## [1.19.0] - 2024-05-15

### Added

- Support all photo sizes from icloudpy in photo filter

### Fixed

- Binary path + login doesn't persist

## [1.18.1] - 2024-05-14

### Fixed

- Download filtered album, if present, from all libraries when no library is specified
- Honors PUID (or 1000), PGID (or 1000) and UMASK (or 0022) environment variables

## [1.18.0] - 2024-02-26

### Added

- Allow `retry_login_interval` to set to -1 to retry login only once and exit
- Discord notifications

### Fixed

- Folder mentioned in the "ignore" section of config.yaml gets downloaded

## [1.17.0] - 2024-01-23

### Added

- Telegram notifications

## [1.16.1] - 2023-12-01

### Added

- Re-enabled arm/v7 build

### Fixed

- Fix for broken sync of packages

## [1.16.0] - 2023-11-02

### Added

- Support for `photos > folder_format` config option
- Support for shared library

### Changed

- Override config path via environment variable `ENV_CONFIG_FILE_PATH`
- icloudpy upgraded to 0.5.0

### Fixed

- Fix for `photos > download_all` should ignore filtered albums
- Fix downloading json files from drive

## [1.15.0] - 2023-10-05

### Added

- Normalized filenames for accent characters
- Option to preserve album structure

### Changed

- Upgraded icloudpy to 0.4.0

### Fixed

- Use actual To address from SMTP settings
- Error with unpacking packages

## [1.14.1] - 2023-08-27

### Fixed

- Fix for bug - photos without extension

## [1.14.0] - 2023-03-20

### Added

- Make use of `remove_obsolete` config option for iCloud Photos
- Add ignore option for iCloud Drive

### Changed

- Once a day heartbeat

## [1.13.0] - 2023-02-09

### Added

- Application usage tracking

### Changed

- icloudpy upgrade to 0.3.3

## [1.12.0] - 2023-01-20

### Added

- Support for username based email services

### Changed

- Handle errors raised by icloudpy and continue execution

## [1.11.0] - 2023-01-14

### Added

- Download photos from nested albums

## [1.10.0] - 2023-01-10

### Added

- Added photo quality and unique id to local photo names
- Photo extension filters in config

### Changed

- Make source code contributor friendly
- Infrastructure updates - pre-commit, dockerfile etc.

### Fixed

- Bugfix in Readme: `sync_inteval` -> `sync_interval`
- Preventing re-download of empty files

## [1.9.1] - 2022-07-24

### Added

- Packages are now extracted by default
- Support for iCloud China server `iCloud.com.cn` users

### Changed

- Added debug log messages for more information when file and photo is downloaded
- Corrected email body to have right docker exec command

### Fixed

- Unexpected re-downloading of packages has been fixed

## [1.9.0] - 2022-02-21

### Added

- Password as environment variable - `ENV_ICLOUD_PASSWORD`
- Persist session outside container
- Optional email in SMTP config

### Changed

- Default log level is now info
- Upgraded icloudpy to 0.3.0

## [1.8.1] - 2022-02-15

### Added

- Introduces wait before retrying login again
- Added `retry_login_interval` delay when retrying missing password

## [1.8.0] - 2022-02-14

### Added

- Logging to file and console
- Enabled separate `sync_interval` for photos and drive

### Changed

- Workflow updates for requirements.txt changes

### Fixed

- Number in folder name is not interpreted as string

## [1.7.1] - 2022-01-28

### Changed

- Don't download photos and drive unless explicitly specified in config.yaml
- Upgraded icloudpy to 0.2.1

### Fixed

- Bug of application failure if photo `file_size` is missing

## [1.7.0] - 2022-01-23

### Changed

- Replaced seemingly dead `pyiCloud` library with `icloudpy` library

## [1.6.0] - 2022-01-15

### Added

- iCloud Photos support

## [1.5.0] - 2021-08-12

### Added

- Support for ARM architecture (`linux/arm64` and `linux/arm/7`)

### Changed

- Heavily optimized docker images for size - going from 411.1 MB to 23.93 MB
- Moved CI/CD fully to GitHub Actions

## [1.4.0] - 2021-07-26

### Added

- Sync 'App Library' type

### Changed

- CI moved to GH Actions

## [1.3.0] - 2021-05-25

### Added

- When `filters` isn't specified in the config file, all of iCloud drive content is downloaded

## [1.2.0] - 2021-04-17

### Added

- Once in a day SMTP notification if credentials are expired/invalid

## [1.1.1] - 2021-04-09

### Fixed

- Fixed issue #11

## [1.1.0] - 2021-04-03

### Added

- file_extensions in config file is now optional - allows syncing of all the content recursively

### Fixed

- Fixed verbose mode not displaying all the information

## [1.0.0] - 2021-02-19

### Added

- Initial release

[Unreleased]: https://github.com/mandarons/icloud-docker/compare/v1.28.0...HEAD

[1.28.0]: https://github.com/mandarons/icloud-docker/compare/v1.27.0...v1.28.0
[1.27.0]: https://github.com/mandarons/icloud-docker/compare/v1.26.0...v1.27.0
[1.26.0]: https://github.com/mandarons/icloud-docker/compare/v1.25.0...v1.26.0
[1.25.0]: https://github.com/mandarons/icloud-docker/compare/v1.24.0...v1.25.0
[1.24.0]: https://github.com/mandarons/icloud-docker/compare/v1.23.0...v1.24.0
[1.23.0]: https://github.com/mandarons/icloud-docker/compare/v1.22.0...v1.23.0
[1.22.0]: https://github.com/mandarons/icloud-docker/compare/v1.21.0...v1.22.0
[1.21.0]: https://github.com/mandarons/icloud-docker/compare/v1.20.2...v1.21.0
[1.20.2]: https://github.com/mandarons/icloud-docker/compare/v1.20.1...v1.20.2
[1.20.1]: https://github.com/mandarons/icloud-docker/compare/v1.20.0...v1.20.1
[1.20.0]: https://github.com/mandarons/icloud-docker/compare/v1.19.0...v1.20.0
[1.19.0]: https://github.com/mandarons/icloud-docker/compare/v1.18.1...v1.19.0
[1.18.1]: https://github.com/mandarons/icloud-docker/compare/v1.18.0...v1.18.1
[1.18.0]: https://github.com/mandarons/icloud-docker/compare/v1.17.0...v1.18.0
[1.17.0]: https://github.com/mandarons/icloud-docker/compare/v1.16.1...v1.17.0
[1.16.1]: https://github.com/mandarons/icloud-docker/compare/v1.16.0...v1.16.1
[1.16.0]: https://github.com/mandarons/icloud-docker/compare/v1.15.0...v1.16.0
[1.15.0]: https://github.com/mandarons/icloud-docker/compare/v1.14.1...v1.15.0
[1.14.1]: https://github.com/mandarons/icloud-docker/compare/v1.14.0...v1.14.1
[1.14.0]: https://github.com/mandarons/icloud-docker/compare/v1.13.0...v1.14.0
[1.13.0]: https://github.com/mandarons/icloud-docker/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/mandarons/icloud-docker/compare/v1.11.0...v1.12.0
[1.11.0]: https://github.com/mandarons/icloud-docker/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/mandarons/icloud-docker/compare/v1.9.1...v1.10.0
[1.9.1]: https://github.com/mandarons/icloud-docker/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/mandarons/icloud-docker/compare/v1.8.1...v1.9.0
[1.8.1]: https://github.com/mandarons/icloud-docker/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/mandarons/icloud-docker/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/mandarons/icloud-docker/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/mandarons/icloud-docker/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/mandarons/icloud-docker/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/mandarons/icloud-docker/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/mandarons/icloud-docker/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/mandarons/icloud-docker/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/mandarons/icloud-docker/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/mandarons/icloud-docker/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/mandarons/icloud-docker/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mandarons/icloud-docker/releases/tag/v1.0.0