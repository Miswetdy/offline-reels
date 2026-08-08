# TASK-008: Instagram Collector Stage 3B bounded operator run

Stage 3B adds an explicit Windows-hosted operator command for exactly three
Reels. It is not imported by FastAPI and does not start by itself.

The operator manually authenticates in headed Chromium, opens personal Reels,
centres one Reel, then confirms the run with exact `y`. Every candidate is
paused, receives a fresh minimal in-memory `sessionid`/`csrftoken` CookieJar,
is downloaded session-first, ffprobe-validated, published under
`instagram-sources/`, and committed in PostgreSQL before one controlled scroll.
Each of the first two durable positions may use one bounded retry wheel if the
first transition confirmation times out; a newly observed shortcode gets a
short stabilization window before that retry. The final third Reel has no
advance. Normalization remains pending and `videos`
is not changed.

Before every wheel the selected Reels page recalculates the central visible
video's clipped viewport centre and moves the mouse to that in-memory point.
It never clicks, focuses, types, or serializes coordinates; unavailable or
invalid targets stop safely before a wheel is sent.

The optional smoke infrastructure uses project
`offline-reels-collector-smoke`, loopback-only PostgreSQL/MinIO ports and its
own volumes. Its default ports are PostgreSQL `55432` and MinIO `59100`; both
have environment overrides and startup rejects occupied or excluded ports
before Compose starts. It is separate from production/dev Compose resources. The next
stage is 3C: an isolated Linux/container Collector service and bounded 10-Reel
live verification. Phone account connection, normalization worker, Collector
API and frontend are not implemented here.

Live execution is deliberately manual and requires separate authorization. One
bounded test-account run has now completed successfully: three session-first
sources were validated, published and committed; two targeted wheel transitions
were confirmed; the read-only verifier confirmed the exact source-object delta
and that `videos` was unchanged. Normalization was not run, mobile login is not
implemented, and the smoke state is deliberately retained for Stage 3C's
separate Linux/container ten-Reel test.

The host operator and verifier use only the smoke application MinIO key. Root
credentials stay inside `minio-bootstrap`, which idempotently installs a
bucket-scoped policy. Startup waits for PostgreSQL and MinIO health, successful
bootstrap/migration, and Alembic head before reporting readiness.

Before the run, the operator result captures safe fingerprints of `videos.id`
and the complete `instagram-sources/` object baseline. Verification consumes
that exact result file, checks the exact object-key delta plus streaming hashes,
workspace cleanup, and the structured per-position event order. It never
creates a replacement baseline after collection. A failed verification makes
the command fail without rolling back already durable sources.

## Operator commands

Prepare the pinned optional adapters and local Chromium once:

```powershell
uv --directory apps/api sync --extra collector --frozen
$env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path .playwright-browsers).Path
uv --directory apps/api run playwright install chromium
```

Prepare the preserved loopback-only smoke PostgreSQL/MinIO project:

```powershell
.\scripts\start-collector-smoke.ps1
```

Run the manually authorized bounded collection:

```powershell
.\scripts\run-collector-stage3b.ps1
```

Verify one result read-only and, only after all Stage 3B work is complete, remove
the exact smoke project and its volumes:

```powershell
.\scripts\verify-collector-stage3b.ps1 -ResultFile <stage-3b-result-json>
.\scripts\cleanup-collector-smoke.ps1
```

The live command never accepts credentials from PowerShell and never prints
credentials, cookies, raw yt-dlp output, media URLs or signed object URLs.

Before readiness, the feed scans only open `www.instagram.com` pages in the
persistent context. A page with a valid central Reel wins over login/challenge
or other pages, so an Instagram redirect that opens a new tab does not bind the
run to the initial tab. Identity stays tied to that central video: direct and
bounded container anchors are considered before a strict current-page pathname
fallback. A pre-confirmation failure records only aggregate page/video counts,
strategy and a safe reason code; it creates no collection run or source object.
