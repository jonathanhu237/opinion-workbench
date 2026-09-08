# Media exit boundary

The retired media implementation remains in the tree only where it is needed
for migration, historical fixtures, or compatibility with old injected test
workers. It is not part of the live product assembly.

## Live path checks

- `backend/src/longtian_api/api/router.py` no longer imports or includes the
  media-cache router.
- `backend/src/longtian_api/main.py` no longer creates `MediaCache`,
  `MediaSpool`, or `MediaRetention`, stores `app.state.media_cache`, or starts
  the retention loop.
- `frontend/src/routes/settings.tsx` contains only AI settings. The detail and
  evidence views no longer mount local media readers. The old
  `/settings/media` and `/media-settings` addresses only redirect to
  `/settings` without a media hash.
- `ContentEnrichmentService` is composed without a spool and passes
  `text_only=True` to production workers. `WeiboEnricher` also forces this
  value at its public entry point, so the old parser media-acquisition and
  transfer branches return through text-only projection before any media
  transfer call.
- v38 migration is the only live media-cache service import. It first removes
  provably project-owned files, then drops the four cache tables. A filesystem
  deletion I/O error keeps the database at v37 with its ownership rows so the
  next startup can retry; unknown or mixed entries are preserved and do not
  block the schema upgrade.

## Retained historical modules

These files are intentionally unmounted and are not production entry points:

- `frontend/src/routes/media-settings.tsx`
- `frontend/src/routes/original-media-cache.tsx`
- `frontend/src/lib/api/media-cache.ts`
- `backend/src/longtian_api/api/v1/media_cache.py`
- `backend/src/longtian_api/services/media_cache.py`
- `backend/src/longtian_api/services/media_retention.py`
- old media migration definitions and media branches in the Weibo/gallery
  compatibility code

`backend/src/longtian_api/services/media_cleanup.py` and
`backend/src/longtian_api/migrations/media_exit_v38.py` are retained as the
one-way upgrade and safe cleanup path, rather than as a runtime cache.
