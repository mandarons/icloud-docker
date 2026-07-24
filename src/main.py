"""Main module.

Starts the embedded web UI thread (when ``app.web_ui.enabled``) and then
enters the sync loop. Both run in the same process so they share the
keyring + session-data filesystem state.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import argparse
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
    """Best-effort config load -- returns ``None`` if config is missing or
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


def run(dry_run: bool = False, check_files: int | None = None) -> None:
    """Entry point. Spawn the web UI thread if enabled, then run the sync
    loop. ``dry_run`` / ``check_files`` are threaded straight through to
    ``sync.sync`` (the web thread is a daemon, so a dry run still exits)."""
    config = _load_config_safely()
    if config and config_parser.get_web_ui_enabled(config=config):
        web.start_in_thread(
            host=config_parser.get_web_ui_host(config=config),
            port=config_parser.get_web_ui_port(config=config),
        )
    sync.sync(dry_run=dry_run, check_files=check_files)


if __name__ == "__main__":  # pragma: no cover -- script entry, not test-callable
    parser = argparse.ArgumentParser(
        prog="icloud-docker",
        description="iCloud Drive + Photos backup loop. See config.yaml for runtime settings.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Authenticate, summarise what would be synced, then exit "
            "without downloading or modifying any files. Useful for "
            "verifying credentials + mount paths + config before the "
            "real sync loop is allowed to run."
        ),
    )
    parser.add_argument(
        "--check-files",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Only meaningful with --dry-run. Walks N photos per library "
            "and reports per-library counts of would_skip / size_mismatch "
            "/ not_found / error against your on-disk tree. Use this "
            "BEFORE a real sync to confirm a boredazfcuk -> mandarons (or "
            "any cross-tool) migration will recognise existing files "
            "instead of re-downloading them. Pass 0 to walk every photo "
            "(slow on large libraries -- recommend 50-200 first)."
        ),
    )
    args = parser.parse_args()

    # Validate the --check-files / --dry-run combination before handing off
    # to run(). Without these guards, `--check-files 10` (no --dry-run)
    # starts the normal sync loop and silently ignores the flag, and
    # `--check-files -1` is treated as "walk everything" by the migration
    # walkers -- both of which trip up users expecting fail-fast feedback.
    if args.check_files is not None:
        if not args.dry_run:
            parser.error("--check-files requires --dry-run")
        if args.check_files < 0:
            parser.error(
                "--check-files must be a non-negative integer "
                "(0 means walk everything, N > 0 caps the walk at N)",
            )

    run(dry_run=args.dry_run, check_files=args.check_files)
