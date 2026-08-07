# ADR 007: Instagram Collector pipeline and durable state foundation

## Status

Accepted. This ADR defines the production data and domain boundary only; it
does not introduce a browser worker, downloader, scheduler, API endpoint, or
new deployment service.

## Context

The official Instagram API does not provide a personal recommended Reels feed.
The separate, non-production research spike confirmed a constrained path with a
test account: A2/A3/A4 established a persistent browser session and bounded
feed observation, C1 established source-commit-before-scroll sequencing, C2
confirmed a session-first download, and N1 confirmed VP9 to
H.264/yuv420p/AAC normalization. That spike remains isolated; its code, profile
and session state are not copied into this repository.

The earlier B1 blob/network-response observer was rejected as the production
download mechanism. Instagram Web can expose blob-backed playback and a broad
response observer is both brittle and an unnecessarily sensitive integration
surface.

## Decision

The Collector is a sequential server-side pipeline:

1. Verify the Instagram session, open the personal Reels feed, identify the
   active shortcode and pause its video.
2. Use `shortcode` as the global external idempotency key.
3. If the source is not already durable, download it session-first, validate it
   with ffprobe, persist the source object, and commit `source_ready`.
4. Permit exactly one subsequent scroll only after that durable source commit,
   or after verifying an already durable source. A failure for the current Reel
   prohibits scrolling.
5. A separate normalizer advances `source_ready -> normalizing -> ready`.
   A retryable normalizer error returns the Reel to `source_ready`; its finished
   failed normalization job retains the safe reason code and a later pending
   job performs the retry. The Collector never waits for transcoding before
   moving the feed.
6. Only `ready` canonical MP4 (H.264, yuv420p, AAC) is linked to `videos` and
   becomes visible in the existing PWA catalog. VP9/AV1 source media never
   enters `videos` directly.

The persistent Chromium profile is a secret infrastructure concern. In a later
service it is mapped from an internal account UUID into an isolated encrypted
volume, never stored as a database path. The user enters password and 2FA
directly in Instagram. Production yt-dlp is session-first and receives only a
minimal in-memory CookieJar. Cookie files, `cookiesfrombrowser`, storage-state
export, persisted cookies, auth headers, and cookie logging are prohibited.

Checkpoint, CAPTCHA, or reauthentication move the account into a controlled
state and stop automation. Persisted reason codes are short, stable machine
codes matching ASCII `^[A-Z][A-Z0-9_]{0,63}$` at the domain/service boundary.
The database bounds them to `String(64)` but does not parse arbitrary text. Raw
exceptions, Instagram HTML, CDN URLs, headers and cookie/session markers are
never stored.

## Persistence boundary

The foundation adds:

- `instagram_accounts` for safe connection state only;
- `instagram_reels` for global identity, source state and the optional unique
  link to a canonical `videos` row;
- `instagram_collection_runs` and ordered run items for durable sequential
  history, with a partial unique index allowing one queued/running run per
  account;
- `instagram_normalization_jobs` as a durable future-worker queue, with one
  active pending/running job per Reel.

The database enforces source metadata for `source_ready`, `normalizing` and
`ready`, and enforces the `ready -> videos` relationship. It cannot cleanly
express cross-table source-state validation for job insertion without a trigger;
that final guard belongs to the future service transaction.

Portable database checks reject empty shortcode, canonical URL and source object
key values, and require a 64-character source SHA-256 when supplied. Canonical
Instagram URL validation and hexadecimal SHA content remain future service-layer
validation, avoiding database-specific regular expressions.

A permanent source failure may enter `failed`; a subsequent collection run can
explicitly retry it through `failed -> downloading`. `ready` remains terminal.
Run items store a nullable download auth mode: `source_committed` records the
actual `session_first` attempt, `already_available` records no mode because no
download ran, and `failed` may be either pre-attempt or session-first.

## Consequences and alternatives

The server-side Collector can operate independently from the phone. The phone
still cannot be relied on for large background downloads when an iOS PWA is
fully closed.

Alternative approaches rejected for this foundation:

- official API: it does not provide the target personalized feed;
- client-side Instagram access: it would expose a prohibited credential/session
  boundary;
- direct copy of spike code: it mixes experimental browser runtime with the
  production core;
- broad blob/network extraction: rejected after B1 due to fragile blob-backed
  media and excessive observation scope;
- combining normalization with feed collection: it would break the durable
  source-before-scroll throughput boundary.

## Implemented fixture core

Stage 2 implements the orchestration core only with deterministic fixtures. It
uses production-owned typed ports for a feed, downloader, validator and source
storage; no port exposes DOM, HTML, cookies, browser state or media URLs. The
fixture service proves the required `detect -> pause -> download -> validate ->
publish -> durable DB commit -> advance` order and records only safe summary
fields. It creates the pending normalization job in the same database
transaction as the Reel source metadata and run item.

Because source storage and PostgreSQL are separate systems, a failure after a
new fixture publication gets best-effort compensation for that new object only.
Compensation cannot delete an object that existed before the attempt and cannot
replace the original safe database-failure reason. Full startup reconciliation,
MinIO, browser automation and session-first yt-dlp adapters remain future,
isolated runtime work. This core does not change current PWA, video API, or
normalizer behavior.
