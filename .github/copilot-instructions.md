# iCloud Docker - AI Coding Agent Instructions

## Project Overview
This is a containerized iCloud sync client that downloads files/photos from iCloud Drive and Photos to local filesystem. Built as a long-running Docker service using Alpine Linux with custom process management (no S6 overlay - uses `su-exec` and `docker-entrypoint.sh`).

## Architecture & Core Components

### Main Sync Loop (`src/sync.py`) - **RECENTLY REFACTORED**
- **Orchestrator pattern**: Main `sync()` function delegates to 15+ focused helper functions following SRP
- **State management**: `SyncState` class encapsulates countdown timers and sync flags to avoid parameter passing
- **Adaptive scheduling**: `_calculate_next_sync_schedule()` determines which service syncs next based on timers
  - Tracks `drive_time_remaining` and `photos_time_remaining` in state object
  - Subtracts elapsed time from other service's timer when one service syncs
- **Oneshot mode**: Set sync_interval to `-1` to run once and exit (useful for cron-style scheduling)
  - Exit condition: `_should_exit_oneshot_mode()` checks if ALL configured intervals are negative
- **2FA handling**: `_handle_2fa_required()` manages authentication retry with configurable intervals
- **Password management**: `_retrieve_password()` uses keyring storage, falls back to `ENV_ICLOUD_PASSWORD`
  - Stores password from env var into keyring on first run for persistence

### Configuration System - **HEAVILY REFACTORED**
- **Layered architecture**: Core utilities in `config_utils.py`, logging in `config_logging.py`, main API in `config_parser.py`
- **YAML-based** with deep path traversal: `traverse_config_path()` → `get_config_value()` pattern (NEVER direct dict access)
- **Runtime config reloading**: Config re-read on every sync loop iteration via `_load_configuration()`
- **Environment overrides**: `ENV_CONFIG_FILE_PATH` and `ENV_ICLOUD_PASSWORD` override file values
- **Validation pattern**: ALWAYS use `traverse_config_path()` before `get_config_value()` to avoid KeyError
- **Thread configuration**: `get_app_max_threads()` supports `"auto"` (caps at 8) or integer 1-16
- **Zero duplication**: Shared patterns extracted into helper functions (e.g., `get_sync_interval()`)

### Drive Sync Modules - **SPLIT INTO 8 SPECIALIZED MODULES**
- **`sync_drive.py`**: High-level orchestration and folder processing
- **`drive_parallel_download.py`**: Parallel download coordination with `ThreadPoolExecutor`
- **`drive_file_download.py`**: Individual file download and atomic operations
- **`drive_filtering.py`**: File/folder filtering logic via glob matching
- **`drive_file_existence.py`**: File existence checks and package detection
- **`drive_cleanup.py`**: Obsolete file removal when `remove_obsolete` enabled
- **`drive_package_processing.py`**: ZIP auto-extraction and gzip handling with `magic` library
- **`drive_folder_processing.py`**: Directory traversal and recursive processing

### Photos Sync Modules - **SPLIT INTO 7 SPECIALIZED MODULES**
- **`sync_photos.py`**: High-level orchestration (libraries vs albums)
- **`album_sync_orchestrator.py`**: Album synchronization coordination
- **`photo_download_manager.py`**: Parallel download task collection and execution
- **`photo_filter_utils.py`**: Photo filtering by extensions and album preferences
- **`photo_path_utils.py`**: Path normalization and folder format handling
- **`photo_file_utils.py`**: File operations and metadata handling
- **`hardlink_registry.py`**: `HardlinkRegistry` class for deduplication across albums
- **File sizes**: `original`, `original_alt` (RAW fallback), `medium`, `thumb`
- **Hardlink deduplication**: `use_hardlinks` mode with registry tracking across albums
- **Date organization**: `folder_format` uses strftime patterns (e.g., `"%Y/%m"`)

### Notification System (`src/notify.py`)
- **Multi-provider**: Discord, Telegram, Pushover, SMTP with rate limiting (24-hour throttle)
- **2FA alerts**: Automatically notifies when authentication expires (`api.requires_2sa`)
- **Rate limiting**: `last_send` parameter prevents notification spam (returns same timestamp if < 24hrs)

### Usage Tracking (`src/usage.py`)
- **Opt-in telemetry**: Collects anonymized sync statistics for usage analytics (see `USAGE.md`)
- **Opt-out**: Set `app.usage_tracking.enabled: false` in config to disable completely
- **Data collected**: Version, sync duration/counts, error indicators (no file names/paths/credentials)
- **Endpoints**: `NEW_INSTALLATION_ENDPOINT` and `NEW_HEARTBEAT_ENDPOINT` from Dockerfile build args

## Development Workflow

### Local Testing
```bash
# Run full CI pipeline locally (includes ruff, pytest, allure report)
source .venv/bin/activate && ./run-ci.sh
# Manually: ruff check --fix && ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest
```

### Key Testing Patterns
- **Mock strategy**: Tests use `ICloudPyServiceMock` in `tests/data/__init__.py` (4000+ lines) with photo fixtures in `tests/data/photos_data.py` (2800+ lines)
- **Config injection**: Tests override config paths via `tests.CONFIG_PATH` and `tests.TEMP_DIR`
- **100% coverage requirement**: `pytest.ini` enforces `--cov-fail-under=100` (build fails below 100%)
- **Temp directory cleanup**: All tests use `setUp()/tearDown()` pattern to clean `tests.TEMP_DIR`
- **Allure reporting**: CI generates test reports via `allure generate --clean`
- **Test structure**: Each `src/*.py` has mirror `tests/test_*.py` (e.g., `sync.py` → `test_sync.py`)

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
  - `drive_package_processing.py` detects ZIP via `magic.from_file()` and auto-extracts
  - Handles gzip streams with `gzip.open()` for compressed downloads
- **Thread safety**: Use `files_lock` when modifying shared `files` set in parallel download workers

### Refactoring Principles - **CRITICAL FOR NEW CODE**
- **Single Responsibility Principle**: Every function has ONE clear purpose - modules split from monoliths
- **No code duplication**: Extract common patterns into utilities (e.g., `config_utils.py`, `filesystem_utils.py`)
- **Separation of concerns**: Business logic, logging, and configuration parsing are separate
- **State management**: Use classes like `SyncState` and `HardlinkRegistry` instead of parameter passing
- **Layered architecture**: Core utilities → Business logic → Orchestration layers
- **Example refactor**: `sync.py` main loop uses 15+ focused helpers; drive/photos split into 8/7 modules respectively

### Error Handling Strategy
- **Graceful degradation**: Missing config sections disable features rather than crash
  - Example: No `drive` section means skip drive sync entirely
- **Network errors**: iCloudPy has built-in retry logic for transient failures
- **Clean exits**: Oneshot mode uses `_should_exit_oneshot_mode()` to break main loop after single sync
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
- **Type annotations**: All new functions must have comprehensive type hints and docstrings

## External Dependencies
- **iCloudPy** (0.7.0): Core iCloud API client (`from icloudpy import ICloudPyService`)
  - Runtime uses PyPI package, not the `external/icloudpy` git submodule
  - Submodule is included for reference/development purposes only
- **ruamel.yaml** (0.18.15): YAML parsing with comment preservation
- **python-magic** (0.4.27): File type detection for drive sync (requires `libmagic` at runtime)
- **requests** (~2.32.3): HTTP client for notifications and usage tracking
- **Container tools**: `su-exec` (setuid alternative), `shadow` (user management)

## Common Pitfalls
- **Refactoring violations**: Don't create monolithic functions - break into SRP-compliant helpers
- **Config validation**: Missing `traverse_config_path()` check will cause KeyError crashes
- **Thread limits**: Don't exceed 16 max_threads (server protection) - auto caps at min(CPU, 8)
- **Test coverage**: 100% required - new code MUST have corresponding test cases in `tests/`
- **Unicode normalization**: Always normalize file paths (NFC for storage, NFD for comparison)
- **State management**: Use classes for complex state instead of passing many parameters