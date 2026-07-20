# ADR 003: Keyset pagination and native multi-video feed

## Status

Accepted.

## Context

The `/videos` page needs to load multiple videos incrementally without duplicate entries, offset drift, or a client dependency on MinIO. It also needs a simple mobile-friendly vertical interaction before performance optimizations are introduced.

## Decision

- `GET /videos` returns `{ "items": [...], "next_cursor": "..." }`.
- Videos are ordered by `created_at DESC, id DESC` and PostgreSQL uses keyset pagination from the last returned tuple.
- The cursor is a versioned base64url JSON payload signed with HMAC-SHA-256. It is opaque to the client and is verified with `hmac.compare_digest`.
- The `/videos` frontend uses native vertical scroll-snap. `IntersectionObserver` retains a ratio for every mounted item, resolves ties by the feed center, and is backed by a requestAnimationFrame-throttled scroll fallback. The active item plays while all other players are paused.
- Playback starts muted. A feed-session React state controls the custom accessible mute button and all mounted players.
- The frontend requests five records per page. It keeps loaded video elements mounted, but assigns a stream URL only to the active item (`preload="auto"`) and the next item (`preload="metadata"`); all other items use `preload="none"` without a source.

## Consequences

- No database schema change or offset pagination is needed; the existing `(created_at, id)` index supports the query.
- `VIDEO_CURSOR_SECRET` is required and must be unique and random in production.
- The browser receives only Backend API URLs and never receives MinIO credentials or direct object URLs.
- Long feed sessions can increase browser memory because virtualization is intentionally deferred until real-device measurements justify its complexity.
- Browser autoplay can still be rejected; the UI catches this per video and remains usable.
