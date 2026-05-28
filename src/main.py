"""Main module.

Starts the embedded web UI thread (when ``app.web_ui.enabled``) and then
enters the sync loop. Both run in the same process so they share the
keyring + session-data filesystem state.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    ENV_CONFIG_FILE_PATH_KEY,
    config_parser,
    get_logger,
    read_config,
    sync,
    web,
)

LOGGER = get_logger()


def _load_config_safely():
    """Best-effort config load — returns ``None`` if config is missing or
    partial. The web UI surfaces 'setup needed' states; the sync loop
    handles missing config independently."""
    config_path = os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)
    if not os.path.isfile(config_path):
        return None
    try:
        return read_config(config_path=config_path)
    except (KeyError, AttributeError, TypeError) as e:
        LOGGER.warning(f"main: read_config failed (partial config?): {e!s}")
        return None


def run() -> None:
    """Entry point. Spawn the web UI thread if enabled, then sync loop."""
    config = _load_config_safely()
    if config and config_parser.get_web_ui_enabled(config=config):
        web.start_in_thread(
            host=config_parser.get_web_ui_host(config=config),
            port=config_parser.get_web_ui_port(config=config),
        )
    sync.sync()


if __name__ == "__main__":
    run()
