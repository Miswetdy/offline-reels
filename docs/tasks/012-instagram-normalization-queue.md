# TASK-012: Instagram normalization queue (Stage 5)

## Scope

Implement `source_ready -> normalizing -> ready` as a separate PostgreSQL/MinIO
worker. It is browser-free and never starts with FastAPI.

## Durable rules

- `SKIP LOCKED` claim, opaque worker id, bounded lease, one default worker;
- source SHA/size, ffprobe and full decode before final publication;
- attempt-owned staging is never API-visible; canonical final key is SHA-256 based;
- ready/video/job DB commit occurs before source deletion;
- cleanup-pending is reconciled independently; retries stop after three attempts;
- only allowlisted ASCII reason codes are persisted or emitted.

## Preserved Collector smoke manual acceptance

Never run the saved ten Reels without exact `y` confirmation. First run the
read-only `./scripts/run-stage5-normalizer-preflight.ps1` helper and wait for
its aggregate JSON. It reads existing local container configuration only into
the process environment and never prints it. Then, one command at a time: build
the worker image; warn about transformation; obtain confirmation; execute
`./scripts/run-stage5-normalizer-smoke.ps1 -Migrate` once, then
`./scripts/run-stage5-normalizer-smoke.ps1 -Limit 10`; verify read-only state
with `./scripts/run-stage5-normalizer-smoke.ps1 -Verify`;
verify API catalog and one ffprobe/full-decode MP4 with the corresponding
`-Catalog` and `-Media` modes;
decode one final MP4; and run the worker again expecting no work. Retry and
cancellation belong only to disposable infrastructure. Cleanup must not remove
committed smoke videos.

## Manual smoke acceptance

Accepted on the preserved Collector smoke after migration `0006`: preflight
reported 10 source-ready Reels, 10 pending jobs, 10 source objects and 0
videos. The bounded run completed all ten on attempt one via transcode. Final
verification reported 10 ready Reels, 10 completed jobs, 10 `videos`, 10 final
objects, no active/failed jobs, no staging, no source objects and no cleanup
pending. The existing FastAPI catalog returned HTTP 200 with 10 items; a final
object passed H.264/yuv420p/AAC, positive-duration and full-decode checks. A
second bounded worker run was a no-op. Disposable automated retry/cancellation
tests remained separate; the worker image was removed after manual acceptance.
