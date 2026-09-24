# Tests

This directory contains the test suite for iCloud Docker.

## Local Rules

- **Every `src/*.py` must have a corresponding `tests/test_*.py`**
- **100% test coverage is enforced** (`--cov-fail-under=100` in pytest.ini)
- **Use `setUp()/tearDown()`** pattern to clean `tests.TEMP_DIR`
- **Never modify production config** — use `tests/data/test_config.yaml`

## Test Commands

| Task | Command |
|------|---------|
| Run all tests | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest` |
| Run specific test file | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_sync.py` |
| Run with coverage report | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest --cov-report html` |
| Run CI pipeline | `./run-ci.sh` |

## Key Files

| File | Purpose |
|------|---------|
| `conftest.py` | Autouse fixtures for config dir redirect and env restore |
| `data/__init__.py` | `ICloudPyServiceMock` (4000+ lines) |
| `data/photos_data.py` | Photo fixtures (2800+ lines) |
| `data/test_config.yaml` | Test configuration file |

## Mock Strategy

- Mock iCloud API responses with `ICloudPyServiceMock`
- Use `tests.CONFIG_PATH` and `tests.TEMP_DIR` for config injection
- All tests use `setUp()/tearDown()` pattern to clean temp directories

## Quality Gates

Before declaring work complete, run:
1. `ruff check` — no lint errors
2. `ruff format` — consistent formatting
3. `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest` — 100% coverage, all tests pass

## Related Docs

- `docs/standards/testing.md` — Testing standards
- `docs/systems/` — Component documentation

## Keep Docs Current

If test commands, mock patterns, or coverage requirements change, update `docs/standards/testing.md` and `tests/AGENTS.md`. See `AGENTS.md` Documentation Maintenance section for full checklist.
