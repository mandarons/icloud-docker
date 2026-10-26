# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Edited photos can be downloaded: `photos.filters.file_sizes` accepts `full`
  — Apple's rendered edit (crop, filters, portrait, markup) — with `adjusted`
  as an accepted alias. The edit is usually HEIC (JPEG for older edits)
  whatever the original was, so its extension comes from the version's MIME
  type. `original_alt` (alias `alternative`) remains the RAW/JPEG pair
  alternate and is no longer described as an edit
  ([#292](https://github.com/mandarons/icloud-docker/issues/292),
  [#577](https://github.com/mandarons/icloud-docker/pull/577))
- `photos.filters.fallback_to_original` (default false): a photo that has no
  copy of a requested version is downloaded as its `original` instead of being
  skipped, so `file_sizes: [full]` means "the edit, or the original if the
  photo was never edited" — icloudpd's behaviour. `live_video_*` requests never
  fall back: a still image under a `.mov` name is not a video
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))

### Changed

- `photos.preserve_originals_as_bak` now hides the untouched original when the
  photo has an **edit** (`full`) and both `original` and `full` are requested.
  It previously keyed off `original_alt`, which is the RAW/JPEG pair alternate,
  not an edit: for RAW shooters it hid the untouched JPEG as
  `*.original.bak` without writing any edit at all
  ([#572](https://github.com/mandarons/icloud-docker/issues/572),
  [#577](https://github.com/mandarons/icloud-docker/pull/577)). RAW/JPEG
  pairs no longer produce a `.bak`; existing `*.original.bak` copies are
  untracked and are only swept when the asset leaves iCloud, so remove them by
  hand if they are no longer wanted
- On an edited photo, `medium`, `thumb` and the Live Photo `live_video_*`
  renditions now come from the `CPLAsset` record and therefore describe the
  edit. Their filenames do not change, so `check_photo_exists` sees a size
  mismatch and the first sync after the upgrade re-downloads them in place
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- Naming: in `simple` mode the edit gets a `-adjusted` marker when it would
  otherwise resolve to the same name as the original
  (`IMG_1234-adjusted.heic` when both are HEIC, `IMG_1234-adjusted.jpeg` when
  both are JPEG, and `.JPG` counts as the same container as `.jpeg`); when a
  HEIC original and a JPEG edit already differ, no marker is added. With
  `photos.file_format`, `full` counts as a variant while `original` is
  requested in the same run, so a template cannot put both on one path
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- `icloudpy` 0.12.0: `PhotoAsset.versions` reads each version from the
  `CPLAsset` record first and falls back to `CPLMaster`, which is what makes
  the edit visible. The release raises its Python floor to 3.14, which the
  container and CI already run. `file_sizes` entries are de-duplicated after
  alias normalization, so `[original, adjusted, full]` downloads the edit once
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- The image is built on Python 3.14 (`python:3.14-alpine3.24`, both stages),
  matching CI and the devcontainer. Python 3.10 reached end of life on
  2026-10-01, and its floor was also holding back dependency updates behind
  their newer `Requires-Python`. The Ruff target moves to `py314`, pre-commit
  hooks and the Allure CLI were refreshed (the hook's ruff now matches the
  pinned one instead of running a second version), and two redundant test pins
  were dropped: `coverage`, already supplied by `pytest-cov`, and `ipython`,
  which nothing imported
  ([#573](https://github.com/mandarons/icloud-docker/pull/573))

### Fixed

- Expired download URLs (HTTP 410) on edited photos: the refresh now re-fetches
  the `CPLAsset` record as well as `CPLMaster`. The edit's URL
  (`resJPEGFull*`) lives on the asset record, whose `recordName` differs from
  the master's, so refreshing only the master retried with the same stale URL
  and reported the photo as a failed download
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- `full` is no longer mistaken for an edit when only the `CPLMaster` record
  carries `resJPEGFullRes`: that is Apple's display rendition for a format it
  does not render natively (PNG screenshots, RAW, GIF, some MP4), and those
  photos were never edited. Previously such a photo's real original could be
  hidden as `*.original.bak` while a lossy JPEG render took its place, and
  `[adjusted]` without fallback downloaded that render. A `full` counts only
  when `resJPEGFullRes` / `resVidFullRes` is on the `CPLAsset` record
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- `fallback_to_original` no longer downloads `original` more than once per
  photo: with two requested sizes a photo lacks (e.g.
  `[adjusted, alternative]`), both used to resolve to the same path, racing two
  downloads onto one file in `metadata` mode and keeping a duplicate copy per
  photo in `simple` mode
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))
- A file already sitting at its final path is no longer reported as renamed.
  With `filename_format: simple` and no `folder_format`, the flat legacy path
  *is* the file's current path, so every existing file logged `Renaming X over
  existing X` on every run although nothing moved; the rename is now skipped
  when both paths are the same
  ([#574](https://github.com/mandarons/icloud-docker/issues/574),
  [#575](https://github.com/mandarons/icloud-docker/pull/575))
- An edited video's extension now comes from the video MIME type
  (`com.apple.quicktime-movie`, `public.mpeg-4`). Previously `full` looked only
  in the image mapping, logged "Unknown filetype" and kept the original's
  extension, writing an edited AVI or 3GP as QuickTime under the old name
  ([#577](https://github.com/mandarons/icloud-docker/pull/577))

## [2.2.0] 2026-10-19

### Added

- Unattended sync without a stored Apple ID password: with no `ENV_ICLOUD_PASSWORD`
  and an empty keyring the container now resumes the saved session in
  `/config/session_data` instead of logging "Password is not stored in keyring"
  and retrying forever without ever trying the valid session. Session-only
  sign-in stops after validating the session and never falls through to a
  credential sign-in, so no placeholder password is posted to Apple on every
  retry; the dashboard reads the saved session when the keyring is empty, says
  which way a session stopped, and serves Refresh trust from the session alone
  ([#557](https://github.com/mandarons/icloud-docker/pull/557),
  [#524](https://github.com/mandarons/icloud-docker/issues/524))
- JSON webhook for every notification and sync event — `app.webhooks.url`
  receives the notifications the app already sends plus `sync_started`,
  `sync_succeeded`, `sync_failed` (always carrying a `reason`) and
  `trust_refreshed`, as a JSON POST of `{event, message, timestamp, data}`, with
  an optional `events` allow-list and extra request `headers`. It shares the
  other transports' 24-hour throttle, except `sync_failed`, which is never
  throttled for receivers that track state rather than read notices
  ([#556](https://github.com/mandarons/icloud-docker/pull/556))
- Monitoring pings — `app.webhooks.start`, `success` and `failure` are bare GET
  URLs shaped for Healthchecks.io and similar monitors, which notice a sync
  that stopped happening by a ping that never arrives. `success` requires at
  least one service to have actually synced, so an unmounted volume or an
  empty configuration cannot keep a monitor green
  ([#556](https://github.com/mandarons/icloud-docker/pull/556),
  [#398](https://github.com/mandarons/icloud-docker/issues/398))
- Optional recycle bin — `app.recycle_bin.enabled` moves what Drive and Photos
  cleanup would delete to `<root>/Recently Deleted/<service>/<YYYY-MM-DD>/`,
  at the path the file had under the destination, instead of unlinking it;
  `app.recycle_bin.retention_days` bounds how long day folders are kept (omit
  to keep everything). Off by default, and it changes how cleanup removes
  things, never what `remove_obsolete`, the delete limit and the failed-library
  exclusions allow
  ([#559](https://github.com/mandarons/icloud-docker/pull/559))
- Dashboard controls for a stored password: it says whether one is on disk
  (and that on a headless host the keyring is a plain-text file), offers
  **Remove stored password** (`POST /auth/forget-password`) after checking the
  saved session signs in without it, and is not offered while
  `ENV_ICLOUD_PASSWORD` would write the password back on the next cycle. A
  dashboard sign-in with a different password than the stored one flags the
  stored copy as out of date; nothing is removed or overwritten unasked
  ([#565](https://github.com/mandarons/icloud-docker/pull/565))

### Changed

- A `sync_interval` of `0` is now treated as unset: it is logged as an invalid
  value — a positive number of seconds, or negative for one-shot — and the
  default interval is used instead. A service configured with 0 was otherwise
  due on every pass, so the scheduler slept 0 and synced it back to back, the
  fastest way to get throttled by Apple
  ([#555](https://github.com/mandarons/icloud-docker/pull/555))
- A library Apple is still indexing no longer stops Photos. icloudpy 0.11.0
  opens such a library with `photos_require_finished_index=False`, so what
  Apple already lists is downloaded, a warning names the library each cycle,
  and the rest of Photos carries on. Until its `indexing_state` reads
  `FINISHED` the listing may be incomplete, so the library is kept out of
  obsolete-file cleanup exactly like one that failed — with a single shared
  destination nothing is cleaned while any library indexes. Anything but an
  explicit `FINISHED`, a missing state included, counts as unfinished, and if
  the state cannot be checked, every library is kept out of cleanup for that
  cycle. The dashboard's library row says "Apple is still indexing this
  library · downloading, cleanup paused". The old wait for indexing, its
  30-minute retry, its dashboard note and the `photos_indexing` webhook reason
  are removed, since icloudpy no longer raises the error that started them
  ([#568](https://github.com/mandarons/icloud-docker/pull/568))
- Webhook `sync_failed` reasons now separate the fault. `sign_in_failed` is
  reserved for Apple refusing the sign-in itself — a network fault or an Apple
  service error before sign-in completes is `sign_in_error` — and a
  session-only sign-in the alert flags as needing a human is reported the same
  way by the alert and the webhook
  ([#556](https://github.com/mandarons/icloud-docker/pull/556),
  [#557](https://github.com/mandarons/icloud-docker/pull/557))
- `icloudpy` 0.11.0, which adds the `photos_require_finished_index` opt-out the
  Photos change above needs
  ([#568](https://github.com/mandarons/icloud-docker/pull/568))
- Dependency bumps (test tooling only): ruff 0.17.0, allure-pytest 2.16.2.
  `.ruff.toml` now pins `target-version = "py310"` and declares the codebase's
  `import datetime` convention: 0.17 assumes Python 3.11 when no target is
  set, which suggests `datetime.UTC` (absent on the 3.10 runtime) and would
  have restyled 19 files
  ([#567](https://github.com/mandarons/icloud-docker/pull/567),
  [#561](https://github.com/mandarons/icloud-docker/pull/561))

### Fixed

- Packages and their contents are no longer renamed to the NFD form of their
  whole path. On Linux NFC and NFD are different names, so a non-ASCII parent
  folder made the rename fail and the download report a failure, a non-ASCII
  package name moved the package away from the NFC path the next sync checks,
  and any real rename of a child moved the package's mtime off iCloud's — each
  re-downloading the package on every sync. A package now keeps the path it
  was asked for and its contents are recorded exactly as they are on disk; a
  leftover NFD copy left by an earlier version is reported when the package is
  downloaded and is removed by `drive.remove_obsolete` (off by default)
  ([#554](https://github.com/mandarons/icloud-docker/pull/554),
  [#527](https://github.com/mandarons/icloud-docker/issues/527))
- A blank `ENV_ICLOUD_PASSWORD` — what Compose substitutes for an unset
  `${VAR}` — now counts as no password: it no longer skips session-only mode,
  sends an empty password to Apple's sign-in on every retry, or overwrites a
  real keyring entry with `""`. An empty keyring entry likewise counts as no
  password
  ([#557](https://github.com/mandarons/icloud-docker/pull/557))
- The sync loop sleeps until the next service is due, not for the difference
  between the two countdowns. With Drive every hour and Photos every 12 hours
  it used to sync Drive at 0h, 11h, 21h, 30h … and not Photos until 67h;
  close intervals re-synced the faster service seconds after it finished
  (300/360 slept 60 seconds). The smaller countdown is now taken off both
  timers and whichever reaches zero is enabled
  ([#555](https://github.com/mandarons/icloud-docker/pull/555))
- A web sign-in no longer writes the Apple ID password to the keyring — the
  promise the `/auth` page used to break, and on a headless host that keyring
  is a plain-text file. The password, 2FA-code and security-key paths use the
  typed password for that sign-in only, and never overwrite a stored copy;
  the security-key page now asks for the password when none is stored, instead
  of requiring a stored one. Storing a password stays opt-in
  (`ENV_ICLOUD_PASSWORD` or answering yes at the `icloud` command's prompt),
  and passwords already stored are left alone
  ([#565](https://github.com/mandarons/icloud-docker/pull/565),
  [#558](https://github.com/mandarons/icloud-docker/issues/558))
- A library named in `filters.libraries` that Apple does not list — a Shared
  Library that was left, say — fails on its own instead of raising a
  `KeyError` that stopped Photos for every library each cycle. The others
  sync, it is kept out of obsolete-file cleanup, and the dashboard shows it
  failed with "Apple does not list this library"
  ([#568](https://github.com/mandarons/icloud-docker/pull/568))
- The dashboard's stored-password session check uses the region from
  `config.yaml`, so on a `region: china` install **Remove stored password** no
  longer always refuses
  ([#565](https://github.com/mandarons/icloud-docker/pull/565))
- Shared Library downloads no longer fail permanently with HTTP 410 on long
  walks: the pending-download buffer also drains once its oldest task is 10
  minutes old, so URLs valid ~30-40 minutes cannot expire before they are
  used, and the expired-URL refresh looks each asset up in the zone carried on
  its own master record instead of always the primary library's zone
  ([#560](https://github.com/mandarons/icloud-docker/pull/560))
- Binned files stay restorable by name and by library: a path removed twice in
  a day is now numbered before the extension (`IMG_1234 (2).HEIC`) so dropping
  the number restores the name iCloud knows, and with `library_destinations`
  each library's removals are filed under its own folder instead of collapsing
  two libraries' copies of the same path into anonymous numbered siblings
  ([#559](https://github.com/mandarons/icloud-docker/pull/559))
- The no-password log line reports the fault itself — session missing or
  session rejected — instead of the misleading "Password is not stored in
  keyring" it used to print alongside it
  ([#557](https://github.com/mandarons/icloud-docker/pull/557))

## [2.1.0] 2026-09-30

### Added

- Sign in with a hardware security key (WebAuthn). Apple IDs with a security key
  enrolled get no 6-digit codes; the web UI now relays Apple's challenge to the
  machine holding the key via a one-line `uv` command (`src/icloud_sign.py`),
  and the sync loop recognises such an account — no 2FA push, no Telegram
  listener, notifications point at `/auth`
  ([#547](https://github.com/mandarons/icloud-docker/pull/547))
- Complete iCloud 2FA from Telegram without a shell or web UI: set
  `app.telegram.listen: true`, reply the auth keyword to get a code pushed,
  then reply the 6-digit code ([#470](https://github.com/mandarons/icloud-docker/pull/470))
- `photos.filename_format: simple` — plain `IMG_1234.HEIC` names matching
  Apple/boredazfcuk style, so an existing boredazfcuk tree is recognised
  without re-downloading; collisions fall back to the metadata name
  ([#457](https://github.com/mandarons/icloud-docker/pull/457))
- `photos.file_format` — a single `${photo.*}` template applied to all
  versions, with `${photo.variant_suffix}` keeping originals un-suffixed
  ([#457](https://github.com/mandarons/icloud-docker/pull/457))
- `photos.preserve_originals_as_bak` — keep the untouched original of an
  edited photo as `*.original.bak` beside the visible edited version, hidden
  from photo browsers but recoverable (default off; needs `original_alt` in
  `file_sizes`) ([#458](https://github.com/mandarons/icloud-docker/pull/458))
- Per-library sync state on the web dashboard: "Syncing now", a relative
  last-sync time, or "Failed" with the last completion underneath; the
  dashboard lists only the libraries this container syncs
  ([#546](https://github.com/mandarons/icloud-docker/pull/546))
- Proactive trust-token refresh — `app.trust_refresh_days` (default 14,
  0 disables, must exceed `trust_expiry_warn_days`) re-mints Apple's ~90-day
  trust cookie on a schedule so a container restart months later resumes
  without a second factor ([#530](https://github.com/mandarons/icloud-docker/pull/530))
- Notifications name a *revoked* trust token distinctly from an expired one —
  Apple drops trust on security events where refresh can't help
  ([#530](https://github.com/mandarons/icloud-docker/pull/530))
- Obsolete-delete safety ceiling: `photos.obsolete_delete_limit_percent`
  (default 25, 0 disables) makes a cleanup run refuse and report instead of
  deleting when more than that share of a destination would go
  ([#535](https://github.com/mandarons/icloud-docker/pull/535))
- Log rotation — `app.logger.max_bytes` (default 50 MB) and
  `app.logger.backup_count` (default 3) bound the log file instead of letting
  it grow with library size; `max_bytes: 0` hands it to external logrotate
  ([#528](https://github.com/mandarons/icloud-docker/pull/528))
- Completing a re-auth in the web UI now ends the sign-in retry wait
  immediately instead of waiting out `retry_login_interval`
  ([#531](https://github.com/mandarons/icloud-docker/pull/531))
- A required 2FA re-auth now actually requests Apple's code push (best-effort,
  once per re-auth episode) — trusted devices stay silent otherwise
  ([#486](https://github.com/mandarons/icloud-docker/pull/486))
- Photo renames (Live Photo self-heal, legacy layout migration) are logged;
  one that replaces an existing file is logged as a warning
  ([#457](https://github.com/mandarons/icloud-docker/pull/457))

### Changed

- Sign-in failures other than a 2FA prompt no longer exit the container:
  API response errors and network faults back off (30-minute floor) instead of
  crash-looping under `restart: unless-stopped`; rate-limited accounts are not
  hammered ([#529](https://github.com/mandarons/icloud-docker/pull/529))
- A per-service outage (e.g. `Zone does not exist`) is logged as a service
  problem on the ordinary interval, not charged as a sign-in failure with the
  rate-limit backoff; after a genuine sign-in failure the retry waits at least
  the shortest configured sync interval ([#529](https://github.com/mandarons/icloud-docker/pull/529))
- An unreadable or missing `config.yaml` no longer becomes a restart loop: the
  loop waits for the file (dry-run reports and exits), and logging falls back
  to defaults instead of dying at import ([#529](https://github.com/mandarons/icloud-docker/pull/529))
- The dashboard reports `reauth_needed` — sync stopped, with a link to the auth
  page — instead of a healthy account while the loop is actually failing
  ([#531](https://github.com/mandarons/icloud-docker/pull/531))
- Download timeouts: `drive.request_timeout` now applies to the download
  stream itself (it previously only reached `is_package()`), and a new
  `photos.request_timeout` does the same for photos — both default 30s,
  between-bytes so large videos are unaffected; a stalled connection no longer
  freezes a sync forever while the container reports healthy
  ([#529](https://github.com/mandarons/icloud-docker/pull/529))
- The Telegram reply prompt is sent only by the 2FA handler — a rejected
  password or throttled sign-in no longer tells you to reply `auth`, which
  would hide the real error ([#470](https://github.com/mandarons/icloud-docker/pull/470))
- Updated icloudpy to 0.10.0 (security-key 2FA APIs) and requests to 2.34.2
- Usage-tracking HTTP contract documented (`docs/systems/usage.md`): schemas,
  samples, retry behaviour ([#511](https://github.com/mandarons/icloud-docker/pull/511))
- CI: Allure test reports generated with native runner steps (no Docker-based
  action); `.github/**` added to workflow path triggers
- Dependency bumps: ruff 0.16.9, coverage 7.16.2, allure-pytest 2.16.1,
  pre-commit 4.6.2, flask 3.1.3; GitHub Actions checkout v7, upload-artifact
  v7, docker/login-action v4, github-script v9

### Fixed

- Drive packages (`.key`, `.pxm`, `.band`, `.framework`, `.app`, …) are no longer
  re-downloaded on every sync. `package_exists()` compared the summed size of the
  *unpacked* directory against `item.size`, which is the size of the remote *zip* —
  never equal, so the up-to-date branch was unreachable
  ([#525](https://github.com/mandarons/icloud-docker/issues/525), [#526](https://github.com/mandarons/icloud-docker/pull/526))
- Flat single-file package bundles (unrecognised MIME, or `drive.flatten_packages`)
  are no longer re-downloaded every sync — their on-disk bytes are the archive
  size, which never equals `item.size`; freshness now falls back to the mtime
  `download_file` stamps ([#473](https://github.com/mandarons/icloud-docker/pull/473), [#550](https://github.com/mandarons/icloud-docker/pull/550))
- Package extraction is gated on `zipfile.is_zipfile()` rather than the libmagic MIME
  string, which reports `application/octet-stream` for many of Apple's packageDownload
  zips. Previously those packages were never unpacked and the raw zip was left on disk
  under the package's own name ([#525](https://github.com/mandarons/icloud-docker/issues/525))
- Two sibling iWork packages (bare-rooted internal zips) no longer collide with
  `FileExistsError` — bare-rooted archives extract into their own bundle
  subdirectory; self-prefixed ones (`.band`) keep the historical in-parent
  extraction ([#473](https://github.com/mandarons/icloud-docker/pull/473))
- Zip-slip: `_zip_entries_self_prefixed()` also recognises `../bundle/` traversal
  ([#473](https://github.com/mandarons/icloud-docker/pull/473))
- Expired download URL (HTTP 410) recovery now uses CloudKit `records/lookup` instead
  of `records/query`. `CPLMaster` is not a query-indexable type, so every refresh
  attempt failed with `Type is not marked indexable: CPLMaster (BAD_REQUEST)`, which
  could stop large albums syncing entirely ([#521](https://github.com/mandarons/icloud-docker/issues/521), [#522](https://github.com/mandarons/icloud-docker/pull/522))
- A CloudKit *error record* returned inside a 410 refresh response is rejected
  instead of being assigned as the photo's master record (surfaced later as
  `KeyError: 'fields'`, charged to the download so the refresh warning never
  fired) ([#522](https://github.com/mandarons/icloud-docker/pull/522))
- Photo downloads are verified before replacing anything: stream to a `.part`
  file, compare against the size iCloud declares, then move into place — a
  partial or wrong-body transfer can no longer sit where the photo belongs or
  destroy the previous good copy ([#545](https://github.com/mandarons/icloud-docker/pull/545))
- Filename-collision handling no longer orphans the file it preserves: the
  collided-with path is tracked so obsolete-cleanup leaves it alone (on a real
  library a single pass deleted 185,207 files this way) ([#457](https://github.com/mandarons/icloud-docker/pull/457))
- The Live Photo self-heal verifies the candidate is really the video (by
  CloudKit size) before renaming, and never renames the still onto its own
  path ([#457](https://github.com/mandarons/icloud-docker/pull/457))
- No legacy rename may start from the path the still legitimately occupies —
  under flat layouts syncing a `live_video_*` size could rename the still onto
  the video's path, losing both ([#457](https://github.com/mandarons/icloud-docker/pull/457))
- Obsolete-file cleanup never runs against the shared photos root: a library
  with no `library_destinations` entry could otherwise delete every other
  library's tree ([#534](https://github.com/mandarons/icloud-docker/pull/534))
- One unreadable library no longer stops the others: per-library faults are
  isolated, and failed libraries are excluded from obsolete cleanup (which
  would otherwise read their files as "server dropped these")
  ([#534](https://github.com/mandarons/icloud-docker/pull/534))
- Stalled downloads time out instead of blocking a worker forever while the
  container stays "healthy" (drive: observed 3-day freeze; photos: 4.5-hour
  freeze) ([#529](https://github.com/mandarons/icloud-docker/pull/529))
- The first-run auth form includes the CSRF token it needs
  ([#533](https://github.com/mandarons/icloud-docker/pull/533))
- A scalar `photos.filters.libraries: Family` (not a list) is treated as one
  library instead of iterating the string one library per character
  ([#546](https://github.com/mandarons/icloud-docker/pull/546))
- Container entry point hands ownership of `session_data/` and
  `python_keyring/` to the unprivileged user every start, so pre-existing
  root-owned directories can't cause `Permission denied`
  ([#549](https://github.com/mandarons/icloud-docker/pull/549))
- Broken star-history chart in the README ([#518](https://github.com/mandarons/icloud-docker/pull/518))

## [2.0.0] - 2026-08-07

### Added

- Per-library destination subdirectories (`photos.library_destinations`)
  ([#456](https://github.com/mandarons/icloud-docker/pull/456))
- Embedded web UI — sync dashboard + on-device 2FA re-auth flow
  ([#464](https://github.com/mandarons/icloud-docker/pull/464))

### Changed

- Comprehensive documentation overhaul ([#510](https://github.com/mandarons/icloud-docker/pull/510), [#498](https://github.com/mandarons/icloud-docker/pull/498))
- Dependency bumps: flask 3.1.3, ruff 0.16.1, coverage 7.15.3, pre-commit 4.6.1;
  GitHub Actions cache v6, setup-python v7, download-artifact v8,
  build-push-action v7 (pinned refs)

### Fixed

- Preserve the mount marker file during `remove_obsolete` cleanup
  ([#509](https://github.com/mandarons/icloud-docker/pull/509))

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

[Unreleased]: https://github.com/mandarons/icloud-docker/compare/v2.1.0...HEAD

[2.1.0]: https://github.com/mandarons/icloud-docker/compare/v2.0.0...v2.1.0

[2.0.0]: https://github.com/mandarons/icloud-docker/compare/v1.28.0...v2.0.0

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
