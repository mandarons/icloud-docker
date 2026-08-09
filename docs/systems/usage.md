# Usage Tracking & wapar-api Contract

The usage tracking telemetry (`src/usage.py`) reports anonymized installation and sync statistics to the wapar-api server (`https://wapar-api.mandarons.com`). This document is the **authoritative API contract** for implementing or extending the wapar-api consumer app.

## Responsibilities

- Register new installations and app upgrades on the server
- Send one heartbeat per UTC day with anonymized sync statistics
- Retry transient failures (5xx, 429, network) with exponential backoff
- Persist installation ID and app version in a local cache (`.data`) under the root destination

## Endpoints

| Endpoint | Purpose | Payload Key |
|----------|---------|-------------|
| Install | Register installation / report upgrade | `appName`, `appVersion`, optional `previousId` |
| Heartbeat | Daily sync statistics report | `installationId`, optional `data` |

- Both endpoints receive `Content-Type: application/json` (sent via `requests.post(..., json=...)`)
- Endpoint URLs come from `NEW_INSTALLATION_ENDPOINT` / `NEW_HEARTBEAT_ENDPOINT` environment variables, set as Docker build args
- Requests carry **no authentication headers** — the server must not require an API key

## Endpoint 1: Install (register installation)

### Request — new installation

```json
{
  "appName": "icloud-docker",
  "appVersion": "1.9.0"
}
```

### Request — upgrade (existing installation)

On an app upgrade the client includes the previously assigned ID so the server can retire the old record:

```json
{
  "appName": "icloud-docker",
  "appVersion": "1.10.0",
  "previousId": "9f2e2d4a-6f6a-4b3e-9a0c-1d2e3f4a5b6c"
}
```

### Field reference

| Field | Type | Required | Notes |
|--------|------|----------|-------|
| `appName` | string | yes | Always `icloud-docker` |
| `appVersion` | string | yes | e.g. `1.9.0`; `dev` in unversioned builds |
| `previousId` | string (UUID) | no | Present only on upgrades; echoes the issued ID of the previous install |

### Response — success (2xx)

The client extracts the installation ID from the JSON body — the server **must** return a top-level `id`:

```json
{
  "id": "9f2e2d2a-6f6a-4b3e-9a0c-1d2e3f4a5b6c"
}
```

| Field | Type | Notes |
|--------|------|-------|
| `id` | string (UUID) | Stable ID persisted by the client and echoed back as `previousId` on future upgrades |

Missing or malformed `id` is treated as a failed registration by the client.

## Endpoint 2: Heartbeat (sync statistics)

Sent at most once per UTC day (client-throttled by comparing cached vs. current UTC date).

### Request

```json
{
  "installationId": "9f2e2d2a-6f6a-4b3e-9a0c-1d2e3f4a5b6c",
  "data": {
    ...sync statistics object (below), or null...
  }
}
```

### Field reference

| Field | Type | Required | Notes |
|--------|------|----------|-------|
| `installationId` | string (UUID) | yes | ID returned by the install endpoint |
| `data` | object \| null | no | Sync statistics; `null` when no sync data is available |

### Response — any 2xx

The client only checks `response.ok` — the body is ignored. Current reference server returns:

```json
{
  "message": "All good."
}
```

## Sync statistics object (`data`)

Produced by `_send_usage_statistics()` in `src/sync.py` and passed as `data` to `usage.alive()`.

### Complete sample (drive + photos active)

```json
{
  "sync_duration": 312.45,
  "has_drive_activity": true,
  "has_photos_activity": true,
  "has_errors": false,
  "timestamp": "2026-08-07T12:15:33.123456+00:00",
  "drive": {
    "files_count": 42,
    "bytes_count": 104857600,
    "has_errors": false
  },
  "photos": {
    "photos_count": 128,
    "bytes_count": 209715200,
    "hardlinks_count": 12,
    "has_errors": false
  }
}
```

### Sample — drive only

```json
{
  "sync_duration": 15.2,
  "has_drive_activity": true,
  "has_photos_activity": false,
  "has_errors": true,
  "timestamp": "2026-08-07T11:02:01.000000+00:00",
  "drive": {
    "files_count": 3,
    "bytes_count": 512000,
    "has_errors": true
  }
}
```

### Sample — no activity (timers only, nothing to sync)

```json
{
  "sync_duration": 1.4,
  "has_drive_activity": false,
  "has_photos_activity": false,
  "has_errors": false,
  "timestamp": "2026-08-08T23:00:00.123456+00:00"
}
```

### Field reference

| Field | Type | Present when | Notes |
|--------|------|--------------|-------|
| `sync_duration` | number (float) | always | Sync cycle duration in seconds; `0.0` if end time missing |
| `has_drive_activity` | boolean | always | True if any drive files downloaded/skipped/removed |
| `has_photos_activity` | boolean | always | True if any photos downloaded/hardlinked/skipped |
| `has_errors` | boolean | always | True if either service reported errors |
| `timestamp` | string (ISO-8601 UTC) \| null | always | `sync_end_time.isoformat()` e.g. `2026-08-07T12:15:33.123456+00:00`; `null` if sync never completed |
| `drive` | object | when drive sync ran | Aggregated drive stats (below) |
| `photos` | object | when photos sync ran | Aggregated photo stats (below) |

#### `drive`

Payload keys are **snake_case**:

| Field | Type | Notes |
|--------|------|-------|
| `files_count` | integer | Number of files downloaded |
| `bytes_count` | integer | Bytes downloaded |
| `has_errors` | boolean | Drive sync error indicator |

#### `photos`

| Field | Type | Notes |
|--------|------|-------|
| `photos_count` | integer | Number of photos downloaded |
| `bytes_count` | integer | Bytes downloaded |
| `hardlinks_count` | integer | Photos deduplicated via hardlinks |
| `has_errors` | boolean | Photos sync error indicator |

### Privacy guarantees (server-side expectations)

- No file names, paths, or content — counts and booleans only
- No account identifiers besides the randomly generated `installationId`
- The server derives `country` from the client IP address (no geolocation fields in the payload)

## Client behavior the server must tolerate

| Aspect | Value |
|--------|-------|
| Timeouts | 10 s (install), 20 s (heartbeat) |
| Retries | Up to 3 attempts total, exponential backoff `2^attempt` seconds (1 s, 2 s) |
| Retriable | HTTP 429, any 5xx, connection errors, timeouts |
| Not retried | Other 4xx (validation errors) — the client gives up immediately |
| Heartbeat frequency | At most 1 per UTC day per installation (client-throttled) |
| Install cadence | Once per app version; upgrades resend with `previousId` |
| Optional payloads | `data` may be `null`; `drive`/`photos` sub-objects may be absent |

### Implied server requirements

- Install responses must be `2xx` with a JSON body containing a top-level `id` string — the client does `response.json()["id"]` and treats anything else as registration failure
- 4xx responses (e.g. schema validation) are not retried by the client, so validation problems surface as silently dropped installs — log them prominently server-side
- Heartbeat deduplication per (installation, UTC day) is client-side; keep server ingestion idempotent (counts that replace the day's prior value vs. appends will change dashboard numbers)

## Testing & Development

Point the client at a local test server without touching production:

```bash
NEW_INSTALLATION_ENDPOINT=http://localhost:8000/api/installations \
NEW_HEARTBEAT_ENDPOINT=http://localhost:8000/api/heartbeats \
python src/main.py --once
```

Or bake URLs into the container image:

```bash
docker build \
  --build-arg NEW_INSTALLATION_ENDPOINT=http://localhost:8000/api/installations \
  --build-arg NEW_HEARTBEAT_ENDPOINT=http://localhost:8000/api/heartbeats \
  -t mandarons/icloud-drive .
```

### Test fixtures

- `tests/mocked_usage_post` (`tests/__init__.py`) simulates the server: install → `201 {"id": "<uuid>"}`, heartbeat → `201 {"message": "All good."}`, anything else → `404`
- `tests/test_usage.py` exercises install, upgrade (`previousId`), heartbeat, retry, and throttling paths
- Requests must be sniffed as JSON (`Content-Type: application/json`) with body exactly as documented above