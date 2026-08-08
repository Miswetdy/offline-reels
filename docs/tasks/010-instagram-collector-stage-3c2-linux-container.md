# TASK-010: Stage 3C.2 server-ready Linux Collector

Stage 3C.2 packages the Collector as a separate production-compatible Linux
image. The API target remains lightweight: it contains neither Chromium,
Playwright nor yt-dlp. The Collector target installs the pinned `collector`
extra, the matching Playwright Chromium revision, system `ffmpeg`/`ffprobe`
and `tini`; it runs as UID/GID 10001.

The entrypoint refuses an implicit or live command. Only explicit `fixture`
execution is available in this stage. Profile and workspace are absolute,
disjoint, outside the checkout/root/home, and use separate mounts. A profile
lock is account-scoped. Each run owns one workspace attempt directory, which
is removed after success, failure or cancellation; the persistent profile is
never cleaned by normal shutdown.

`run_instagram_collector_container_fixture` uses real `CollectorEngine`,
`CollectorPersistence`, PostgreSQL, MinIO storage and ffprobe. Its feed and
downloader are synthetic; MP4 creation is local ffmpeg only. It has no
Playwright page, CookieJar or yt-dlp invocation. If a fixture ever obtains a
Playwright context, `FixturePlaywrightNetworkGuard` aborts all HTTP(S)
requests. The Compose network is `internal: true`, so PostgreSQL and MinIO are
the only runtime network peers.

The disposable Compose project is exactly `offline-reels-stage3c2-fixture`.
It does not publish ports and does not start API, web, Caddy, Redis or Funnel.
Its cleanup script first resolves the exact project targets and removes only
that project's containers, network and volumes.

Not implemented: live Instagram operation in container, Windows-profile
migration, mobile authorization, remote browser UI, scheduler and normalizer
worker. These remain Stage 4 work.

## Acceptance result

The disposable PowerShell acceptance completed successfully: initial run made
three `source_ready` Reels and pending normalization jobs with no `videos`
rows, the repeat was an idempotent no-op, and the cancellation scenario kept
the first durable source while recording `CANCELLED_BY_USER`. Exact Stage 3C.2
containers, network and volumes were removed afterwards; the preserved
`offline-reels-collector-smoke` PostgreSQL and MinIO services remained healthy.
