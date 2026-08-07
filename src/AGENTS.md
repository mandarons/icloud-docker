# Source Code

This directory contains the application source code for iCloud Docker.

## Local Rules

- **NEVER use direct dict access** for config — always use `config_parser.get_*()` via `traverse_config_path()`
- **Use `LOGGER = get_logger()`** at module level — never instantiate loggers inline
- **Call `configure_icloudpy_logging()`** immediately after imports to suppress verbose iCloudPy logs
- **Normalize all file paths** with `unicodedata.normalize("NFC", path)` for macOS/Windows compatibility
- **Every function MUST have type hints and docstrings**

## Module Map

| Module | Purpose |
|--------|---------|
| `__init__.py` | Root module: config reading, logging setup, constants |
| `main.py` | Entry point: argparse CLI, spawns web UI thread |
| `sync.py` | Main sync loop orchestrator |
| `sync_drive.py` | Drive sync orchestration (8 helper modules) |
| `sync_photos.py` | Photos sync orchestration (7 helper modules) |
| `config_parser.py` | High-level config retrieval |
| `config_utils.py` | Low-level config traversal utilities |
| `config_logging.py` | Config-related logging helpers |
| `web.py` | Flask web UI |
| `web_signals.py` | Cross-thread signalling |
| `notify.py` | Multi-provider notifications |
| `usage.py` | Anonymized usage tracking |
| `templates/` | Flask HTML templates |

## Key Conventions

- Follow SRP — one clear purpose per function
- All file operations must be thread-safe
- Use `files_lock` when modifying shared state in parallel workers
- Download to temp paths, then move atomically to final location

## Related Docs

- `docs/systems/` — Per-component documentation
- `docs/standards/coding.md` — Coding standards
- `docs/standards/testing.md` — Testing standards

## Keep Docs Current

When modifying this module, update the corresponding `docs/systems/<name>.md` — especially the "Key Entry Points" table if you add/remove/rename public functions. See `AGENTS.md` Documentation Maintenance section for full checklist.
