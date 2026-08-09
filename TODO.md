# TODO: Usage Tracker Fixes

Tracking buffer for the usage-tracking audit (2026-08-07). All findings below were
verified against the current codebase and its git history. The goal is to resolve
**all** of these items in a follow-up session.

## Status

All items resolved in the current working tree (uncommitted). See individual items
below for details on each fix.

## Context

The usage tracker (`src/usage.py`) was comprehensively refactored in commit `091fa55`
("feat: comprehensive refactor of usage tracking module") with the goal of 100% test
coverage. That refactor introduced or perpetuated several bugs that prevent the data
described in `USAGE.md` from actually reaching the server. Coverage is 100% but the
tests exercise each function in isolation and never verify the *multi-day sync-loop
sequence*, which is where the worst bugs live.

## Priority Ranking

| # | Finding | Severity | Signal |
|---|---------|----------|--------|
| A | Sync statistics are effectively never sent after the first day | High | USAGE.md feature #2 is dead |
| B | Cache file path ignores the configured root destination | High | regression + duplicate install events |
| C | `post_with_retry` swallows 5xx/429 responses | Medium | no server-side diagnostics |
| E | `appName` sent is "icloud-docker" vs image name "icloud-drive" | Medium | server-side metric pollution |
| F | Misc: throttle semantics, `utcnow()`, zero-microsecond timestamp edge | Low | hygiene |

> Design decisions (2026-08-07):
> - Local/developer/CI builds are intentionally **not** tracked — no telemetry
>   from them (removed former finding D). No build-arg/convenience work for that.
> - Telemetry failures must **fail silently**: no ERROR/WARNING surfaced to the
>   user in sync logs — all usage-tracking failure paths log at DEBUG only.

---

## A. Sync statistics are effectively never sent after the first day

**Signal:** `src/sync.py:980` (top of loop) vs `src/sync.py:1090` (post-sync).

### What happens

Every sync-loop iteration calls `alive()` twice:

1. `src/sync.py:980` — `alive(config=config)` — **no data** — runs BEFORE
   authentication, on every iteration.
2. `src/sync.py:1090` — `_send_usage_statistics(config, summary)` →
   `alive(config=config, data=usage_data)` — only after a successful sync.

`alive()` → `heartbeat()` (`src/usage.py:337`) throttles to **once per UTC day**
(`src/usage.py:358`, `previous.date() < current.date()`). Because call #1 always
runs first, it always wins the daily heartbeat slot — and it sends `data=None`.

### Resulting behavior

- **Day 0 (installation/upgrade):** `alive()` #1 installs the app; `alive()` #2 then
  sends one heartbeat **with** the day's sync statistics ("first heartbeat" path,
  `src/usage.py:373-378`). Data reaches the server exactly once.
- **Every subsequent day:** `alive()` #1 sends the daily heartbeat with `data=None`;
  `alive()` #2 is throttled (`same UTC day`) and returns `None`; the stats payload is
  silently dropped. Forever.

So the "Sync statistics" feature promised by `USAGE.md` delivers at best one payload
per installation/version, then silence.

### Why tests don't catch it

- `tests/test_sync.py:745, 788` — `@patch("src.usage.alive")`, so the loop-level
  interplay is never exercised.
- `tests/test_usage.py` tests `heartbeat()` in isolation with a single UTC day,
  never the two-calls-per-iteration ordering.

### Suggested fix (options)

1. **Remove the top-of-loop call** (`src/sync.py:979-980`) and let
   `_send_usage_statistics` be the single daily heartbeat carrier (its `alive()`
   handles install + heartbeat + payload in one place). Note: install registration
   then only happens on the first successful sync — acceptable.
2. Or pass the stats into the top-of-loop call — but stats don't exist yet there, so
   option 1 is cleaner.
3. Either way, add an integration-style test: simulate day-1 (install + stats),
   next loop iteration (same day, throttled), next UTC day (top-of-loop without data,
   stats dropped) and assert the server receives stats on the first day only — then
   decide what the *correct* contract is (e.g., daily stats payload with the last
   cycle's data).

### Verification steps

- Read `src/sync.py:973-1135` and trace both `alive()` invocations per iteration.
- `git show 091fa5525^:src/sync.py` — the top-of-loop `alive(config=config)` existed
  before the refactor; the refactor added `_send_usage_statistics` without removing it.

---

## B. Cache file path silently ignores the configured root destination

**Signal:** `src/usage.py:22` and `src/usage.py:43-45`.

### What

```python
CACHE_FILE_NAME = os.path.join(os.environ.get("ICLOUD_DOCKER_CONFIG_DIR", "/config"), ".data")
# => "/config/.data"  (ABSOLUTE path)

def init_cache(config: dict) -> str:
    root_destination_path = prepare_root_destination(config=config)   # e.g. "/icloud"
    cache_file_path = os.path.join(root_destination_path, CACHE_FILE_NAME)
    # => "/config/.data"  — the root destination is a no-op:
    # os.path.join discards the left side when the right side is absolute.
```

The `root_destination_path` argument is dead compute. Verified:

```bash
$ python -c "import os; print(os.path.join('/icloud', '/config/.data'))"
/config/.data
```

### History (why this is worse than cosmetic)

- Original implementation (`git show 7220e1404:src/usage.py`): `CACHE_FILE_NAME =
  ".data"` was **relative** → cache lived at `<root destination>/.data` (e.g.
  `/icloud/.data`).
- Refactor commit `091fa55` changed it to the absolute `/config/.data` without
  updating `init_cache`.

Practical consequence for users upgrading across that boundary: their old
`/icloud/.data` cache is orphaned, the new version registers with `previousId=None`
(a **fresh** installation, not an upgrade), so server-side "new installations" were
inflated once per migrating user. Any future upgrade flow (A) depends on this cache,
so the location must be deliberate.

### Suggested fix

- Make `CACHE_FILE_NAME` relative (`".data"`) again and let `init_cache` place it
  under the root destination — as the function signature and docstring already promise.
  Audit `tests/conftest.py:35-90` (`src.usage.CACHE_FILE_NAME = os.path.join(tmpdir,
  ".data")`) which will need corresponding updates.
- Or, if `/config/.data` is the deliberate choice: drop the dead
  `root_destination_path` parameter from `init_cache`, stop calling
  `prepare_root_destination` (which also creates the root directory for nothing),
  and document the location in `USAGE.md`.

### Verification

- `python3 -c "import os; print(os.path.join(os.getcwd(), '/config/.data'))"`
- Trace `alive()` → `init_cache()` → `load_cache()` and confirm the file created is
  at `/config/.data` regardless of `app.root`.

---

## C. `post_with_retry` swallows 5xx/429 responses (no diagnostics)

**Signal:** `src/usage.py:150-206`.

### What

- Non-retryable 4xx (except 429) returns the response — good.
- 5xx and 429: retried with exponential back-off `max_retries` times; on the final
  failure the function exits the loop and **returns `None`** in place of the last
  `requests.Response`.
- Also: `last_exception` is only set on `requests.ConnectionError`/`Timeout`; when all
  retries fail with 5xx, the "All retry attempts failed" error at
  `src/usage.py:204-206` even logs nothing — so `post_new_installation` /
  `post_new_heartbeat` log "no response" / "no response", making a 500 backend
  indistinguishable from the container holding no networking.

### Suggested fix

- Return the last `response` object after exhausting retries (or a small
  `RetryError` exception carrying the last status), and emit the
  `LOGGER.error("All retry attempts failed: HTTP X")` for both the exception and
  the status-code paths.
- Update `test_post_with_retry_*` tests to assert the returned object's status.

### Verification

- `tests/test_usage.py` `test_post_with_retry_server_errors_5xx` currently asserts
  `result is None`.

---

## E. ~~APP_NAME differs from the published image name~~ — by design

`APP_NAME = "icloud-docker"` matches the repository name. The Docker image
name (`mandarons/icloud-drive`) is a separate concern. No change needed.

**Signal:** `src/usage.py:25` — `APP_NAME = "icloud-docker"` while the container
image is `mandarons/icloud-drive` (Dockerfile, workflows).

### What

`NEW_INSTALLATION_DATA["appName"]` is sent as `"icloud-docker"`. On the server
(wapar-api.mandarons.com) this may be a distinct application from whatever the rest
of the ecosystem uses. If the server keys signs/apps by `appName`, this splits the
metrics into two buckets.

### Fix

- Align `APP_NAME` with the image/project name (`icloud-drive` / `mandarons/icloud-drive`).
- Confirm with the server-side schema which value it expects; update
  `tests/data/__init__.py` mock if necessary.

---

## F. Minor / hygiene items

1. **`alive()` returns `False` on throttled heartbeat** (`src/usage.py:422`).
   Semantically "not required" is not "failure". No caller checks it today, but this
   is brittle for the future and contradicts the docstring ("True if usage tracking
   was successful"). Consider returning `True`, or a tri-state.
2. **`datetime.utcnow()` deprecation** (`src/usage.py:334` + several
   `tests/test_usage.py` call sites). Deprecated in Python 3.12; use
   `datetime.now(datetime.timezone.UTC)`.
3. **Zero-microsecond heartbeat timestamp destroys the cache.** `str(datetime(...))`
   omits the microsecond fraction when it's exactly `0` (e.g. `"2026-08-07 12:34:56"`).
   That string fails both `validate_cache_data` (`src/usage.py:71-75`,
   `strptime(..., "%Y-%m-%d %H:%M:%S.%f")`) and `heartbeat`'s `strptime`
   (`src/usage.py:353`) — the former **wipes the cache** and re-registers the install.
   Probability ~1 per million saves; still add a `%f`-optional parser or store an
   explicit format.
4. **`alive()` with `config=None` creates an orphan directory.** When the config
   file is missing, `sync()` calls `alive(config=None)` (`src/sync.py:979`); the
   `usage_tracking` reads succeed via defaults, `prepare_root_destination(None)`
   then `ensure_directory_exists("./icloud")` — creating an empty `./icloud` in the
   working directory. Guard `alive` against `config is None`.
5. **`tests/__init__.py:37-40` uses `is` vs `==` when comparing the endpoint URL in
   the mocked `requests.post`.** Works today because the default arg flows through
   the module global; breaks if any test ever passes an equivalent-but-distinct
   string. Change to `==`.

---

## Testing & Docs to update alongside

- **Tests:** add a multi-day heartbeat integration test (see A); update the retry
  tests per fixing C; cover the zero-microsecond timestamp (F3) and `alive(None)`
  (F4). Keep 100% coverage in `docs/standards/testing.md` /
  `tests/AGENTS.md` requirements.
- **Docs (per AGENTS.md "Documentation Maintenance"):**
  - `USAGE.md` — reflect whatever the final heartbeat/installation data contract is.
  - `docs/systems/configuration.md` / `README.md` — the `usage_tracking.enabled`
    sample + `APP_VERSION` env doc (README.md:787) if behavior or defaults change.
  - `docs/systems/container.md` — cache location if it moves.
- **The sync-loop data contract** (schema of the `data` payload in `heartbeat()`)
  should be confirmed against the wapar-apiserver endpoint before reworking A.