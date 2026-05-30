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

    # Validate the --check-files / --dry-run combination before handing off
    # to sync.sync(). Without these guards, `--check-files 10` (no
    # --dry-run) starts the normal sync loop and silently ignores the
    # flag, and `--check-files -1` is treated as "walk everything" by
    # the migration walkers (since `if sample > 0` is the cap-check) —
    # both of which trip up users expecting fail-fast feedback.
    if args.check_files is not None:
        if not args.dry_run:
            parser.error("--check-files requires --dry-run")
        if args.check_files < 0:
            parser.error(
                "--check-files must be a non-negative integer "
                "(0 means walk everything, N > 0 caps the walk at N)",
            )

    sync.sync(dry_run=args.dry_run, check_files=args.check_files)
