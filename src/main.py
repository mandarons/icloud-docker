"""Main module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import argparse

from src import sync

if __name__ == "__main__":
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
    args = parser.parse_args()
    sync.sync(dry_run=args.dry_run)
