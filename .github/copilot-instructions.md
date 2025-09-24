# iCloud Docker - AI Coding Agent Instructions

## Project Overview
This is a containerized iCloud sync client that downloads files/photos from iCloud Drive and Photos to local filesystem. Built as a long-running Docker service using Alpine Linux with S6 overlay for process management.

## Architecture & Core Components

### Main Sync Loop (`src/sync.py`)
- **Single-threaded event loop** that alternates between Drive and Photos syncing based on configured intervals
- **Adaptive scheduling**: Dynamically calculates next sync time based on which service synced last
- **2FA handling**: Retries authentication on `api.requires_2sa` with configurable intervals
- **Password management**: Uses `icloudpy.utils` keyring storage, falls back to `ENV_ICLOUD_PASSWORD` env var

### Configuration System (`src/config_parser.py`)
- **YAML-based** with deep path traversal: `config_path = ["app", "credentials", "username"]`
- **Runtime config reloading**: Config is re-read on every sync loop iteration
- **Environment overrides**: `ENV_CONFIG_FILE_PATH` and `ENV_ICLOUD_PASSWORD` override file values
- **Validation pattern**: Use `traverse_config_path()` before `get_config_value()` to avoid errors

### Sync Modules
- **`sync_drive.py`**: Handles folder filtering, file extension filters, and ignore patterns
- **`sync_photos.py`**: Manages album filtering, file size variants (original/medium/thumb), and photo metadata
- **Key pattern**: Both use `wanted_*()` functions for filtering logic before download

### Notification System (`src/notify.py`)
- **Multi-provider**: Discord, Telegram, Pushover, SMTP with rate limiting
- **2FA alerts**: Automatically notifies when authentication expires
- **Rate limiting**: `last_send` parameter prevents notification spam

## Development Workflow

### Local Testing
```bash
# Run full CI pipeline locally
./run-ci.sh
# Uses ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml
```

### Key Testing Patterns
- **Mock strategy**: Tests use `ICloudPyServiceMock` in `tests/data/photos_data.py`
- **Config injection**: Tests override config paths via `tests.CONFIG_PATH`
- **100% coverage requirement**: `pytest.ini` enforces `--cov-fail-under=100`
- **Temp directory cleanup**: All tests use `setUp()/tearDown()` pattern for `tests.TEMP_DIR`

### Docker Development
- **Base image**: `alpine:3.19` with dumb-init for process management
- **Service management**: Main app runs via custom `docker-entrypoint.sh` script
- **Debug container**: Use `Dockerfile-debug` for development with additional tools

## Critical Implementation Details

### Authentication Flow
1. Check `ENV_ICLOUD_PASSWORD` environment variable first
2. Fall back to keyring storage via `utils.get_password_from_keyring()`
3. On 2FA requirement, enter retry loop with `retry_login_interval`
4. For China region, use different endpoints in `get_api_instance()`

### File Handling Patterns
- **Path normalization**: All modules use `unicodedata.normalize()` for cross-platform compatibility
- **Atomic operations**: Files downloaded to temp paths, then moved to final location
- **Compression handling**: `sync_drive.py` auto-extracts `.zip` files and handles compressed content

### Error Handling Strategy
- **Graceful degradation**: Missing config sections disable features rather than crash
- **Exponential backoff**: Network errors use iCloudPy's built-in retry mechanisms
- **Clean exits**: Use `sleep_for < 0` pattern to exit main loop cleanly

### Container Integration
- **User management**: Runs as `abc` user (set via PUID/PGID environment variables)
- **Volume mounts**: `/config` for configuration/session data, `/icloud` for synced content
- **Session persistence**: Authentication tokens stored in `/config/session_data`

## Code Conventions
- **Module structure**: Each `src/*.py` has corresponding `tests/test_*.py`
- **Logging pattern**: Use `LOGGER = get_logger()` at module level
- **Config access**: Always use `config_parser` functions, never direct dict access
- **Error messages**: Include config path context: `config_path_to_string(config_path)`

## External Dependencies
- **iCloudPy**: Core iCloud API client (`from icloudpy import ICloudPyService`)
- **dumb-init**: Process supervision in Docker container
- **ruamel.yaml**: YAML parsing with comment preservation
- **magic**: File type detection for drive sync

When modifying sync logic, ensure both drive and photos intervals are respected in the main loop scheduling algorithm.