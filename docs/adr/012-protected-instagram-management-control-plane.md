# ADR 012: Protected Instagram management control plane

## Status

Accepted.

## Decision

The management API is a PostgreSQL command/state plane, protected by one-time
operator-created device pairing. The CLI emits a short-lived secret once and
the database stores only its SHA-256 hash. Exchanging it consumes the challenge
and sets a short-lived `__Host-` secure, HTTP-only, strict-same-site cookie.
CSRF is session-bound and required with an exact configured HTTPS Origin and
Host for every mutation.

FastAPI only creates, reads and cancels durable commands. It does not import or
start Playwright, Chromium, yt-dlp, ffmpeg, a browser profile, the Collector or
the normalizer. The login gateway claims the existing Stage 4 login state; the
Collector claims queued runs; normalizer workers continue to claim pending
jobs. A cancel request is cooperative: committed Reels remain durable and the
Collector checks cancellation before a Reel, download, publication and scroll.

Login capability is constructed only for the initial response, has `no-store`,
uses a fixed configured HTTPS gateway origin and is never persisted in an
idempotency record. Replaying a request returns the safe session state without
the capability. Auto-collection settings are storage only: `scheduler_active`
is always false until a scheduler is separately implemented.

## Consequences

- The frontend has no static admin/API secret.
- Tokens, pairing values, CSRF values and idempotency keys are hashed and are
  excluded from safe results and application logging.
- Mutations use DB-backed idempotency scoped to management session, operation
  and canonical request fingerprint.
- Technical UUIDs and reason codes are API contracts, not dashboard UI copy.
