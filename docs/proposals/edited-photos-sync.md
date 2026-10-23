# Edited photos sync — consuming icloudpy's `full` version

**Status:** draft proposal. **No implementation yet.**
**Tracks:** [#292](https://github.com/mandarons/icloud-docker/issues/292) (feature) and
[#572](https://github.com/mandarons/icloud-docker/issues/572) (the `preserve_originals_as_bak`
bug that work item 5 fixes)
**Dependency:** [mandarons/icloudpy#206](https://github.com/mandarons/icloudpy/pull/206) — **merged
to `main` on 2026-10-23** (`d14f283`), so the edited rendition is in git but **not in a release**
(latest is 0.11.0). The dependency pin can move once a release containing it ships.

## Problem

iCloud Photos stores two different things that are easy to confuse:

| Version | CloudKit field | Record | What it is |
|---|---|---|---|
| `original` | `resOriginalRes` | `CPLMaster` | the untouched original |
| `original_alt` | `resOriginalAltRes` | `CPLMaster` | the **alternate** rendition (RAW/JPEG pair) — *not* an edit |
| `full` | `resJPEGFullRes` | **`CPLAsset`** | Apple's rendered **edit** (crop, filters, portraits, markups) |
| `medium` / `thumb` | `resJPEGMed` / `resJPEGThumb` | `CPLAsset` first, else `CPLMaster` | renditions; on an edited asset these describe the edit |

icloud-docker 2.2.0 still pins icloudpy 0.11.0, whose `PhotoAsset.versions` reads only the
`CPLMaster` record — the fix is on icloudpy `main` but not in a release. Edited renditions
therefore never appear: configuring
`photos.filters.file_sizes: [full]` makes `collect_download_task` skip **every** photo with
`File size full not found on server`, which is the empty-folder symptom on #292.

Configuring `original_alt` instead (the workaround suggested in the issue) downloads the
alternate/RAW rendition, which exists only for RAW-pair assets — so it works for a few users and
leaves everyone else with an empty tree.

The same misunderstanding exists in our own docs and code: `photos.preserve_originals_as_bak`
treats `original_alt` as "the edited version" (`src/photo_path_utils.py:84`,
`src/config_parser.py:1024`, README/config.yaml comments). For RAW shooters that hides the
untouched JPEG as `*.original.bak` without writing any edit at all. That defect is filed as
[#572](https://github.com/mandarons/icloud-docker/issues/572), and work item 5 below is its fix.

## What icloudpy#206 provides

`PhotoAsset.versions` reads each version from the `CPLAsset` record first and falls back to
`CPLMaster` per version. On an edited asset the versions become
`['full', 'medium', 'original', 'thumb']`, where `full` carries `size`, `url`, `type`
(`public.jpeg`), `width`, `height` and the asset's filename. Unedited photos are unchanged: they
have no `full` key. This is the same mechanism icloudpd uses (`--size adjusted`, PRs #855/#858).

The asset-first lookup applies to **every** version key, not only `full`: an edited asset's
`medium`, `thumb` and Live Photo `live_video_*` renditions also come from the asset record when it
carries them, so they describe the edit too. The reviewer's read-only comparison against a real
library ([review 5623576794](https://github.com/mandarons/icloudpy/pull/206#pullrequestreview-5623576794))
confirms it: unedited assets are byte-identical to before, edited photos and Live Photos download
the actual edit as `full`, and edited videos expose the edited video as the video `full`
(`resVidFullRes`). Existing icloud-docker setups that sync `medium`, `thumb` or
`live_video_*` will therefore start writing edit renditions under unchanged filenames — a
consumer-visible change that needs a CHANGELOG line in both repos.

## Work items

1. **Dependency** — bump `requirements.txt` to the icloudpy release that contains #206 (merged to
   `main`, unreleased as of 2026-10-23). No other pin changes expected (asset-first lookup is
   additive).
2. **Config vocabulary** — accept `adjusted` (canonical: `full`) and `alternative`
   (canonical: `original_alt`) in `photos.filters.file_sizes`, normalizing at parse time in
   `validate_file_sizes` (`src/config_parser.py:929`). Document both spellings; today `full` is
   accepted but undocumented.
3. **Fallback for unedited photos** — `photos.filters.fallback_to_original` (default `false`,
   backward compatible). When true and a requested size is absent for an asset, download
   `original` instead of skipping, except when `original` is already in the list (no duplicate).
   Touches the skip guard in `photo_download_manager.collect_download_task`
   (`src/photo_download_manager.py:198`) and the dry-run guard in `migration_check.py:89`.
   With `file_sizes: [adjusted]` + fallback this implements "edited, or original if never
   edited", which is how icloudpd behaves by default.
4. **Naming and extensions**
   - `get_photo_name_and_extension` (`src/photo_path_utils.py:33`) derives the extension from the
     asset filename, so a `full` JPEG would be written into a `.HEIC` name. Map the extension
     from the version's MIME type for `full`, as already done for `original_alt`.
   - `simple` mode (`filename_format: simple`): when `original` and `full` resolve to the same
     name and extension, suffix the edit (`-adjusted`) so one cannot overwrite the other.
     `metadata` mode is already unique (`name__full__id.ext`).
   - `file_format` templates: `_PRIMARY_VERSIONS` (`src/photo_path_utils.py:125`) treats `full`
     as primary, so `${photo.variant}` / `${photo.variant_suffix}` are empty for it. Decide
     whether `full` becomes a variant when `original` is also requested, or document
     `${photo.file_size}` for template users.
5. **`preserve_originals_as_bak` (#572)** — retarget the "is edited" predicate from `original_alt`
   to `full`, and only hide the original when both `original` and the edit are requested. Four code
   sites, and the third is the one that makes the toggle work at all:
   - `src/photo_path_utils.py:84-93` — `_photo_has_alt_version()` becomes "has an edit"
     (`"full" in photo.versions`); its docstring still calls `original_alt` "edited".
   - `src/photo_path_utils.py:241` — the suffix site; logic unchanged, it is the only caller.
   - `src/sync_photos.py:409-417` — **the activation gate**, today
     `preserve_originals_as_bak and "original_alt" in file_sizes`. It must key on `full`, and the
     "at least one visible file" invariant re-checked for `[original, full]`; otherwise the option
     silently never activates on the new size list. The comment block at `sync_photos.py:402-417`
     ("`original_alt` — the visible 'current view' of an edited photo") is wrong and goes with it.
   - `src/config_parser.py:1024-1043` — the getter's docstring, not a check: its two-file example
     (`original` + `original_alt`) has to be rewritten for `full`.
   This **drops** RAW-pair hiding (open question 8). Existing `*.original.bak` copies are untracked
   and only swept when the asset leaves iCloud (`sync_photos.py:410-411`), so after the change the
   original reappears under its normal name and the old sidecar lingers — the migration note covers
   it.
6. **Expired download URLs (HTTP 410)** — `_refresh_photo_download_url`
   (`src/photo_file_utils.py:171`) re-fetches only the master record. Edited URLs live on the
   asset record, so after a refresh they would still be stale and the download would loop on
   410. Either refresh both records in docker (lookup by asset `recordName`) or add a public
   refresh method to icloudpy and use it (preferred; avoids private-attribute access).
7. **Docs** — two tranches:
   - **Immediate, no dependency (#572 item 1):** correct the `preserve_originals_as_bak` wording in
     `config.yaml:173-178`, `README.md:249-253`, `docs/systems/photos-sync.md:14-15` and the
     docstrings. It hides `original` when an alternate representation exists, not when a photo was
     edited. This needs no icloudpy release and should not wait for one — it can ship as its own
     small PR.
   - **With the implementation:** `docs/systems/photos-sync.md` size table (`full`/`adjusted`,
     `original_alt` as "RAW/alternate"), `config.yaml` + README `file_sizes` example, CHANGELOG
     entries for the new option and the `medium`/`thumb`/`live_video_*` content change, and the
     #292 answer correction (our comment there recommends `original_alt`; it should point at
     `full`/`adjusted` once released).
8. **Migration guidance** — recommend adding the edited size first and verifying, then removing
   `original`; warn that with `remove_obsolete: true` the old originals become cleanup
   candidates, that switching sizes changes on-disk names, and that the first sync after the
   icloudpy bump re-downloads edited `medium`/`thumb`/`live_video_*` files in place. For
   `preserve_originals_as_bak`, warn that RAW-pair users stop getting `.bak` files and that
   existing `*.original.bak` copies are untracked, so they persist as hidden duplicates until the
   asset is deleted or they are removed by hand.

## Behaviour matrix (target)

| `file_sizes` | fallback | Edited photo | Unedited photo |
|---|---|---|---|
| `[original]` (default) | — | original only | original |
| `[adjusted]` | false | edit (`full`) | skipped (current behaviour) |
| `[adjusted]` | true | edit | original |
| `[original, adjusted]` | — | original + edit (`-adjusted` / `__full__`) | original |
| `[original_alt]` | — | alternate rendition (not an edit) | skipped |

With `preserve_originals_as_bak: true`, an `[original, adjusted]` row hides the `original` copy as
`*.original.bak`; unedited photos never get the suffix.

## Risks and limits

- The edit is Apple's **JPEG render**: no HEIC container, no HDR gain map, no depth/portrait
  metadata, and no way to retrieve an edited RAW. Document this before users switch.
- Edited **movies** expose the edit as the video `full` version, and edited **Live Photos** expose
  it through the still image's `full` plus the asset-record `live_video_*` variants. There is no
  separate "edited Live Photo video only" size (icloudpd has none either), so a `file_sizes` list
  containing `live_video_*` downloads the paired video alongside the still.
- For edited assets the `medium`, `thumb` and `live_video_*` versions now come from the asset
  record (they show the edit). `check_photo_exists` compares on-disk size with the version size
  (`src/photo_file_utils.py:287-298`), so existing copies are re-downloaded and overwritten under
  unchanged names — correct data, but a visible change for previews and any downstream index.
- `preserve_originals_as_bak` stops hiding RAW-pair alternates (#572). That is the intended fix,
  not a regression, but it changes existing users' output and belongs in the CHANGELOG and the
  option's docs.
- Size changes churn filenames and interact with obsolete-file cleanup; migration guidance is
  required, not optional.

## Test plan

- Unit: alias normalization in `validate_file_sizes`; extension mapping and collision suffix for
  `full`; fallback on/off incl. no double download when `original` is also requested; refresh
  covering the asset record.
- `preserve_originals_as_bak` (#572): new tests with `full`, **and** rewrite the existing
  wrong-premise ones in `tests/test_preserve_originals_as_bak.py` — `_photo_with_alt` (line 20) is
  a RAW pair mislabelled "edited photo", the `test_edited_photo_*` names assert the wrong
  semantics, and the gate tests (lines 195-216) assert `original_alt` activates the toggle. Add:
  a RAW pair with `original_alt` does **not** get the suffix; gate on for `[original, full]`; gate
  off when `full` is absent even if `original_alt` is present.
- Integration: a fake photo with `versions` containing `full` through
  `collect_download_task` → naming → cleanup tracking; dry-run output.
- Docs: sample config parses; full pytest suite stays at 100% coverage; ruff/yamllint clean.

## Open questions

1. Public spelling: document `adjusted` (icloudpd parity) with `full` canonical, or expose only
   `full`?
2. Should `fallback_to_original` default to true for `adjusted` only, or stay opt-in for every
   size?
3. Fix `preserve_originals_as_bak` in the same release (behaviour change) or separately?
4. Refresh API: public `PhotoAsset.refresh()` in icloudpy vs a docker-side lookup of both records?
5. Target release: 2.3.0, after the icloudpy release ships.
6. Is the edited `medium`/`thumb`/`live_video_*` content change a breaking note in the CHANGELOG, or
   just a line under Changed?
7. `preserve_originals_as_bak`: rename/deprecate it now that it means "hide the original when an
   edit exists" and no longer covers RAW pairs, or keep the name and document the narrower
   meaning? #572 suggests considering a rename.
8. Is dropping RAW-pair hiding acceptable, or does that case need its own option? Existing users
   enabled this toggle for exactly that behaviour.
