# Container

The container system (`Dockerfile`, `docker-entrypoint.sh`, `init.sh`) manages the Docker runtime environment.

## Responsibilities

- Build minimal Alpine Linux image with Python 3.10
- Manage user creation and PUID/PGID mapping
- Handle volume mount ownership and keyring migration
- Start the application via `su-exec` (setuid alternative)
- Support debug builds with `debugpy`

## Build Stages

1. **Builder:** Installs build dependencies, compiles Python packages
2. **Runtime:** Copies built packages to minimal Alpine image

## Key Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Production multi-stage build |
| `Dockerfile-debug` | Debug build with `debugpy` on port 5678 |
| `docker-entrypoint.sh` | Container entry point — user setup, ownership |
| `init.sh` | Starts `python ./src/main.py` with `PYTHONPATH=/app` |

## User Management

- Creates `abc` user with configurable `PUID`/`PGID` (default 911:911)
- Uses `su-exec` for setuid execution (no S6 overlay)
- Uses `shadow` package for user management

## Volume Mounts

| Mount | Purpose | Default |
|-------|---------|---------|
| `/config` | config.yaml + session_data/ + python_keyring/ | Required |
| `/icloud` | Synced content (drive/ + photos/) | Required |

## Entrypoint Sequence

1. `docker-entrypoint.sh` — sets UID/GID, creates user, migrates keyring
2. `su-exec abc /app/init.sh` — drops privileges
3. `python src/main.py` — starts application

## Invariants

- Runs as `abc` user (non-root) after entrypoint
- Session data persists in `/config/session_data` (icloudpy cookie dir)
- Keyring data persists in `/config/python_keyring/`
- `ICLOUD_DOCKER_CONFIG_DIR` env var overrides base config directory

## Dependencies

- **Depends on:** Alpine Linux, su-exec, shadow
- **Depended on by:** Docker Hub builds

## Tests

- `tests/test_docker_entrypoint.py` — entrypoint behavior tests
- `tests/test_container_integration.py` — integration tests
- Run: `ENV_CONFIG_FILE_PATH=./tests/data/test_config.yaml pytest tests/test_docker_entrypoint.py tests/test_container_integration.py`

## Related Docs

- [Configuration](configuration.md)
- [Glossary](../glossary.md)
