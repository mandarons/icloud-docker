# Coding Standards

General coding patterns, naming conventions, and error handling rules for this codebase.

## Config Access

**MUST** use `config_parser.get_*()` functions — NEVER direct dict access.

```python
# CORRECT
username = config_parser.get_username(config=config)

# WRONG — causes KeyError crashes
username = config["app"]["credentials"]["username"]
```

When reading deeply nested config, ALWAYS call `traverse_config_path()` first:

```python
from src.config_utils import traverse_config_path, get_config_value

config_path = ["app", "credentials", "username"]
traverse_config_path(config=config, config_path=config_path)
value = get_config_value(config=config, config_path=config_path)
```

## Logging

**MUST** use `LOGGER = get_logger()` at module level — never instantiate loggers inline.

```python
from src import get_logger
LOGGER = get_logger()

# Use throughout module
LOGGER.info("Syncing drive...")
LOGGER.error(f"Failed: {e!s}")
```

**MUST** call `configure_icloudpy_logging()` immediately after imports to suppress verbose iCloudPy logs:

```python
from src import configure_icloudpy_logging
configure_icloudpy_logging()
```

## File Path Normalization

**MUST** normalize all file paths with NFC for storage:

```python
import unicodedata
normalized = unicodedata.normalize("NFC", path)
```

**MUST** normalize to NFD when comparing existing files on macOS/Windows.

## Module Structure

Each `src/*.py` module MUST have a corresponding `tests/test_*.py` mirror. Modules follow SRP — one clear purpose per function.

## Error Handling

- **Graceful degradation:** Missing config sections disable features, don't crash
- **Notification failures:** Always caught and logged — never break the sync loop
- **Network errors:** iCloudPy has built-in retry for transient failures

## Type Annotations

All new functions MUST have comprehensive type hints and docstrings.

## Constants

Define constants in `src/__init__.py` (e.g., `DEFAULT_COOKIE_DIRECTORY`).

## Related Docs

- [Testing Standards](testing.md)
- [Configuration](../systems/configuration.md)
