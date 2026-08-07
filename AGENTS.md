# iCloud Docker

A containerized iCloud sync client that periodically downloads files from Apple iCloud Drive and iCloud Photos to a local filesystem. Runs as a long-running Docker service with an optional Flask web UI for monitoring and 2FA re-authentication.

## Quick Reference

- **Language:** Python 3.10
- **Framework:** Flask (web UI), iCloudPy (iCloud API)
- **Package manager:** pip

## Commands

| Task | Command |
|------|---------|
| Install dependencies | `pip install -r requirements-test.txt` |
| Run tests | `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest` |
| Run linter | `ruff check` |
| Run formatter | `ruff format` |
| Run full CI pipeline | `./run-ci.sh` |
| Security scan | `bandit --quiet --format=custom --configfile=tests/bandit.yaml src/ tests/` |
| Docker build | `docker build -t mandarons/icloud-drive .` |

Always run the linter and tests before declaring work complete.

## Architecture Overview

The system is a single-process Python application with two concurrent activities: a sync loop (main thread) and an optional Flask web UI (daemon thread). The sync loop authenticates with iCloud, then alternates between Drive and Photos sync based on adaptive countdown timers. Configuration is YAML-based with environment variable overrides, reloaded on every sync iteration. The codebase follows SRP — monolithic modules have been split into focused helpers (8 for Drive, 7 for Photos).

See `docs/index.md` for the full architecture document.

## Key Conventions

- **NEVER use direct dict access** for config — always use `config_parser.get_*()` functions via `traverse_config_path()`
- **Every `src/*.py` must have a mirror `tests/test_*.py`** — 100% test coverage is enforced (`--cov-fail-under=100`)
- **Use `LOGGER = get_logger()`** at module level — never instantiate loggers inline
- **Normalize all file paths** with `unicodedata.normalize("NFC", path)` for macOS/Windows compatibility

See `docs/standards/` for detailed coding and testing standards.

## Safety and Constraints

- **Config validation:** Missing `traverse_config_path()` checks cause `KeyError` crashes — always validate before reading
- **Thread limits:** Never exceed 16 `max_threads` (server protection) — auto caps at `min(CPU, 8)`
- **Unicode normalization:** All file paths MUST be NFC-normalized for storage, NFD for comparison
- **Test coverage:** 100% required — new code MUST have corresponding test cases in `tests/`
- **Web UI security:** No built-in auth — host `127.0.0.1` (default) keeps it loopback-only; `0.0.0.0` requires a reverse proxy

## Documentation Map

- `docs/index.md` — Start here for architecture and component overview
- `docs/systems/` — Per-component documentation
- `docs/flows/` — End-to-end flow documentation
- `docs/standards/` — Coding and testing standards
- `docs/glossary.md` — Domain terminology

## Documentation Maintenance

**Before pushing changes, verify documentation is still accurate.** Stale docs mislead future agents and humans.

1. **Module signature changes:** If you add/remove/rename a public function in `src/*.py`, update the "Key Entry Points" table in the corresponding `docs/systems/<component>.md`.
2. **New modules:** If you add a new `src/*.py`, add it to `docs/index.md` component map, `src/AGENTS.md` module map, and create a `docs/systems/<name>.md` if it has non-trivial responsibilities.
3. **Config keys:** If you add/modify/remove a config key, update `docs/systems/configuration.md` and the sample config in `README.md`.
4. **Commands:** If build/test/lint commands change, update both `AGENTS.md` and `tests/AGENTS.md`.
5. **Conventions:** If a coding or testing convention changes, update `docs/standards/` accordingly.
6. **Flow changes:** If you alter the sync loop, authentication, or notification flow, update the corresponding `docs/flows/*.md`.
7. **Glossary:** If you introduce domain-specific terms, add them to `docs/glossary.md`.

When in doubt, read the doc you would need to update and check if it still matches reality.

## Working in This Repo

1. Read `docs/index.md` for architecture context before making changes.
2. Check `docs/systems/<component>.md` for the component you are modifying.
3. Run tests after every change.
4. Follow the standards in `docs/standards/`.
5. Update documentation before pushing (see Documentation Maintenance above).
