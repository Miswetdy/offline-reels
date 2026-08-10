# ADR 011: Durable Instagram normalization worker

## Status

Accepted.

## Decision

Normalization is an explicit browser-free worker, never a FastAPI startup side
effect. It claims jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`, writes an
opaque UUID worker id and bounded lease, and uses the existing media normalizer.
Only H.264/yuv420p/AAC MP4 output can be published.

Each attempt uploads to `instagram-normalizer-staging/<job>/<attempt>/`, which
is never API-visible. Validated output is copied to deterministic
`videos/<sha256>.mp4`; an existing final key is reused only if size, SHA-256 and
media invariants match. PostgreSQL atomically upserts the video, links the Reel,
marks it ready and completes the job. A new unreferenced final object is
compensated after DB failure; existing final objects are never removed.

Source cleanup begins only after that durable commit. A Reel stays
cleanup-pending until source deletion succeeds or is already absent. The
reconciler cleans stale attempt staging and retries ready-source cleanup without
deleting durable source/final media. Failed jobs remain history; retries create
new pending jobs and the Reel has at most three attempts.
