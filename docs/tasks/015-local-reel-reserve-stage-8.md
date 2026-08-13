# Stage 8 — local Reel reserve

The PWA has one browser-global foreground controller. It reconciles the
existing IndexedDB/Cache Storage library, applies device-local settings, reads
the full paginated ready catalog, and passes only missing videos to the existing
one-at-a-time queue. When short, it requests one bounded management collection
run, waits with deadline/backoff for Collector and normalizer, then refreshes.

Defaults: desired `20`, low watermark `8`, threshold `80%`. The controller runs
when active and wakes on foreground, `pageshow`, and `online`; it does not claim
closed-iOS background execution. Cancel preserves completed media.

## Disposable fixture

`deploy/docker-compose.stage8-fixture.yml` is independent from `compose.yaml`.
It is started only through `scripts/start-stage8-fixture.ps1`, which generates a
unique Compose project name, random loopback HTTPS port, process-only fixture
secrets and project-scoped `stage8_postgres`/`stage8_minio` volumes. It contains
synthetic PostgreSQL, MinIO, API, web, Collector and normalizer services. The
fixture creates no Instagram session/profile and never contacts Instagram. Its
Collector turns a bounded management run into source-ready records and its safe
synthetic normalizer generates a tiny H.264/yuv420p MP4 before publishing a
ready, cursor-paginated catalog row.

`scripts/test-stage8-fixture-e2e.ps1` runs the same fixture in a Chromium
iPhone 13 viewport. It verifies one bounded initial run, ten completed
IndexedDB/Cache Storage records, reload deduplication, offline `/offline`,
quota pause and online/foreground resume, cancellation preserving completed
media, the satisfied no-op, safe UI redaction, and `no-store` on management
and reserve responses. Its certificate-ignore launch flag is limited to the
ephemeral Caddy internal certificate used by the disposable fixture.

## Manual iPhone acceptance

The isolated fixture was manually accepted from Safari and an iOS Home-Screen
installation via a temporary Funnel. The two browser contexts correctly have
separate IndexedDB/Cache Storage libraries, so Home Screen filled its own
three-Reel reserve from the already-ready catalog without requesting another
collection run. Offline playback, reload no-op, network restoration,
pause/resume, quota stop/resume, safe UI redaction and bounded cancellation
were observed. Cancellation now also sends an idempotent cancel command only
for the collection run created by that reserve cycle; PostgreSQL confirmed its
terminal `cancelled` state and no active runs. A fixture-only build flag offers
quota simulation without modifying device quota, Cache Storage, or production
builds. All disposable resources and Funnel were removed after the audit.
