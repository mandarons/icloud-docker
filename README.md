# iCloud-docker

[![CI - Main](https://github.com/mandarons/icloud-docker/actions/workflows/ci-main-test-coverage-deploy.yml/badge.svg?branch=main)](https://github.com/mandarons/icloud-docker/actions/workflows/ci-main-test-coverage-deploy.yml)
[![Tests](https://mandarons.github.io/icloud-docker/badges/tests.svg)](https://mandarons.github.io/icloud-docker/test-results/)
[![Coverage](https://mandarons.github.io/icloud-docker/badges/coverage.svg)](https://mandarons.github.io/icloud-docker/test-coverage/index.html)
[![Latest](https://img.shields.io/github/v/release/mandarons/icloud-docker?color=blue&display_name=tag&label=latest&logo=docker&logoColor=white)](https://hub.docker.com/r/mandarons/icloud-drive)
[![Docker](https://badgen.net/docker/pulls/mandarons/icloud-drive)](https://hub.docker.com/r/mandarons/icloud-drive)
[![Discord][discord-badge]][discord]
[![GitHub Sponsors][github-sponsors-badge]][github-sponsors]
<a href="https://www.buymeacoffee.com/mandarons" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 30px !important;width: 150px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

🤟 **Please star this repository if you end up using this project. If it has improved your life in any way, consider donating to my mission using 'Sponsor' or 'Buy Me a Coffee' button. It will help me to continue supporting this product.** :pray:

iCloud-docker (previously known as iCloud-drive-docker) is a simple iCloud client in Docker environment. It uses [iCloudPy](https://github.com/mandarons/icloudpy) python library to interact with iCloud server.

> **For developers and AI agents:** This project uses [OpenCode](https://opencode.ai) with `AGENTS.md` for agent instructions. See [docs/index.md](docs/index.md) for architecture documentation and [AGENTS.md](AGENTS.md) for build/test commands.

Primary use case of iCloud-docker is to periodically sync wanted or all of your iCloud drive, photos using your iCloud username and password.

**_Please note that this application only downloads the files from server. It does not upload the local files to the server (yet)._**

## Installation

### Installation using Docker Hub

```
docker run --name icloud \
  -v ${PWD}/icloud:/icloud \
  -v ${PWD}/config:/config \
  -e ENV_CONFIG_FILE_PATH=/config/config.yaml \
  -p 8080:8080 \
  mandarons/icloud-drive
```

> The `-p 8080:8080` flag exposes the optional web UI. Remove it if you
> are not enabling `app.web_ui.enabled` in `config.yaml`.

### Installation using docker-compose

```yaml
services:
  icloud:
    image: mandarons/icloud-drive
    environment:
      - PUID=<insert the output of `id -u $user`>
      - PGID=<insert the output of `id -g $user`>
    env_file:
      - .env.icloud # Must contain ENV_CONFIG_FILE_PATH=/config/config.yaml and optionally, ENV_ICLOUD_PASSWORD=<password>
    container_name: icloud
    restart: unless-stopped
    ports:
      - "8080:8080" # Web UI — remove if not using app.web_ui.enabled
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ${PWD}/icloud:/icloud
      - ${PWD}/config:/config # Must contain config.yaml
```

### Authentication (required after container creation or authentication expiration)

```
# Login manually if ENV_ICLOUD_PASSWORD is not specified and/or 2FA is required
docker exec -it icloud /bin/sh -c "su-exec abc icloud --username=<icloud-username> --session-directory=/config/session_data"
```

For China server users, please add `--region=china` as follows:

```
# Login manually if ENV_ICLOUD_PASSWORD is not specified and/or 2FA is required
docker exec -it icloud /bin/sh -c "su-exec abc icloud --username=<icloud-username> --region=china --session-directory=/config/session_data"
```

Follow the steps to authenticate.

#### Two ways to run unattended

The container can keep syncing with or without an Apple ID password on disk. Both run unattended; they differ in what happens months later.

**Password stored** (`ENV_ICLOUD_PASSWORD`, or answering yes to `icloud`'s "Save password in keyring?" prompt) — indefinite unattended operation. When Apple's trusted session lapses the container signs in again by itself and only needs a human for the second factor. The cost is the credential at rest: on a headless host Python's `keyring` resolves to `keyrings.alt.file.PlaintextKeyring`, so the password sits in cleartext in `/config/python_keyring/keyring_pass.cfg`. That is an Apple ID password, which also reaches Find My, iCloud backups, purchases and account recovery.

**No password** — unattended until Apple's trust window closes, then a human signs in once. With no password configured the container resumes the saved session in `/config/session_data` and never attempts a credential sign-in. Nothing derived from your password is written to disk. When the session stops being accepted, sync stops with `No Apple ID password is stored and the saved session is no longer valid …`, sends the usual 2FA notification and waits `retry_login_interval` between attempts; set `app.trust_expiry_warn_days` so the warning arrives before that, not after. How often that happens is Apple's call, not a documented interval — `app.trust_refresh_days` rolls the window forward while the session is healthy, which should make it rare, though that refresh has not been verified against Apple over a full trust lifetime in this mode.

**Signing in again without storing a password.** Run the `docker exec … icloud …` command above and answer **no** to `Save password in keyring?`. The web dashboard works too: its "Refresh trust" button needs no password at all while the session is still alive, and a sign-in through `/auth` uses your password for that sign-in only and never saves it. The dashboard says when a password *is* stored, and its **Remove stored password** button deletes it once it has checked the saved session works without it.

**Switching an existing container to password-free.** Two things, because either one alone is not enough: remove `ENV_ICLOUD_PASSWORD` from the environment (it is copied into the keyring on every cycle it is set; an empty value counts as unset), *and* delete the keyring entry, with the dashboard's **Remove stored password** button or from the command line:

```
docker exec icloud su-exec abc python3 -c "import keyring; keyring.delete_password('icloudpy://icloud-password', '<icloud-username>')"
```

It prints a `PasswordDeleteError` if there was no entry to delete, which is how you confirm there wasn't one. `icloud --delete-from-keyring` also deletes it, but then continues into an interactive password prompt, so it needs `docker exec -it` and a Ctrl-C to get out of.

## Sample Configuration File

```yaml
app:
  logger:
    # level - debug, info (default), warning or error
    level: "info"
    # log filename icloud.log (default)
    filename: "/config/icloud.log"
    # Rotate the log file rather than letting it grow without bound (one line
    # is written per file considered each cycle, so a large library can reach
    # several GB). Defaults: 50 MB per file, 3 backups. Set max_bytes to 0 if
    # an external logrotate manages the file instead.
    # max_bytes: 52428800
    # backup_count: 3
  credentials:
    # iCloud drive username
    username: "please@replace.me"
    # Retry login interval - default is 10 minutes, specifying -1 will retry login only once and exit
    retry_login_interval: 600
  # Drive destination
  root: "/icloud"
  # Optional: refuse to sync if a marker file is missing in the destination.
  # Prevents writing into a wrong directory when bind-mounts fail silently.
  # mount_marker_filename: ".mounted"
  # Optional embedded web UI — see "Web UI" below. Disabled by default.
  # SECURITY: no built-in login; host 127.0.0.1 (default) keeps it
  # loopback-only. "0.0.0.0" publishes a password form to every
  # interface — put a trusted reverse proxy in front if you do that.
  # web_ui:
  #   enabled: false
  #   host: "127.0.0.1"
  #   port: 8080
  #   public_url: ""     # externally reachable URL, embedded in notifications
  # Warn this many days before Apple's ~90-day trust cookie expires (default 7)
  # trust_expiry_warn_days: 7
  # Re-mint the trust token when it has this many days left, so a container
  # restart months later resumes without a second factor. Must exceed
  # trust_expiry_warn_days. Set to 0 to disable. Default 14.
  # trust_refresh_days: 14
  discord:
  # webhook_url: <your server webhook URL here>
  # username: icloud-docker #or any other name you prefer
  telegram:
  # bot_token: <your Telegram bot token>
  # chat_id: <your Telegram user or chat ID>
  # listen: true         # also poll Telegram for replies so you can re-auth 2FA from your phone:
  #                      # reply the auth keyword to have a code pushed to your Apple devices,
  #                      # then reply the 6-digit code. Off by default. Requires bot_token + chat_id.
  #                      # Use a 1:1 chat with the bot (group privacy mode hides plain messages).
  # auth_keyword: auth   # reply word that triggers the 2FA push (default "auth", case-insensitive).
  pushover:
  # user_key: <your Pushover user key>
  # api_token: <your Pushover api token>
  smtp:
    ## If you want to receive email notifications about expired/missing 2FA credentials then uncomment
    # email: "user@test.com"
    ## optional, to email address. Default is sender email.
    # to: "receiver@test.com"
    # password:
    # host: "smtp.test.com"
    # port: 587
    # If your email provider doesn't handle TLS
    # no_tls: true
  # Webhooks (optional). Two independent things, either or both:
  #
  # start/success/failure are bare GET pings for a monitor such as
  # Healthchecks.io, which infers "the sync stopped running" from a ping it
  # expected and did not get -- something no outbound notification can tell
  # you. Set the check's period from your SHORTEST sync_interval and its
  # grace to cover your LONGEST sync.
  #
  # url receives every notification the app sends, plus the sync-cycle
  # events, as a JSON POST:
  #   {"event": ..., "message": ..., "timestamp": ..., "data": {...}}
  # for a receiver that acts on them (Home Assistant, n8n, ntfy behind a
  # proxy, your own endpoint). events filters it; omit for everything.
  # headers is for receivers behind an authenticating proxy.
  #
  # URLs and header values are credentials and this app never logs them (at
  # logger.level debug the HTTP library logs request paths, as it does for
  # your Telegram token).
  # webhooks:
  #   start: "https://hc-ping.com/<uuid>/start"
  #   success: "https://hc-ping.com/<uuid>"
  #   failure: "https://hc-ping.com/<uuid>/fail"
  #   url: "https://receiver.example.com/icloud"
  #   events:              # optional allow-list; omit to receive all of them
  #     - sync_failed
  #     - two_factor_required
  #   headers:             # optional, for an authenticating receiver
  #     Authorization: "Bearer <token>"
  region: global # For China server users, set this to - china (default: global)
  # Maximum number of parallel download threads for both drive and photos
  # auto: automatically set based on CPU cores (default, max 8)
  # integer: specific number of threads (max 16)
  # max_threads: auto
  # max_threads: 4
  notifications:
    # Sync summary notifications - sent after each sync cycle with statistics
    sync_summary:
      # Enable/disable sync summary notifications (default: false)
      enabled: false
      # Send notifications on successful syncs (default: true when enabled)
      on_success: true
      # Send notifications when errors occur during sync (default: true when enabled)
      on_error: true
      # Minimum number of downloads required to send notification (default: 1)
      # Set to 0 to always send notifications regardless of download count
      min_downloads: 1
drive:
  destination: "drive"
  # Remove local files that are not present on server (i.e. files delete on server)
  remove_obsolete: false
  sync_interval: 300
  # HTTP read timeout in seconds for the download stream (default: 30).
  # Prevents a stalled connection from freezing a sync forever.
  # request_timeout: 30
  # Keep packages (.key, .numbers, .app, …) as the downloaded single file
  # instead of extracting them — lower inode footprint on NAS, simpler dedup.
  # Default false (extract into a bundle directory).
  # flatten_packages: false
  # Optional: refuse to sync if a marker file is missing in the destination.
  # require_mount_marker: false
  filters: # Optional - use it only if you want to download specific folders.
    # File filters to be included in syncing iCloud drive content
    folders:
      - "folder1"
      - "folder2"
      - "folder3"
    file_extensions:
      # File extensions to be included
      - "pdf"
      - "png"
      - "jpg"
      - "jpeg"
  ignore:
    # When specifying folder paths, append it with /*
    - "node_modules/*"
    - "*.md"
photos:
  destination: "photos"
  # Remove local photos that are not present on server (i.e. photos delete on server)
  remove_obsolete: false
  # Optional, default 25. Ceiling on how much of a destination one cleanup run
  # may delete, as a percentage of the files found there. Above this share the
  # run reports what it would have removed and deletes nothing. 0 disables it.
  # obsolete_delete_limit_percent: 25
  # HTTP read timeout in seconds for photo downloads (default: 30). Between-bytes,
  # not a total budget, so large videos are unaffected.
  # request_timeout: 30
  # With file_sizes including both "original" and "original_alt", write edited
  # photos as the visible edited version plus the untouched original as
  # *.original.bak (hidden from photo browsers, filesystem-recoverable).
  # Default false.
  # preserve_originals_as_bak: false
  sync_interval: 500
  all_albums: false # Optional, default false. If true preserve album structure. If same photo is in multiple albums creates duplicates on filesystem
  use_hardlinks: false # Optional, default false. If true and all_albums is true, create hard links for duplicate photos instead of separate copies. Saves storage space.
  folder_format: "%Y/%m" # optional, if set put photos in subfolders according to format. Format cheatsheet - https://strftime.org
  # enumeration_chunk_size: 1000 # Optional, default 1000. Photos buffered per streaming chunk. Lower = lower peak memory on huge libraries, slightly more per-chunk overhead.
  # Optional: refuse to sync if a marker file is missing in the destination.
  # require_mount_marker: false
  filename_format: metadata # optional, default "metadata". "metadata" = name__filesize__base64id.ext (legacy). "simple" = plain name.ext (boredazfcuk/Apple-style; lets you migrate without re-downloading)
  # file_format: optional single template applied to ALL versions (overrides filename_format). Tokens:
  #   ${photo.filename} ${photo.ext} ${photo.id} ${photo.file_size} ${photo.year} ${photo.month} ${photo.day}
  #   ${photo.variant} (empty for original/full, else version) and ${photo.variant_suffix} (separator+variant, only when present).
  #   Example (keeps plain Apple/boredazfcuk names for originals, so existing files are not re-downloaded):
  #   file_format: "${photo.filename}${photo.variant_suffix}.${photo.ext}"
  # variant_separator: "_" # separator before the variant in ${photo.variant_suffix} (default "_")
  filters:
    # List of libraries to download. If omitted (default), photos from all libraries (own and shared) are downloaded. If included, photos only
    # from the listed libraries are downloaded.
    # libraries:
    #   - PrimarySync # Name of the own library

    # Per-library destination subdirectories (optional).
    # When set, photos from each library are written to
    # <photos.destination>/<subdirectory>/… instead of sharing one tree.
    # library_destinations:
    #   PrimarySync: personal
    #   SharedLibrary: shared

    # if all_albums is false - albums list is used as filter-in, if all_albums is true - albums list is used as filter-out
    # if albums list is empty and all_albums is false download all photos to "all" folder. if empty and all_albums is true download all folders
    albums:
      - "album 1"
      - "album2"
    file_sizes: # valid values are original, medium and/or thumb
      - "original"
      # - "medium"
      # - "thumb"
    # Live Photos: by default only the still image is downloaded.
    # To also download the paired .mov video file, add one of:
    #   live_video_original - full-resolution video (large)
    #   live_video_medium   - medium-quality video
    #   live_video_thumb    - thumbnail-quality video (smallest)
    # Non-Live Photos do not have these versions and are skipped.
    # - "live_video_original"
    extensions: # Optional, media extensions to be included in syncing iCloud Photos content
      # - jpg
      # - heic
      # - png
```

**_Note: On every sync, this client iterates all the files. Depending on number of files in your iCloud (drive + photos), syncing can take longer._**

## Dry Run and File Checking

Before running a full sync (especially for the first time or after migrating from another tool), you can use `--dry-run` to verify that everything is configured correctly without downloading any files:

```bash
docker exec icloud icloud --username=<username> --session-directory=/config/session_data --dry-run
```

This authenticates, summarises what *would* be synced (Drive + Photos destinations, library names), then exits.

### `--check-files N` (migration validation)

Use `--check-files N` with `--dry-run` to walk N photos per library and report whether existing on-disk files would be recognised instead of re-downloaded. This is especially useful when migrating from another iCloud backup tool (e.g. boredazfcuk/iCloud-Docker):

```bash
# Spot-check 100 photos per library
docker exec icloud icloud --username=<username> --session-directory=/config/session_data --dry-run --check-files 100

# Walk every photo (slow on large libraries)
docker exec icloud icloud --username=<username> --session-directory=/config/session_data --dry-run --check-files 0
```

The output reports per-library counts of: `would_skip` (already up-to-date), `size_mismatch`, `not_found`, and `error`. A high `would_skip` count means most files will not be re-downloaded during a real sync.

## Web UI

An optional embedded dashboard that shows sync status and lets you complete
2FA re-authentication from a browser — useful on a headless box where
`docker exec` isn't convenient. The dashboard tracks state per library —
"Syncing now", a relative last-sync time, or "Failed" with the last
completion underneath — and lists only the libraries this container
actually syncs. When the sync loop is failing it reports that (with a link
to the auth page) instead of a healthy account. Disabled by default;
enable with:

```yaml
app:
  web_ui:
    enabled: true
    host: "127.0.0.1"   # default — loopback only
    port: 8080
    public_url: "https://icloud.example.com"   # used in notification links
```

| key | default | meaning |
|---|---|---|
| `app.web_ui.enabled` | `false` | Master switch. When false nothing is served and no thread is started. |
| `app.web_ui.host` | `127.0.0.1` | Bind address. Loopback-only by default. |
| `app.web_ui.port` | `8080` | TCP port. |
| `app.web_ui.public_url` | *(unset)* | Externally reachable URL embedded in notifications, so the re-auth link works from your phone. Falls back to `http://host:port` with a one-time warning. |
| `app.trust_expiry_warn_days` | `7` | Warn this many days before Apple's ~90-day trust cookie expires, so re-auth can be scheduled rather than discovered mid-sync. |
| `app.trust_refresh_days` | `14` | Proactively re-mint the trust token when it has this many days left, so restarts keep resuming without a second factor. Must exceed `trust_expiry_warn_days`; `0` disables. |

### Security model — read before exposing it

The UI **has no authentication of its own** and accepts your Apple ID
password at `POST /auth/password`. The trust boundary is the network, so:

- **Default (`host: 127.0.0.1`)** — reachable only from inside the
  container. Safe.
- **`host: "0.0.0.0"`** — publishes a credential-accepting form over
  plaintext HTTP to every interface. Only do this behind a reverse proxy
  that supplies authentication and TLS (Cloudflare Access, Tailscale,
  Authelia, Traefik + forward-auth). The app trusts a single
  `X-Forwarded-*` hop for correct scheme/URL generation.

State-changing endpoints require a CSRF cookie plus a matching token, so
scripted callers must load a page first to obtain the cookie and echo the
token back in an `X-CSRF-Token` header.

### Sign in with a security key

Once security keys are enrolled on an Apple ID, Apple stops offering 6-digit codes entirely and answers with a WebAuthn challenge instead. Until now that left such an account unable to re-authenticate at all.

With the web UI enabled, open `/auth`. When Apple asks for a key, the page hands you one short command:

```sh
uv run https://raw.githubusercontent.com/mandarons/icloud-docker/v<version>/src/icloud_sign.py <challenge>
```

Run it on whichever machine has the key ([uv](https://docs.astral.sh/uv/) fetches its one dependency, `fido2`), touch the key, and paste the result back. The signer never sees your password and never contacts Apple. It prints what it is about to sign before asking for the touch, and returns the signature through the clipboard. The page links to the exact file first, and for a machine with no internet it also offers a self-contained version that carries the signer inline. Development builds, which have no release tag to point at, offer only that version.

**Why a command and not a button:** WebAuthn ties Apple's challenge to `apple.com`, so no browser will sign it on another site's behalf, and browsers block raw access to security keys for the same reason. That restriction is what protects the account from phishing. The alternative is the pattern Windows Remote Desktop and Citrix ship as [WebAuthn redirection](https://learn.microsoft.com/en-us/azure/virtual-desktop/redirection-configure-webauthn): the session that needs the assertion relays the challenge to the machine holding the key, and only the signed assertion travels back.

The sync loop recognises such an account on its own: it skips the 2FA push and the Telegram code listener (Apple sends no code), and its notifications point at `/auth` instead.

## Performance Optimization

### Parallel Downloads

This client supports parallel downloads to significantly improve sync performance, especially for users with large amounts of data. The parallel download feature uses multiple threads to download files simultaneously.

**Key Features:**
- **Automatic thread scaling**: By default, uses the number of CPU cores (up to 8 threads)
- **Configurable**: Set custom thread count or use "auto" via `max_threads` configuration
- **IO-optimized**: Designed for IO-heavy operations typical in file downloads
- **Thread-safe**: All file operations are protected with locks to ensure data integrity

**Configuration Options:**
- `max_threads: auto` - Automatic scaling based on CPU cores (default)
- `max_threads: 4` - Use 4 parallel download threads
- `max_threads: 1` - Disable parallel downloads (sequential mode)
- Omit the setting to use automatic scaling

**Performance Impact:**
- **Large file collections**: Can reduce sync time from hours to minutes
- **Small file collections**: Minimal impact due to overhead
- **Network-bound**: Most effective on fast internet connections
- **Disk-bound**: Benefits systems with fast storage (SSDs)

### Hard Link Deduplication

When using `all_albums: true`, photos that appear in multiple albums (such as "All Photos", "Videos", and custom albums) would normally be downloaded multiple times, consuming unnecessary storage space.

The `use_hardlinks` feature solves this by:

- **Storage Savings**: Creates hard links instead of duplicate files, potentially saving 50-75% of storage space
- **Smart Processing**: Syncs "All Photos" album first as the reference source
- **Automatic Fallback**: Falls back to normal download if hard link creation fails
- **Cross-Platform**: Works on filesystems that support hard links (Linux, macOS, Windows NTFS)

**Example Configuration:**
```yaml
photos:
  all_albums: true
  use_hardlinks: true  # Enable hard link deduplication
```

**Storage Impact Example:**
- **Without hard links**: Same photo in 3 albums = 3 separate files (3× storage usage)
- **With hard links**: Same photo in 3 albums = 1 file + 2 hard links (1× storage usage)

### Streaming Album Enumeration (Memory Optimization)

For users with large photo libraries (100K+ photos), the sync process can consume significant memory during album enumeration. The streaming enumeration feature bounds peak memory usage by processing photos in fixed-size chunks instead of loading the entire album into memory at once.

**How it works:**
- Photos are processed in chunks (default: 1000 photos per chunk)
- Each chunk is downloaded before the next chunk is loaded
- Peak memory usage is bounded by chunk size, not total album size

**Configuration:**
```yaml
photos:
  enumeration_chunk_size: 1000  # Default: 1000. Lower values reduce peak memory.
```

**Performance Impact:**
- **Large libraries (100K+ photos)**: Reduces peak memory from 4 GB+ to under 1 GB
- **Small libraries**: Minimal impact, slight overhead from chunk boundaries
- **Invalid values**: Non-positive or non-numeric values fall back to default (1000)

**When to adjust:**
- If your container has a low `mem_limit` (e.g., 2 GB), keep the default or lower it
- If you have ample memory and want slightly fewer chunk boundaries, increase it

## Notifications

iCloud-docker supports multiple notification channels to keep you informed about sync operations and authentication status.

### 2FA Authentication Alerts

Automatic notifications are sent when your iCloud authentication expires and 2FA is required:
- **Automatic Detection**: Triggered when iCloud session expires
- **Rate Limited**: Notifications are throttled to once per 24 hours per service to prevent spam
- **Multi-Channel**: Sent to all configured notification services simultaneously
- **Critical Priority**: Ensures you're promptly notified when manual authentication is needed

2FA alerts are automatically enabled when any notification service is configured. No additional settings required.

#### Re-authenticate over Telegram (headless 2FA)

If you run headless (no console, no web UI), you can complete 2FA straight from
Telegram. Set `app.telegram.bot_token` + `chat_id`, then enable `app.telegram.listen: true`.
When iCloud needs re-authentication the container messages your chat and waits:

1. Reply the **auth keyword** (default `auth`, set via `app.telegram.auth_keyword`).
   The container calls Apple to push a 2FA code to your trusted devices.
2. Reply the **6-digit code** Apple sent (spaces/dashes are tolerated, so `123 456`
   works). The container validates it and trusts the session, and sync resumes — no
   console or web UI needed.

Only messages from your configured `chat_id` are honoured. Other configured channels
(email, Discord, Pushover) still receive the standard 2FA alert.

**Notes:**
- **Multiple containers:** give each its own **bot token** (a `getUpdates` poll consumes
  updates for the whole bot, so containers sharing one token would steal each other's
  replies). A distinct `auth_keyword` per container is still useful for clarity.
- **Use a 1:1 chat with the bot.** In group chats, Telegram bot privacy mode hides plain
  `auth`/code messages from the bot.

### Sync Summary Notifications

Get detailed reports after each sync cycle with comprehensive statistics:

**Features:**
- **Detailed Statistics**: Download counts, file sizes, sync duration, and storage estimates
- **Smart Filtering**: Configurable thresholds to reduce noise
- **Flexible Triggers**: Send on success, errors, or both
- **Storage Insights**: Hardlink savings, space usage estimates
- **No Rate Limiting**: Unlike 2FA alerts, sync summaries are sent for every qualifying sync

**Configuration Options:**
```yaml
app:
  notifications:
    sync_summary:
      enabled: true           # Enable/disable sync summary notifications (default: false)
      on_success: true        # Send on successful syncs (default: true when enabled)
      on_error: true          # Send when errors occur (default: true when enabled)
      min_downloads: 5        # Minimum downloads to trigger notification (default: 1)
```

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `enabled` | boolean | `false` | Master switch for sync summary notifications |
| `on_success` | boolean | `true` | Send notifications for successful syncs |
| `on_error` | boolean | `true` | Send notifications when sync errors occur |
| `min_downloads` | integer | `1` | Minimum files downloaded to trigger notification |

**Example Notification Content:**
```
🔄 iCloud Sync Summary

📊 Statistics:
• Drive: 15 files downloaded, 2.3 GB
• Photos: 8 photos downloaded, 450 MB
• Total Duration: 3m 42s
• Hardlinks Created: 3 (saved 120 MB)

✅ Status: Completed successfully
⏰ Next sync: Drive in 4m 18s, Photos in 6m 58s
```

### Supported Notification Services

#### Discord

```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
    username: "icloud-sync"  # Optional: Custom bot name (default: icloud-docker)
```

**Setup Steps:**
1. Go to your Discord server settings
2. Navigate to Integrations → Webhooks
3. Create a new webhook or edit existing one
4. Copy the webhook URL
5. Optionally customize the username

#### Telegram

```yaml
app:
  telegram:
    bot_token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    chat_id: "123456789"  # Can be user ID or group chat ID
```

**Setup Steps:**
1. Message @BotFather on Telegram
2. Use `/newbot` command and follow instructions
3. Save the bot token provided
4. Add your bot to desired chat or use personal chat
5. Get your chat ID using @userinfobot or @RawDataBot

#### Pushover

```yaml
app:
  pushover:
    user_key: "your-30-char-user-key"
    api_token: "your-30-char-app-token"
    priority: "your-notification-priority"
```

**Setup Steps:**
1. Sign up at [Pushover.net](https://pushover.net)
2. Note your user key from the dashboard
3. Create a new application to get an API token
4. Install Pushover app on your mobile device

#### Email (SMTP)

```yaml
app:
  smtp:
    email: "icloud-sync@yourdomain.com"      # Sender address
    to: "admin@yourdomain.com"               # Recipient (optional, defaults to sender)
    username: "smtp-username"                # Optional: If different from email
    password: "your-app-password"            # App password or SMTP password
    host: "smtp.gmail.com"                   # SMTP server
    port: 587                                # SMTP port (587 for TLS, 465 for SSL, 25 for plain)
    no_tls: false                           # Set to true if TLS is not supported
```

**Popular SMTP Settings:**
- **Gmail**: `smtp.gmail.com:587` (requires app password)
- **Outlook**: `smtp-mail.outlook.com:587`
- **Yahoo**: `smtp.mail.yahoo.com:587`
- **AWS SES**: `email-smtp.region.amazonaws.com:587`

#### Webhooks

The other providers tell you what a sync did. None of them can tell you that a sync *stopped happening* — a container that dies, or a loop wedged on a sign-in Apple keeps refusing, simply goes quiet — and none of them can be acted on by a program. `app.webhooks` covers both gaps with two independent mechanisms; configure either or both.

**Monitoring pings (`start` / `success` / `failure`)** are bare GETs at the sync-cycle boundaries, for a monitor that alarms on the ping it did not get:

```yaml
app:
  webhooks:
    start: "https://hc-ping.com/<uuid>/start"     # a sync cycle is beginning
    success: "https://hc-ping.com/<uuid>"         # the cycle finished cleanly
    failure: "https://hc-ping.com/<uuid>/fail"    # the cycle failed, or finished with errors
```

Each URL is optional and independent — set only `failure` if that is all you want. The URLs above are the Healthchecks.io ping endpoints for one check, so the three together give you run duration, a failure alert, and an alert when the container stops pinging at all. Any service that accepts a GET works the same way (Uptime Kuma push monitors, Better Stack heartbeats, your own endpoint).

| Event | Fires when |
|-------|-----------|
| `start` | Sign-in succeeded and the cycle is about to sync |
| `success` | The cycle completed, no photo download failed, and at least one service actually synced |
| `failure` | A photo download failed; or the cycle synced nothing at all (every due service skipped for a missing mount marker, or no `drive:`/`photos:` section configured); or it never got that far — 2FA required, no password in the keyring, sign-in refused, or a service error after sign-in |

Note the asymmetry in the download-failure case: only Photos counts failed downloads into the sync statistics today, so a Drive file that fails to download does not by itself turn a cycle into a `failure`. A dry run that signs in sends nothing; one whose sign-in fails reports it like any other cycle, as the other notification channels already do.

**Setting the check's schedule.** The container pings once per sync cycle, and a cycle happens whenever either service's timer expires — so the expected period is your **shortest** `sync_interval`, plus however long that service takes to run. The grace should cover your **longest** sync comfortably, because a cycle that is busy downloading a large library sends nothing until it finishes. With `drive.sync_interval: 300` and `photos.sync_interval: 900`, a period of 5 minutes and a grace of an hour or two is a reasonable start; widen the grace rather than chase false alarms. Note that `failure` repeats on every retry while a sign-in problem persists (by design — the check should stay red), so expect a run of them rather than one.

A failed ping is logged at warning and otherwise ignored: the monitor's own grace period covers it, and nothing about a sync should depend on a monitoring service being up. A ping carries no body; the event endpoint below is what carries detail.

**An event endpoint (`url`)** receives every notification this app sends, plus the sync-cycle events, as a JSON POST — one place for a receiver that reacts rather than reads (Home Assistant, n8n, ntfy behind a proxy, a script of your own):

```yaml
app:
  webhooks:
    url: "https://receiver.example.com/icloud"
    events:                      # optional allow-list; omit to receive every event
      - sync_failed
      - two_factor_required
    headers:                     # optional, for a receiver behind an authenticating proxy
      Authorization: "Bearer <token>"
```

The payload shape is stable:

```json
{
  "event": "sync_succeeded",
  "message": "iCloud sync cycle completed",
  "timestamp": "2026-10-03T21:14:07.512431+00:00",
  "data": {
    "has_errors": false,
    "duration_seconds": 184.221,
    "drive": {"files_downloaded": 12, "files_skipped": 4310, "files_removed": 0, "bytes_downloaded": 48216104, "duration_seconds": 61.08, "errors": 0},
    "photos": {"photos_downloaded": 37, "photos_skipped": 51022, "photos_hardlinked": 4, "bytes_downloaded": 391048212, "bytes_saved_by_hardlinks": 10485760, "albums_synced": ["Recents"], "duration_seconds": 123.14, "errors": 0}
  }
}
```

`message` is the same human text the other transports send, so a receiver can forward it verbatim; `data` is the structured form for receivers that act on numbers. `timestamp` is ISO-8601 UTC. `data` is always present, possibly empty, and omits a key rather than sending `null` for it.

| Event | Fires when | `data` |
|-------|-----------|--------|
| `sync_started` | Sign-in succeeded and the cycle is about to sync | — |
| `sync_succeeded` | The cycle completed, no photo download failed, and a service actually synced | full sync statistics (as above) |
| `sync_failed` | A photo download failed; the cycle synced nothing; or it never got that far | statistics, plus a `reason` — always present: `download_errors`, `mount_marker_missing`, `photos_indexing`, `nothing_synced`, `two_factor_required`, `security_key_required`, `password_missing`, `sign_in_failed`, `sign_in_error`, `sync_error` |
| `sync_summary` | The sync-summary notification is sent (needs `app.notifications.sync_summary.enabled`, and respects its `min_downloads` / `on_success` / `on_error`) | full sync statistics |
| `two_factor_required` | iCloud wants a 6-digit code | `username`, `dashboard_url` |
| `security_key_required` | The account signs in with a hardware security key, so Apple will send no code at all | `username`, `dashboard_url` |
| `password_missing` | No password is stored and the saved session can't be resumed | `username`, `dashboard_url` |
| `sign_in_failed` | Apple rejected the sign-in itself — a wrong password, a throttle, or a 5xx during sign-in (`ICloudPyFailedLoginException` specifically, plus, when no password is stored, an Apple error that can't be told apart from a rejected session; a sign-in that never completed because of a network fault or an Apple service error is `sync_failed` with `reason: sign_in_error`, and a fault after a successful sign-in is `reason: sync_error`) | `username`, `dashboard_url` |
| `trust_expiring` | The ~90-day trust window is closing (once per cookie value) | `username`, `dashboard_url`, `days_remaining` |
| `trust_refreshed` | The trust token was proactively re-minted. Webhook-only: no other transport reports this | `expires_at`, `days_remaining_before` |

**Which events to key on.** The four alert events ride the same dispatch as Telegram and email, which means they inherit the **same 24-hour throttle**: treat them as throttled notices meant for a human, one per day at most. If you want to drive automation off the current state — an alarm that clears itself, a dashboard tile, a retry counter — key on `sync_failed` and its `data.reason` instead, which is sent on every cycle and every retry and therefore always reflects now. A dry run that signs in sends nothing; one whose sign-in fails reports it like any other cycle, as the other notification channels already do. `dashboard_url` appears only when the web UI is configured. The Apple ID appears in `data.username` because it is already in the message text every other transport sends.

Everything here is fire-and-forget: a 10-second timeout, no retries, every exception swallowed, and failures logged at warning. Nothing about a sync depends on a receiver being up. URLs and header values are credentials — anyone holding a ping URL can report your check healthy — and this app never logs either, not even on failure (a `requests` exception stringifies to the full URL, so only the exception type is logged). At `app.logger.level: debug` the HTTP library underneath (`urllib3`) logs request paths, which include a ping URL; that is already true of your Telegram bot token, so treat a debug-level log file as sensitive either way. Misspelled names in `events` are reported once at container start rather than silently matching nothing.

### Advanced Configuration

#### Multiple Services Setup

```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "icloud-sync"
  telegram:
    bot_token: "1234567890:ABC..."
    chat_id: "123456789"
  pushover:
    user_key: "user-key"
    api_token: "app-token"
    priority: 1
  smtp:
    email: "icloud@domain.com"
    to: "admin@domain.com"
    password: "app-password"
    host: "smtp.gmail.com"
    port: 587

  notifications:
    sync_summary:
      enabled: true
      on_success: true
      on_error: true
      min_downloads: 10  # Only notify for significant syncs
```

#### Recycle Bin

With `remove_obsolete: true`, files that are gone from iCloud are deleted from disk on the next sync. The recycle bin moves them aside instead:

```yaml
app:
  root: "/icloud"
  recycle_bin:
    enabled: true
    retention_days: 30   # optional; omit to keep everything forever
```

Removed files land in `<root>/Recently Deleted/drive/` or `<root>/Recently Deleted/photos/`, in a folder per day, at the same path they had under the destination (`Recently Deleted/photos/2026-10-04/2024/05/IMG_1234.HEIC`). With `library_destinations`, each library's folder comes first (`…/2026-10-04/personal/2024/05/IMG_1234.HEIC`). If the same file is removed twice in one day, the second copy is numbered before its extension (`IMG_1234 (2).HEIC`). To restore one, move it back and drop any number. Day folders older than `retention_days` are deleted at the start of each cleanup.

The bin never widens what cleanup removes: with `remove_obsolete: false` nothing is cleaned up and nothing reaches the bin, and `obsolete_delete_limit_percent` still applies.

#### Environment-Based Configuration

Use environment variables for sensitive data:
```yaml
app:
  telegram:
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
  smtp:
    email: "${SMTP_EMAIL}"
    password: "${SMTP_PASSWORD}"
```

#### Conditional Notifications

```yaml
# Development - minimal notifications
app:
  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Skip success notifications
      on_error: true         # Only errors
      min_downloads: 100     # High threshold

# Production - comprehensive monitoring
app:
  notifications:
    sync_summary:
      enabled: true
      on_success: true       # All syncs
      on_error: true         # All errors
      min_downloads: 1       # Every download
```

### Usage Examples

#### Home Lab Setup
```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "HomeServer-iCloud"

  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Too noisy for home use
      on_error: true         # Important to know about failures
      min_downloads: 10      # Only significant changes
```

#### Business/Server Setup
```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "Production-iCloud"
  smtp:
    email: "icloud-monitor@company.com"
    to: "sysadmin@company.com"
    # ... SMTP settings

  notifications:
    sync_summary:
      enabled: true
      on_success: true       # Monitor all activity
      on_error: true         # Critical for business continuity
      min_downloads: 1       # Track every change
```

#### Mobile-Focused Setup
```yaml
app:
  pushover:
    user_key: "user-key"
    api_token: "app-token"

  telegram:
    bot_token: "bot-token"
    chat_id: "chat-id"

  notifications:
    sync_summary:
      enabled: true
      on_success: false      # Reduce mobile notification noise
      on_error: true         # Always know about issues
      min_downloads: 25      # Only significant syncs
```

### Troubleshooting

#### Discord Webhook Not Working
- Verify webhook URL is complete and includes token
- Check webhook permissions in Discord server settings
- Test webhook with curl: `curl -X POST -H "Content-Type: application/json" -d '{"content":"test"}' YOUR_WEBHOOK_URL`

#### Telegram Messages Not Received
- Verify bot token format: `XXXXXXXXX:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`
- Ensure chat_id is correct (positive for users, negative for groups)
- Check that bot has permission to message the chat
- Use @userinfobot to verify your chat ID

#### Email/SMTP Issues
- For Gmail: Use app passwords, not regular password
- Check port settings: 587 (TLS), 465 (SSL), 25 (plain)
- Some providers require "less secure apps" or specific settings
- Test SMTP settings with tools like `telnet` or online SMTP testers

#### Pushover Not Delivering
- Verify user key and API token are 30 characters each
- Check Pushover app settings on your device
- Ensure your Pushover subscription is active

#### Manual Testing

Test individual notification services:
```python
# In Python console within container
from src import notify, read_config
config = read_config()

# Test Discord
notify._send_discord_no_throttle(config, "Test message", dry_run=False)

# Test Telegram
notify._send_telegram_no_throttle(config, "Test message", dry_run=False)
```

#### Log Analysis

Monitor notification activity in logs:
```bash
# Follow live logs
docker logs -f icloud

# Search for notification events
docker logs icloud 2>&1 | grep -i "notification\|2fa\|sync summary"

# Check for errors
docker logs icloud 2>&1 | grep -i "error\|failed"
```

### Security Considerations

#### Sensitive Information
- **Webhook URLs**: Treat as passwords, do not share publicly
- **Bot Tokens**: Keep private, can be regenerated if compromised
- **Email Passwords**: Use app passwords when possible
- **API Keys**: Store in environment variables or secure configs

#### Message Content
- Notifications include file counts and sizes, not filenames
- No personal data or iCloud credentials are transmitted
- Error messages are generic and don't expose system details
- Authentication messages are informational only

#### Network Security
- All HTTPS/TLS connections are verified
- SMTP can use TLS encryption
- No credential storage in notification messages
- Rate limiting prevents notification spam

### Performance Impact

- **2FA Alerts**: Minimal impact due to 24-hour throttling
- **Sync Summaries**: Low impact, sent after sync completion
- **Multiple Services**: Parallel processing minimizes delays
- **Network Issues**: Won't block sync operations

**Optimization Tips:**
- Use `min_downloads` to reduce notification frequency
- Disable `on_success` for very frequent syncs
- Configure only needed notification services
- Monitor log levels to avoid verbose notification logging

## Privacy and Usage Tracking

iCloud-docker collects anonymized usage statistics to help improve the project. This includes application version, sync statistics (file counts, sync duration), and general error indicators. **No personal data, file names, or iCloud credentials are collected.**

### Disable Usage Tracking

To completely opt out of usage tracking, add this to your `config.yaml`:

```yaml
app:
  usage_tracking:
    enabled: false
```

For more details about what data is collected and how it's used, see [USAGE.md](USAGE.md).

## Setup Guides

### UGREEN NAS Setup

This guide helps you set up iCloud sync on a UGREEN NAS system using Docker.

#### Prerequisites
- UGREEN NAS with Docker support
- Docker App installed on your UGREEN NAS
- iCloud account credentials

#### Step-by-Step Setup

1. **Create folder structure in your UGREEN userspace**

   Create the following directory structure in your UGREEN user directory:
   ```
    /Cloud-Drives/
    ├── Google-Drive
    ├── iCloud
    │   ├── Data
    │   └── Config
    │       └── config.yaml (see step 2)
    └── OneDrive
   ```

2. **Create config file**
   - Copy the sample configuration from this README
   - Make your adjustments to the `config.yaml`
   - Place it into the `Config` folder you created above

3. **Create Project in UGREEN Docker App**
   - Open the UGREEN Docker App
   - Name: `icloud-<icloud_username>` (replace `<icloud_username>` with your actual username)
   - Use the following Docker Compose configuration:

   ```yaml
   services:
     icloud-<icloud_username>:
       image: mandarons/icloud-drive
       environment:
         - PUID=<shown above the compose editor>
         - PGID=<shown above the compose editor>
         - ENV_CONFIG_FILE_PATH=/config/config.yaml
       container_name: icloud-<icloud_username>
       restart: unless-stopped
        volumes:
          - /etc/timezone:/etc/timezone:ro
          - /etc/localtime:/etc/localtime:ro
          - /home/<ugreen_username>/Cloud-Drives/iCloud/Data:/icloud
          - /home/<ugreen_username>/Cloud-Drives/iCloud/Config:/config
   ```

   Replace `<ugreen_username>` with your UGREEN system username.

4. **Build and start the container**
   - Save the Docker Compose configuration
   - Build and start the container using the Docker App

5. **Log into your Apple Account**
   - In the UGREEN Docker App, switch to "Containers"
   - Click on your container name `icloud-<icloud_username>`
   - Switch to the "Terminal" tab
   - Click on "Add"
   - Input the command `bin/sh`
   - Run the icloud command:
     ```bash
     su-exec abc icloud --username=<icloud_username> --session-directory=/config/session_data
     ```
   - Follow the authentication prompts to complete 2FA if required

6. **Restart the container**
   - Restart the container from the Docker App to ensure everything is working correctly

#### Multiple Account Setup

To set up multiple iCloud accounts, repeat these steps for each UGREEN user and Apple account combination. Each account should have its own separate folder structure and Docker container.

#### Notes
- This setup provides an iCloud backup solution on UGREEN NAS until official support is available in the UGREEN Cloud Drives App
- The same approach can be adapted for other cloud services like Google Drive and OneDrive
- Make sure to use unique container names for each iCloud account to avoid conflicts

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ENV_CONFIG_FILE_PATH` | `/config/config.yaml` | Path to the configuration file inside the container. |
| `ENV_ICLOUD_PASSWORD` | *(unset)* | iCloud password for automatic login. Stored in the container's keyring on first use. If unset (or empty) and the keyring is empty, the container runs off the saved session alone and needs a manual `docker exec` login once Apple stops accepting it — see [Two ways to run unattended](#two-ways-to-run-unattended). |
| `APP_VERSION` | `dev` | Application version, automatically set during Docker build. Used for usage tracking and displayed in the web UI. |
| `ICLOUD_DOCKER_CONFIG_DIR` | `/config` | Overrides the base config directory. Session data and keyring are stored relative to this path. The usage cache (`.data`) lives under the root destination (`app.root`). |
| `PUID` | *(unset)* | User ID for file ownership. |
| `PGID` | *(unset)* | Group ID for file ownership. |

## Usage Policy

As mentioned in [USAGE.md](https://github.com/mandarons/icloud-docker/blob/main/USAGE.md)

## Star History

<a href="https://star-history.dera.page/#mandarons/icloud-docker&Timeline">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://star-history.dera.page/svg?repos=mandarons/icloud-docker&type=Timeline&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://star-history.dera.page/svg?repos=mandarons/icloud-docker&type=Timeline" />
   <img alt="Star History Chart" src="https://star-history.dera.page/svg?repos=mandarons/icloud-docker&type=Timeline" />
 </picture>
</a>

[github-sponsors]: https://github.com/sponsors/mandarons
[github-sponsors-badge]: https://img.shields.io/github/sponsors/mandarons
[discord]: https://discord.gg/fyMGBvNW
[discord-badge]: https://img.shields.io/discord/871555550444408883
