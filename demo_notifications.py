#!/usr/bin/env python3
"""
Demo script to show sync summary notification functionality.

This script demonstrates how the sync summary feature works by:
1. Creating sample sync statistics
2. Formatting notification messages
3. Showing what notifications would look like
"""

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sync_stats import DriveStats, PhotoStats, SyncSummary, format_bytes, format_duration


def format_sync_summary_message(summary):
    """
    Format sync summary as notification message (simplified version for demo).
    """
    has_errors = summary.has_errors()
    status_emoji = "⚠️" if has_errors else "✅"
    status_text = "Completed with Errors" if has_errors else "Complete"

    message_lines = [f"{status_emoji} iCloud Sync {status_text}", ""]

    # Drive statistics
    if summary.drive_stats and summary.drive_stats.has_activity():
        drive = summary.drive_stats
        message_lines.append("📁 Drive:")
        if drive.files_downloaded > 0:
            size_str = format_bytes(drive.bytes_downloaded)
            message_lines.append(f"  • Downloaded: {drive.files_downloaded} files ({size_str})")
        if drive.files_skipped > 0:
            message_lines.append(f"  • Skipped: {drive.files_skipped} files (up-to-date)")
        if drive.files_removed > 0:
            message_lines.append(f"  • Removed: {drive.files_removed} obsolete files")
        if drive.duration_seconds > 0:
            duration_str = format_duration(drive.duration_seconds)
            message_lines.append(f"  • Duration: {duration_str}")
        if drive.has_errors():
            message_lines.append(f"  • Errors: {len(drive.errors)} failed")
        message_lines.append("")

    # Photos statistics
    if summary.photo_stats and summary.photo_stats.has_activity():
        photos = summary.photo_stats
        message_lines.append("📷 Photos:")
        if photos.photos_downloaded > 0:
            size_str = format_bytes(photos.bytes_downloaded)
            message_lines.append(f"  • Downloaded: {photos.photos_downloaded} photos ({size_str})")
        if photos.photos_hardlinked > 0:
            message_lines.append(f"  • Hard-linked: {photos.photos_hardlinked} photos")
        if photos.bytes_saved_by_hardlinks > 0:
            saved_str = format_bytes(photos.bytes_saved_by_hardlinks)
            message_lines.append(f"  • Storage saved: {saved_str}")
        if photos.albums_synced:
            albums_str = ", ".join(photos.albums_synced[:5])
            if len(photos.albums_synced) > 5:
                albums_str += f" (+{len(photos.albums_synced) - 5} more)"
            message_lines.append(f"  • Albums: {albums_str}")
        if photos.duration_seconds > 0:
            duration_str = format_duration(photos.duration_seconds)
            message_lines.append(f"  • Duration: {duration_str}")
        if photos.has_errors():
            message_lines.append(f"  • Errors: {len(photos.errors)} failed")
        message_lines.append("")

    # Error details if present
    if has_errors:
        message_lines.append("Failed items:")
        all_errors = []
        if summary.drive_stats:
            all_errors.extend(summary.drive_stats.errors[:5])
        if summary.photo_stats:
            all_errors.extend(summary.photo_stats.errors[:5])
        message_lines.extend([f"  • {error}" for error in all_errors[:10]])
        total_errors = 0
        if summary.drive_stats:
            total_errors += len(summary.drive_stats.errors)
        if summary.photo_stats:
            total_errors += len(summary.photo_stats.errors)
        if total_errors > 10:
            message_lines.append(f"  ... and {total_errors - 10} more errors")
        message_lines.append("")

    message = "\n".join(message_lines)
    subject = f"icloud-docker: Sync {status_text}"
    return message, subject


def demo_successful_sync():
    """Demo a successful sync with drive and photos."""
    print("=" * 80)
    print("DEMO: Successful Sync with Drive and Photos")
    print("=" * 80)
    
    # Create drive statistics
    drive_stats = DriveStats(
        files_downloaded=15,
        files_skipped=234,
        files_removed=3,
        bytes_downloaded=2415919104,  # ~2.3 GB
        duration_seconds=272,  # 4m 32s
    )
    
    # Create photo statistics
    photo_stats = PhotoStats(
        photos_downloaded=42,
        photos_hardlinked=128,
        bytes_downloaded=1932735283,  # ~1.8 GB
        bytes_saved_by_hardlinks=5798205849,  # ~5.4 GB
        albums_synced=["All Photos", "Favorites", "Family"],
        duration_seconds=135,  # 2m 15s
    )
    
    # Create summary
    summary = SyncSummary(
        drive_stats=drive_stats,
        photo_stats=photo_stats,
    )
    
    # Format message
    message, subject = format_sync_summary_message(summary)
    
    print(f"\nSubject: {subject}\n")
    print(message)
    print()


def demo_sync_with_errors():
    """Demo a sync with errors."""
    print("=" * 80)
    print("DEMO: Sync with Errors")
    print("=" * 80)
    
    # Create drive statistics with errors
    drive_stats = DriveStats(
        files_downloaded=3,
        bytes_downloaded=157286400,  # ~150 MB
        duration_seconds=80,  # 1m 20s
        errors=[
            "/Documents/Report.pdf (timeout)",
            "/Documents/Large_File.zip (connection reset)",
        ],
    )
    
    # Create photo statistics with errors
    photo_stats = PhotoStats(
        photos_downloaded=10,
        bytes_downloaded=471859200,  # ~450 MB
        duration_seconds=45,
        errors=["/Photos/IMG_1234.heic (File not found)"],
    )
    
    # Create summary
    summary = SyncSummary(
        drive_stats=drive_stats,
        photo_stats=photo_stats,
    )
    
    # Format message
    message, subject = format_sync_summary_message(summary)
    
    print(f"\nSubject: {subject}\n")
    print(message)
    print()


def demo_drive_only_sync():
    """Demo a drive-only sync."""
    print("=" * 80)
    print("DEMO: Drive-Only Sync")
    print("=" * 80)
    
    # Create drive statistics only
    drive_stats = DriveStats(
        files_downloaded=8,
        files_skipped=102,
        bytes_downloaded=524288000,  # ~500 MB
        duration_seconds=120,  # 2m
    )
    
    # Create summary
    summary = SyncSummary(drive_stats=drive_stats)
    
    # Format message
    message, subject = format_sync_summary_message(summary)
    
    print(f"\nSubject: {subject}\n")
    print(message)
    print()


def demo_photos_only_sync_with_hardlinks():
    """Demo a photos-only sync with extensive hardlinking."""
    print("=" * 80)
    print("DEMO: Photos-Only Sync with Hard Links")
    print("=" * 80)
    
    # Create photo statistics with heavy hardlink usage
    photo_stats = PhotoStats(
        photos_downloaded=20,
        photos_hardlinked=200,
        bytes_downloaded=1073741824,  # 1 GB
        bytes_saved_by_hardlinks=10737418240,  # 10 GB saved!
        albums_synced=["All Photos", "Favorites", "Family", "Vacation 2023", "Work", "Friends"],
        duration_seconds=180,  # 3m
    )
    
    # Create summary
    summary = SyncSummary(photo_stats=photo_stats)
    
    # Format message
    message, subject = format_sync_summary_message(summary)
    
    print(f"\nSubject: {subject}\n")
    print(message)
    print()


def demo_formatting_functions():
    """Demo the formatting utility functions."""
    print("=" * 80)
    print("DEMO: Formatting Utility Functions")
    print("=" * 80)
    
    print("\nByte Formatting:")
    print(f"  500 bytes = {format_bytes(500)}")
    print(f"  1.5 KB = {format_bytes(1536)}")
    print(f"  2.3 GB = {format_bytes(2415919104)}")
    print(f"  5.4 GB = {format_bytes(5798205849)}")
    
    print("\nDuration Formatting:")
    print(f"  30 seconds = {format_duration(30)}")
    print(f"  90 seconds = {format_duration(90)}")
    print(f"  272 seconds = {format_duration(272)}")
    print(f"  4500 seconds = {format_duration(4500)}")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("iCloud-Docker Sync Summary Notification Demo")
    print("=" * 80 + "\n")
    
    demo_successful_sync()
    demo_sync_with_errors()
    demo_drive_only_sync()
    demo_photos_only_sync_with_hardlinks()
    demo_formatting_functions()
    
    print("=" * 80)
    print("Demo Complete!")
    print("=" * 80)
