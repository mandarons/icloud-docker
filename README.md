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

Primary use case of iCloud-docker is to periodically sync wanted or all of your iCloud drive, photos using your iCloud username and password.

**_Please note that this application only downloads the files from server. It does not upload the local files to the server (yet)._**

## Installation

### Installation using Docker Hub

```
docker run --name icloud -v ${PWD}/icloud:/icloud -v ${PWD}/config:/config -e ENV_CONFIG_FILE_PATH=/config/config.yaml mandarons/icloud-drive
```

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
    volumes:
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
      - ${PWD}/icloud:/icloud
      - ${PWD}/config:/config # Must contain config.yaml
      - ${PWD}/keyring:/home/abc/.local # Optional: Persist keyring for credentials (no password re-entry on container recreation)
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

## Sample Configuration File

```yaml
app:
  logger:
    # level - debug, info (default), warning or error
    level: "info"
    # log filename icloud.log (default)
    filename: "/config/icloud.log"
  credentials:
    # iCloud drive username
    username: "please@replace.me"
    # Retry login interval - default is 10 minutes, specifying -1 will retry login only once and exit
    retry_login_interval: 600
  # Drive destination
  root: "/icloud"
  discord:
  # webhook_url: <your server webhook URL here>
  # username: icloud-docker #or any other name you prefer
  telegram:
  # bot_token: <your Telegram bot token>
  # chat_id: <your Telegram user or chat ID>
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
  sync_interval: 500
  all_albums: false # Optional, default false. If true preserve album structure. If same photo is in multiple albums creates duplicates on filesystem
  use_hardlinks: false # Optional, default false. If true and all_albums is true, create hard links for duplicate photos instead of separate copies. Saves storage space.
  folder_format: "%Y/%m" # optional, if set put photos in subfolders according to format. Format cheatsheet - https://strftime.org
  filters:
    # List of libraries to download. If omitted (default), photos from all libraries (own and shared) are downloaded. If included, photos only
    # from the listed libraries are downloaded.
    # libraries:
    #   - PrimarySync # Name of the own library

    # if all_albums is false - albums list is used as filter-in, if all_albums is true - albums list is used as filter-out
    # if albums list is empty and all_albums is false download all photos to "all" folder. if empty and all_albums is true download all folders
    albums:
      - "album 1"
      - "album2"
    file_sizes: # valid values are original, medium and/or thumb
      - "original"
      # - "medium"
      # - "thumb"
    extensions: # Optional, media extensions to be included in syncing iCloud Photos content
      # - jpg
      # - heic
      # - png
```

**_Note: On every sync, this client iterates all the files. Depending on number of files in your iCloud (drive + photos), syncing can take longer._**

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

## Notifications

iCloud-docker supports multiple notification channels to keep you informed about sync operations and authentication status.

### 2FA Authentication Alerts

Automatic notifications are sent when your iCloud authentication expires and 2FA is required:
- **Rate Limited**: Notifications are throttled to once per 24 hours per service to prevent spam
- **Multi-Channel**: Sent to all configured notification services simultaneously
- **Critical Priority**: Ensures you're promptly notified when manual authentication is needed

### Sync Summary Notifications

Get detailed reports after each sync cycle with comprehensive statistics:

**Features:**
- **Comprehensive Statistics**: Download counts, error summaries, sync duration, and storage estimates
- **Configurable Triggers**: Send on success, errors, or both
- **Smart Filtering**: Set minimum download thresholds to reduce noise
- **Multi-Service Support**: Works with Discord, Telegram, Pushover, and Email
- **No Rate Limiting**: Unlike 2FA alerts, sync summaries are sent for every qualifying sync

**Configuration Options:**
```yaml
app:
  notifications:
    sync_summary:
      enabled: true           # Enable sync summary notifications
      on_success: true        # Send on successful syncs (default: true)
      on_error: true         # Send when errors occur (default: true)
      min_downloads: 5       # Minimum downloads to trigger notification (default: 1)
```

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

**Discord**
- Uses webhook URLs for reliable delivery
- Supports rich formatting and emojis
- Ideal for server/team notifications

**Telegram**
- Requires bot token and chat ID
- Supports both private messages and group chats
- Excellent mobile notification support

**Pushover**
- Dedicated mobile notification service
- Supports priority levels and custom sounds
- Great for personal alerts

**Email (SMTP)**
- Supports TLS and non-TLS configurations
- UTF-8 support for international characters
- Automatic charset detection for rich content
- Configurable sender and recipient addresses

### Configuration Examples

**Multiple Services Setup:**
```yaml
app:
  discord:
    webhook_url: "https://discord.com/api/webhooks/..."
    username: "icloud-sync"
  telegram:
    bot_token: "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
    chat_id: "123456789"
  pushover:
    user_key: "your-user-key"
    api_token: "your-app-token"
  smtp:
    email: "icloud-sync@yourdomain.com"
    to: "admin@yourdomain.com"
    password: "your-app-password"
    host: "smtp.gmail.com"
    port: 587
```

**Notification Best Practices:**
- **Test Configuration**: Use a sync with few files to verify notifications work
- **Threshold Tuning**: Set `min_downloads` based on your typical sync patterns
- **Error Monitoring**: Keep `on_error: true` to catch sync issues early
- **Service Redundancy**: Configure multiple services for important notifications

For detailed notification setup instructions, troubleshooting, and advanced configuration examples, see [NOTIFICATION_CONFIG.md](NOTIFICATION_CONFIG.md).

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
   │   ├── Config
   │   │   └── config.yaml (see step 2)
   │   └── keyring
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
         - /home/<ugreen_username>/Cloud-Drives/iCloud/keyring:/home/abc/.local # Optional: Persist keyring for credentials (no password re-entry on container recreation)
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

## Usage Policy

As mentioned in [USAGE.md](https://github.com/mandarons/icloud-docker/blob/main/USAGE.md)

## Star History

<a href="https://star-history.com/#mandarons/icloud-docker&Timeline">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mandarons/icloud-docker&type=Timeline&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=mandarons/icloud-docker&type=Timeline" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=mandarons/icloud-docker&type=Timeline" />
 </picture>
</a>

[github-sponsors]: https://github.com/sponsors/mandarons
[github-sponsors-badge]: https://img.shields.io/github/sponsors/mandarons
[discord]: https://discord.gg/fyMGBvNW
[discord-badge]: https://img.shields.io/discord/871555550444408883
