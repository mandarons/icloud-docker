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
    parser.add_argument(
        "--check-files",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Only meaningful with --dry-run. Walks N photos per library "
            "and reports per-library counts of would_skip / size_mismatch "
            "/ not_found / error against your on-disk tree. Use this "
            "BEFORE a real sync to confirm a boredazfcuk → mandarons (or "
            "any cross-tool) migration will recognise existing files "
            "instead of re-downloading them. Pass 0 to walk every photo "
            "(slow on large libraries — recommend 50–200 first)."
        ),
    )
    args = parser.parse_args()
    sync.sync(dry_run=args.dry_run, check_files=args.check_files)
