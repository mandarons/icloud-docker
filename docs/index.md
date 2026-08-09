# Architecture Index

**Start here** for an overview of the iCloud Docker system.

## Purpose

iCloud Docker is a containerized sync client that downloads files from Apple iCloud Drive and iCloud Photos to a local filesystem. It runs as a long-running Docker service, authenticating via Apple ID credentials and 2FA, and supports multiple notification channels. An optional Flask web UI provides a dashboard for monitoring sync status and completing 2FA re-authentication from a browser.

## System Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                     │
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐  │
│  │   main.py    │───▶│         sync.py               │  │
│  │  (CLI entry) │    │  (adaptive sync loop)         │  │
│  └──────┬───────┘    └──────┬───────────────┬───────┘  │
│         │                   │               │           │
│         ▼                   ▼               ▼           │
│  ┌──────────────┐   ┌────────────┐  ┌────────────┐    │
│  │  web.py      │   │ sync_drive │  │ sync_photos│    │
│  │  (Flask UI)  │   │ (8 modules)│  │ (7 modules)│    │
│  └──────────────┘   └────────────┘  └────────────┘    │
│         │                   │               │           │
│         ▼                   ▼               ▼           │
│  ┌──────────────┐   ┌─────────────────────────────┐   │
│  │web_signals.py│   │     config_parser.py         │   │
│  │ (cross-thread│   │  (YAML + env overrides)      │   │
│  │  signalling) │   └─────────────────────────────┘   │
│  └──────────────┘                                       │
│                                                         │
│  ┌──────────────┐   ┌─────────────────────────────┐   │
│  │  notify.py   │   │       usage.py               │   │
│  │ (Discord,    │   │  (anonymized telemetry)      │   │
│  │  Telegram,   │   └─────────────────────────────┘   │
│  │  SMTP, etc.) │                                       │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
         │                    │                │
         ▼                    ▼                ▼
    iCloud API          Local FS          Notification
    (iCloudPy)       (/icloud mount)     Services (webhooks)
```

## Component Map

| Component | Responsibility | Source Dir | System Doc |
|-----------|---------------|------------|------------|
| Entry Point | CLI parsing, web UI thread spawn | `src/main.py` | — |
| Sync Engine | Adaptive scheduling, 2FA handling, dry-run | `src/sync.py` | [docs/systems/sync-engine.md](systems/sync-engine.md) |
| Configuration | YAML parsing, env overrides, validation | `src/config_parser.py`, `config_utils.py` | [docs/systems/configuration.md](systems/configuration.md) |
| Drive Sync | File downloading, parallel threads, filtering | `src/sync_drive.py` + 7 helpers | [docs/systems/drive-sync.md](systems/drive-sync.md) |
| Photos Sync | Photo downloading, albums, hardlinks | `src/sync_photos.py` + 6 helpers | [docs/systems/photos-sync.md](systems/photos-sync.md) |
| Web UI | Flask dashboard, 2FA auth flow, CSRF | `src/web.py` | [docs/systems/web-ui.md](systems/web-ui.md) |
| Notifications | Discord, Telegram, Pushover, SMTP | `src/notify.py` | [docs/systems/notifications.md](systems/notifications.md) |
| Usage Tracking | Anonymized install/heartbeat telemetry, wapar-api contract | `src/usage.py` | [docs/systems/usage.md](systems/usage.md) |
| Container | Docker build, entrypoint, user mgmt | `Dockerfile`, `docker-entrypoint.sh` | [docs/systems/container.md](systems/container.md) |

## Key Flows

| Flow | Description | Doc |
|------|-------------|-----|
| Authentication | 2FA handling, password management, China region | [docs/flows/authentication.md](flows/authentication.md) |
| Sync Cycle | End-to-end sync loop execution | [docs/flows/sync-cycle.md](flows/sync-cycle.md) |

## Standards

- [Coding Standards](standards/coding.md) — patterns, naming, error handling
- [Testing Standards](standards/testing.md) — structure, coverage, mock patterns
- [Glossary](glossary.md) — domain terminology

## Data Flow

1. **Config load:** `config_parser.py` reads YAML + env overrides on every sync iteration
2. **Auth:** `sync.py` authenticates via iCloudPy (keyring or env password)
3. **Drive sync:** `sync_drive.py` walks iCloud Drive tree, downloads files in parallel
4. **Photos sync:** `sync_photos.py` enumerates albums, downloads with hardlink dedup
5. **Notifications:** `notify.py` sends 2FA alerts and sync summaries
6. **Telemetry:** `usage.py` sends anonymized stats (opt-out available)

## External Dependencies

| Dependency | Purpose | Version |
|-----------|---------|---------|
| iCloudPy | iCloud API client | 0.9.0 |
| ruamel.yaml | YAML parsing with comment preservation | 0.19.1 |
| python-magic | File type detection (ZIP/gzip) | 0.4.27 |
| Flask | Web UI framework | 3.1.3 |
| requests | HTTP client for notifications | ~2.32.3 |
