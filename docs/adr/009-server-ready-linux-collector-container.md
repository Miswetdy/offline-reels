# ADR 009: Separate Linux Collector runtime image

## Status

Accepted — Stage 3C.2.

## Context

The Collector needs Chromium, Playwright, yt-dlp and media tools, while the
FastAPI runtime must remain small and must not own browser state or external
Instagram credentials.

## Decision

Use a separate `collector` Docker target in `apps/api/Dockerfile`. It installs
the pinned optional Collector dependencies and matching Playwright Chromium in
a shared, non-root-readable runtime path. The target has a `tini` entrypoint,
uses a dedicated non-root user, and only accepts an explicit fixture command
in Stage 3C.2. Profile and workspace are independent volumes.

For server reproducibility, validate the composition using an internal Docker
network and real PostgreSQL/MinIO. The fixture flow uses synthetic candidates
and local ffmpeg MP4 generation, blocking future fixture Playwright HTTP(S)
traffic. No Windows browser profile or Instagram state is included in a build
context or image layer.

## Consequences

The API target is not burdened by browser tooling. The Collector image is
larger by design and is the only runtime suitable for eventual Stage 4 live
work. Stage 3C.2 proves packaging and transactional synthetic flow, not a live
Instagram login or collection run.
