# Glossary

Domain terminology, acronyms, and project-specific vocabulary.

| Term | Definition |
|------|-----------|
| **2FA** | Two-Factor Authentication — Apple's requirement for iCloud access. Also called 2SA (Two-Step Authentication) in iCloudPy. |
| **2SA** | Two-Step Authentication — Apple's older term for 2FA. Used interchangeably in code (`api.requires_2sa`). |
| **iCloudPy** | Python library for interacting with iCloud services. Used as the API client. |
| **Drive** | iCloud Drive — Apple's file storage service. Synced via `sync_drive.py`. |
| **Photos** | iCloud Photos — Apple's photo storage service. Synced via `sync_photos.py`. |
| **Oneshot mode** | Running a single sync cycle then exiting. Enabled by setting `sync_interval` to `-1`. |
| **Mount marker** | A sentinel file (e.g., `.mounted`) that must exist before sync proceeds. Prevents writes to unmounted directories. |
| **Trust cookie** | Apple's `X-APPLE-WEBAUTH-HSA-TRUST` cookie. ~90-day window before re-auth is required. |
| **Hardlink** | filesystem link pointing to the same inode. Used for photo deduplication across albums. |
| **HardlinkRegistry** | Class in `hardlink_registry.py` that tracks hardlinks across albums to prevent duplicates. |
| **SyncState** | Class encapsulating countdown timers and sync flags. Avoids parameter passing between functions. |
| **SyncSummary** | Data class holding per-cycle statistics (files downloaded, bytes, errors, duration). |
| **DriveStats** | Statistics for a single Drive sync cycle. |
| **PhotoStats** | Statistics for a single Photos sync cycle. |
| **web_signals** | Cross-thread communication via sentinel files. Connects web UI "Sync now" button to sync loop. |
| **PUID/PGID** | Process User ID / Process Group ID — Linux user mapping for file ownership in Docker. |
| **su-exec** | Setuid execution tool — drops privileges from root to `abc` user. Alternative to S6 overlay. |
| **keyring** | Python keyring library — stores iCloud password securely in `/config/python_keyring/`. |
| **session_data** | Directory containing iCloudPy authentication cookies. Persisted across container restarts. |
| **NFC/NFD** | Unicode normalization forms. NFC for storage, NFD for macOS/Windows file comparison. |
| **Atomic download** | Downloading to temp path, then moving to final location. Prevents partial files. |
| **folder_format** | strftime pattern for date-based photo organization (e.g., `"%Y/%m"`). |
| **enumeration_chunk_size** | Photos buffered per streaming chunk. Bounds peak memory on large libraries. |
| **all_albums** | Config flag to preserve album structure. When true, photos organized by album. |
| **remove_obsolete** | Config flag to delete local files not present on server. |
| **adaptive scheduling** | Algorithm that alternates Drive/Photos sync based on countdown timers. |
