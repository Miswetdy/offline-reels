# ADR 018: Authenticated feed-JSON canonical Reel fallback

## Status

Accepted.

## Context

Mobile Instagram Reels can advance the visible media while retaining a generic
`/reels/` location and exposing no nearby canonical anchor. The Collector must
not use a stale canonical URL after a confirmed media transition.

## Decision

The Instagram browser adapter listens only to authenticated JSON responses and
extracts bounded, strictly validated `code` fields into an in-memory queue.
It never persists, logs, returns, or exposes response bodies, URLs, cookies,
media URLs, or raw JSON. DOM canonical identity remains preferred. If it is
missing or stale, the fallback is eligible only after a distinct active-media
identity has been observed. The code is converted to the existing canonical
`https://www.instagram.com/reel/{code}/` candidate and passes the established
candidate validator before download.

## Consequences

- The Collector can continue after a confirmed mobile swipe when DOM anchors
  are unavailable.
- The fallback remains isolated inside the replaceable Instagram adapter.
- The bounded queue is not an API contract and must have fixture/unit coverage.
