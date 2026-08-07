# TASK-006: Instagram Collector fixture engine

## Goal

Prove the production Collector ordering against deterministic local fixtures,
without Instagram, a browser, cookies, network access, MinIO or a worker.

## Implemented

- Typed ports for feed control, temporary download, validation and source
  storage.
- Canonical Instagram Reel candidate validation owned by the production API.
- Sequential engine using stage 1 models and transitions.
- One transaction for source metadata, pending normalization job, ordered run
  item and run counters.
- Fixture CLI with bounded targets and allowlisted success/failure scenarios.
- Best-effort compensation of only a newly published fixture object after a
  database failure.

## Invariants

- The current Reel is paused before a download begins.
- Feed advance is prohibited until the current result is durably committed or
  recorded as already available.
- `confirmed_advances` increases only after the feed confirms a new valid
  shortcode; a physical advance that times out, repeats or returns an invalid
  candidate is not counted.
- A failing current Reel ends the run without an advance.
- The final committed Reel does not cause an extra advance.
- The Collector owns every temporary source path and performs idempotent
  cleanup after both success and failure.

## Not implemented

No production browser/session adapter, yt-dlp adapter, ffprobe adapter, MinIO
adapter, reconciliation worker, scheduler, API route or frontend UI is part of
this task.
