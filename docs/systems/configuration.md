# Configuration

The configuration system (`src/config_parser.py`, `src/config_utils.py`, `src/config_logging.py`) provides YAML-based config with environment variable overrides.

## Responsibilities

- Parse YAML config file with `ruamel.yaml` (preserves comments)
- Provide typed accessor functions (`get_username()`, `get_drive_sync_interval()`, etc.)
- Validate config values and log warnings for invalid/missing keys
- Support environment variable overrides (`ENV_CONFIG_FILE_PATH`, `ENV_ICLOUD_PASSWORD`)
- Create and validate destination directories

## Boundaries

The config system is a pure data layer — it does NOT perform sync operations, network calls, or file downloads. It reads config and returns values.

## Key Entry Points

| Function | Purpose |
|----------|---------|
| `get_username(config)` | Validate and return iCloud username |
| `get_drive_sync_interval(config)` | Return drive interval in seconds |
| `get_photos_sync_interval(config)` | Return photos interval in seconds |
| `get_app_max_threads(config)` | Return thread count (auto or 1-16) |
| `prepare_drive_destination(config)` | Create and return drive dest path |
| `prepare_photos_destination(config)` | Create and return photos dest path |
| `get_web_ui_enabled(config)` | Check if web UI is enabled |

## Config Access Pattern

ALWAYS use this pattern — NEVER direct dict access:

```python
# CORRECT
from src import config_parser
username = config_parser.get_username(config=config)

# WRONG — causes KeyError crashes
username = config["app"]["credentials"]["username"]
```

The underlying pattern is `traverse_config_path()` → `get_config_value()`:

```python
from src.config_utils import traverse_config_path, get_config_value

config_path = ["app", "credentials", "username"]
traverse_config_path(config=config, config_path=config_path)
value = get_config_value(config=config, config_path=config_path)
```

## Invariants

- Config is reloaded on every sync iteration — values can change at runtime
- Missing sections disable features gracefully (no crash)
- `get_app_max_threads()` caps at `min(CPU_COUNT, 8)` for server protection
- Max thread limit is 16 — never exceed this
- Username is always stripped before use

## Dependencies

- **Depends on:** `config_utils`, `config_logging`, `filesystem_utils`, `src` (constants)
- **Depended on by:** `sync.py`, `sync_drive.py`, `sync_photos.py`, `web.py`, `notify.py`

## Tests

- `tests/test_config_parser.py` — comprehensive config tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_config_parser.py`

## Related Docs

- [Coding Standards](../standards/coding.md) — config access rules
- [Glossary](../glossary.md) — config terminology
