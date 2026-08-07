# Testing Standards

Test structure, coverage requirements, and mock patterns for this codebase.

## Coverage Requirement

100% test coverage is enforced — `pytest.ini` includes `--cov-fail-under=100`. Build fails below 100%.

## Test Structure

Every `src/*.py` module MUST have a corresponding `tests/test_*.py` mirror:

| Source | Test |
|--------|------|
| `src/sync.py` | `tests/test_sync.py` |
| `src/sync_drive.py` | `tests/test_sync_drive.py` |
| `src/sync_photos.py` | `tests/test_sync_photos.py` |
| `src/web.py` | `tests/test_web.py` |
| `src/config_parser.py` | `tests/test_config_parser.py` |
| `src/notify.py` | `tests/test_notify.py` |

## Running Tests

```bash
# Full test suite
ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest

# Specific test file
ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync.py

# Full CI pipeline (ruff + pytest + allure)
./run-ci.sh
```

## Mock Strategy

Tests use `ICloudPyServiceMock` in `tests/data/__init__.py` (4000+ lines) with photo fixtures in `tests/data/photos_data.py` (2800+ lines).

- Mock iCloud API responses for deterministic testing
- Use `tests.CONFIG_PATH` and `tests.TEMP_DIR` for config injection
- All tests use `setUp()/tearDown()` pattern to clean `tests.TEMP_DIR`

## conftest.py Fixtures

Two autouse fixtures in `tests/conftest.py`:

1. **`_redirect_config_dir`** (session-wide): Redirects `ICLOUD_DOCKER_CONFIG_DIR` to a writable tempdir. Reassigns `src.DEFAULT_COOKIE_DIRECTORY` and `src.usage.CACHE_FILE_NAME` at runtime.

2. **`_restore_env_config_file_path`** (per-test): Snapshots and restores `ENV_CONFIG_FILE_PATH` to prevent test pollution.

## Test Commands

| Task | Command |
|------|---------|
| Run all tests | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest` |
| Run with coverage report | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest --cov-report html` |
| Run specific test | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync.py::test_sync` |
| Run CI pipeline | `./run-ci.sh` |

## Quality Gates

Before merging, ALL of these must pass:
- `ruff check` — no lint errors
- `ruff format` — consistent formatting
- `pytest` — 100% coverage, all tests pass
- `bandit` — no security issues

## Related Docs

- [Coding Standards](coding.md)
- [Sync Engine](../systems/sync-engine.md)
