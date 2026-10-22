# Edited photos sync — consuming icloudpy's `full` version

**Status:** draft proposal. **No implementation yet.**
**Tracks:** [#292](https://github.com/mandarons/icloud-docker/issues/292)
**Blocked by:** [mandarons/icloudpy#206](https://github.com/mandarons/icloudpy/pull/206) — exposes
the edited rendition; needs a released icloudpy containing it before the dependency pin can move.

## Problem

iCloud Photos stores two different things that are easy to confuse:

| Version | CloudKit field | Record | What it is |
|---|---|---|---|
| `original` | `resOriginalRes` | `CPLMaster` | the untouched original |
| `original_alt` | `resOriginalAltRes` | `CPLMaster` | the **alternate** rendition (RAW/JPEG pair) — *not* an edit |
| `full` | `resJPEGFullRes` | **`CPLAsset`** | Apple's rendered **edit** (crop, filters, portraits, markups) |
| `medium` / `thumb` | `resJPEGMed` / `resJPEGThumb` | master (edited thumb on asset) | renditions |

icloud-docker 2.2.0 still pins icloudpy 0.11.0, whose `PhotoAsset.versions` reads only the
`CPLMaster` record. Edited renditions therefore never appear: configuring
`photos.filters.file_sizes: [full]` makes `collect_download_task` skip **every** photo with
`File size full not found on server`, which is the empty-folder symptom on #292.

Configuring `original_alt` instead (the workaround suggested in the issue) downloads the
alternate/RAW rendition, which exists only for RAW-pair assets — so it works for a few users and
leaves everyone else with an empty tree.

The same misunderstanding exists in our own docs and code: `photos.preserve_originals_as_bak`
treats `original_alt` as "the edited version" (`src/photo_path_utils.py:84`,
`src/config_parser.py:1024`, README/config.yaml comments). For RAW shooters that hides the
untouched JPEG as `*.original.bak` without writing any edit at all.

## What icloudpy#206 provides

`PhotoAsset.versions` reads each version from the `CPLAsset` record first and falls back to
`CPLMaster` per version. On an edited asset the versions become
`['full', 'medium', 'original', 'thumb']`, where `full` carries `size`, `url`, `type`
(`public.jpeg`), `width`, `height` and the asset's filename. Unedited photos are unchanged: they
have no `full` key. This is the same mechanism icloudpd uses (`--size adjusted`, PRs #855/#858).

## Work items

1. **Dependency** — bump `requirements.txt` to the icloudpy release that contains #206. No other
   pin changes expected (asset-first lookup is additive).
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
5. **`preserve_originals_as_bak`** — rebase the "is edited" check from `original_alt` to `full`
   (`src/photo_path_utils.py:84`, `src/config_parser.py:1024`) and only apply it when both
   `original` and the edit are requested. This is a user-visible behaviour change for RAW
   shooters; call it out in the CHANGELOG.
6. **Expired download URLs (HTTP 410)** — `_refresh_photo_download_url`
   (`src/photo_file_utils.py:171`) re-fetches only the master record. Edited URLs live on the
   asset record, so after a refresh they would still be stale and the download would loop on
   410. Either refresh both records in docker (lookup by asset `recordName`) or add a public
   refresh method to icloudpy and use it (preferred; avoids private-attribute access).
7. **Docs** — `docs/systems/photos-sync.md` (size table: add `full`/`adjusted`, keep
   `original_alt` as "RAW/alternate"), `config.yaml` + README (`file_sizes` example for edits;
   corrected `preserve_originals_as_bak` wording), CHANGELOG entry.
8. **Migration guidance** — recommend adding the edited size first and verifying, then removing
   `original`; warn that with `remove_obsolete: true` the old originals become cleanup
   candidates, and that switching sizes changes on-disk names.

## Behaviour matrix (target)

| `file_sizes` | fallback | Edited photo | Unedited photo |
|---|---|---|---|
| `[original]` (default) | — | original only | original |
| `[adjusted]` | false | edit (`full`) | skipped (current behaviour) |
| `[adjusted]` | true | edit | original |
| `[original, adjusted]` | — | original + edit (`-adjusted` / `__full__`) | original |
| `[original_alt]` | — | alternate rendition (not an edit) | skipped |

## Risks and limits

- The edit is Apple's **JPEG render**: no HEIC container, no HDR gain map, no depth/portrait
  metadata, and no way to retrieve an edited RAW. Document this before users switch.
- Edited **Live Photo video** is not exposed by any field icloudpd uses either; out of scope.
- For edited photos the `thumb` version now comes from the asset record (it shows the edit);
  harmless for downloads, but a visible change in previews.
- Size changes churn filenames and interact with obsolete-file cleanup; migration guidance is
  required, not optional.

## Test plan

- Unit: alias normalization in `validate_file_sizes`; extension mapping and collision suffix for
  `full`; fallback on/off incl. no double download when `original` is also requested;
  `preserve_originals_as_bak` with `full`; refresh covering the asset record.
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
