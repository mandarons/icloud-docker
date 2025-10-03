# iCloud Docker - AI Coding Agent Instructions

## Project Overview
This is a containerized iCloud sync client that downloads files/photos from iCloud Drive and Photos to local filesystem. Built as a long-running Docker service using Alpine Linux with custom process management (no S6 overlay - uses `su-exec` and `docker-entrypoint.sh`).

## Architecture & Core Components

### Main Sync Loop (`src/sync.py`)
- **Single-threaded event loop** that alternates between Drive and Photos syncing based on configured intervals
- **Adaptive scheduling**: Dynamically calculates next sync time based on which service synced last and remaining countdown timers
  - Tracks `drive_time_remaining` and `photos_time_remaining` to determine which service should sync next
  - Subtracts elapsed time from other service's timer when one service syncs
- **Oneshot mode**: Set sync_interval to `-1` to run once and exit (useful for cron-style scheduling)
  - Exit condition: `sleep_for < 0` or all configured intervals are negative
- **2FA handling**: Retries authentication on `api.requires_2sa` with configurable `retry_login_interval`
- **Password management**: Uses `icloudpy.utils` keyring storage, falls back to `ENV_ICLOUD_PASSWORD` env var
  - Stores password from env var into keyring on first run for persistence

### Configuration System (`src/config_parser.py`)
- **YAML-based** with deep path traversal: `config_path = ["app", "credentials", "username"]`
- **Runtime config reloading**: Config is re-read on every sync loop iteration (enables hot config updates)
- **Environment overrides**: `ENV_CONFIG_FILE_PATH` and `ENV_ICLOUD_PASSWORD` override file values
- **Validation pattern**: ALWAYS use `traverse_config_path()` before `get_config_value()` to avoid KeyError
- **Defaults in code**: All `get_*()` functions provide sensible defaults (e.g., `DEFAULT_SYNC_INTERVAL_SEC = 1800`)
- **Thread configuration**: `max_threads` supports `"auto"` (caps at 8) or integer 1-16 (server protection cap)

### Sync Modules
- **`sync_drive.py`**: Handles folder filtering, file extension filters, and ignore patterns via glob matching
  - Uses `wanted_file()`, `wanted_folder()`, `wanted_parent_folder()` for hierarchical filtering
  - Auto-extracts ZIP files and handles gzip compression with `magic` library detection
  - Supports `remove_obsolete` to delete local files not on server
- **`sync_photos.py`**: Manages album/library filtering, file size variants, and photo metadata
  - File sizes: `original`, `original_alt` (RAW fallback), `medium`, `thumb`
  - Supports `all_albums` mode with optional `use_hardlinks` to deduplicate photos across albums
  - `folder_format` uses strftime patterns for date-based organization (e.g., `"%Y/%m"`)
  - Thread-safe `files_lock` protects shared file set during parallel downloads
- **Parallel downloads**: Both modules use `ThreadPoolExecutor` with configurable `max_threads` from config

### Notification System (`src/notify.py`)
- **Multi-provider**: Discord, Telegram, Pushover, SMTP with rate limiting (24-hour throttle)
- **2FA alerts**: Automatically notifies when authentication expires (`api.requires_2sa`)
- **Rate limiting**: `last_send` parameter prevents notification spam (returns same timestamp if < 24hrs)

## Development Workflow

### Local Testing
```bash
# Run full CI pipeline locally (includes ruff, pytest, allure report)
source .venv/bin/activate && ./run-ci.sh
# Manually: ruff check --fix && ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest
```

### Key Testing Patterns
- **Mock strategy**: Tests use `ICloudPyServiceMock` in `tests/data/photos_data.py` (2800+ lines of fixture data)
- **Config injection**: Tests override config paths via `tests.CONFIG_PATH` and `tests.TEMP_DIR`
- **100% coverage requirement**: `pytest.ini` enforces `--cov-fail-under=100` (build fails below 100%)
- **Temp directory cleanup**: All tests use `setUp()/tearDown()` pattern to clean `tests.TEMP_DIR`
- **Allure reporting**: CI generates test reports via `allure generate --clean`

### Docker Development
- **Base image**: `python:3.10-alpine3.22` (multi-stage build with builder pattern)
- **Service management**: Entry point is `/usr/local/bin/docker-entrypoint.sh` → calls `/app/init.sh` → runs `python src/main.py`
- **User management**: Creates `abc` user with configurable PUID/PGID (default 911:911)
- **Debug container**: `Dockerfile-debug` includes `debugpy` on port 5678 for remote debugging
- **Volume ownership**: Entrypoint sets ownership on `/app`, `/config`, `/icloud`, `/home/abc` if needed

### CI/CD Pipeline
- **Workflow**: `.github/workflows/ci-main-test-coverage-deploy.yml` runs on main branch
- **Steps**: Cache pip → Run tests → Generate coverage badges → Deploy to GitHub Pages
- **Triggers**: Changes to `src/**`, `tests/**`, `Dockerfile`, `pytest.ini`, `requirements*.txt`
- **PR checks**: `.github/workflows/ci-pr-test.yml` runs ruff + pytest on PRs

## Critical Implementation Details

### Authentication Flow
1. Check `ENV_ICLOUD_PASSWORD` environment variable first
2. If set, store in keyring via `utils.store_password_in_keyring()` for persistence
3. Otherwise, retrieve from keyring via `utils.get_password_from_keyring()`
4. On 2FA requirement (`api.requires_2sa`), enter retry loop with `retry_login_interval`
5. For China region, use different endpoints in `get_api_instance()`:
   - Home: `https://www.icloud.com.cn`
   - Setup: `https://setup.icloud.com.cn/setup/ws/1`

### File Handling Patterns
- **Path normalization**: All modules use `unicodedata.normalize("NFC", path)` for macOS/Windows compatibility
  - Also normalize to NFD when searching/comparing existing files
- **Atomic operations**: Files downloaded to temp paths, then moved to final location
- **Compression handling**:
  - `sync_drive.py` detects ZIP via `magic.from_file()` and auto-extracts
  - Handles gzip streams with `gzip.open()` for compressed downloads
- **Thread safety**: Use `files_lock` when modifying shared `files` set in parallel download workers

### Sync Interval Logic (src/sync.py lines 126-146)
```python
if "drive" not in config and "photos" in config:
    sleep_for = photos_time_remaining
elif "drive" in config and "photos" not in config:
    sleep_for = drive_time_remaining
elif drive_time_remaining <= photos_time_remaining:
    sleep_for = photos_time_remaining - drive_time_remaining
    photos_time_remaining -= drive_time_remaining  # Subtract elapsed from photos
    enable_sync_drive, enable_sync_photos = True, False
else:
    sleep_for = drive_time_remaining - photos_time_remaining
    drive_time_remaining -= photos_time_remaining  # Subtract elapsed from drive
    enable_sync_drive, enable_sync_photos = False, True
```

### Error Handling Strategy
- **Graceful degradation**: Missing config sections disable features rather than crash
  - Example: No `drive` section means skip drive sync entirely
- **Network errors**: iCloudPy has built-in retry logic for transient failures
- **Clean exits**: Oneshot mode uses `sleep_for < 0` to break main loop after single sync
- **2FA expiry**: Sends notifications and retries login based on `retry_login_interval` (-1 = exit immediately)

### Container Integration
- **User management**: Runs as `abc` user (PUID/PGID configurable via env vars)
- **Volume mounts**:
  - `/config` → config.yaml + session_data/
  - `/icloud` → synced content (drive/ and photos/)
  - `/home/abc/.local` → Optional keyring persistence
- **Session persistence**: Authentication tokens in `/config/session_data` (iCloudPy cookie directory)
- **Init sequence**: `docker-entrypoint.sh` → sets UID/GID → `su-exec abc /app/init.sh` → `python src/main.py`

## Code Conventions
- **Module structure**: Each `src/*.py` has corresponding `tests/test_*.py` mirror
- **Logging pattern**: Use `LOGGER = get_logger()` at module level (never instantiate inline)
- **iCloudPy logging**: Call `configure_icloudpy_logging()` immediately after imports to suppress verbose logs
- **Config access**: NEVER use direct dict access (`config["key"]`) - always use `config_parser.get_*()` functions
- **Error messages**: Include config path context: `config_path_to_string(config_path)` for debugging
- **Constants**: Define in `src/__init__.py` (e.g., `DEFAULT_COOKIE_DIRECTORY = "/config/session_data"`)

## External Dependencies
- **iCloudPy** (0.7.0): Core iCloud API client (`from icloudpy import ICloudPyService`)
- **ruamel.yaml** (0.18.15): YAML parsing with comment preservation
- **python-magic** (0.4.27): File type detection for drive sync (requires `libmagic` at runtime)
- **requests** (~2.32.3): HTTP client for notifications and usage tracking
- **Container tools**: `su-exec` (setuid alternative), `shadow` (user management)

## Common Pitfalls
- **Scheduler algorithm**: When modifying sync logic, ensure both drive and photos countdown timers are properly updated
- **Unicode normalization**: Always normalize file paths (NFC for storage, NFD for comparison)
- **Config validation**: Missing `traverse_config_path()` check will cause KeyError crashes
- **Thread limits**: Don't exceed 16 max_threads (server protection) - auto caps at min(CPU, 8)
- **Test coverage**: 100% required - new code MUST have corresponding test cases in `tests/`