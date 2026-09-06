# ADR 022: Embedded Reels feed candidate queue

## Context

The Stage-10 mobile presentation can confirm a stable active-media change but
does not expose a safe DOM or URL binding to its canonical Reel ID. The
authenticated GraphQL and Web API responses observed during the same flow did
not contain an accepted canonical alias. In contrast, the authenticated fixed
`/reels/` document contained explicit JSON scripts with validated alias values.

## Decision

After fixed Reels navigation, `AuthenticatedFeedSource` may read only explicit
`application/json` and `application/ld+json` scripts in the current
authenticated document. It traverses each parsed payload with fixed size and
node bounds, accepts only values under `code`, `shortcode` or `media_code` that
pass the canonical shortcode validator, de-duplicates them, and retains at
most 32 values only in process memory.

The queue is independent of swipe. A candidate may be reserved only after the
existing stable-media and post-input authenticated-JSON gates. It is not
represented as a claim that the ID is the exact visual card after that swipe.
Inline JavaScript, DOM attributes, URLs, generic response bodies, non-JSON
assets, cookies, logs and persistent storage remain excluded from this source.

## Consequences

This supports a personalized recommendation queue while preserving bounded
input and fail-closed behavior. The initial candidate and every queued
candidate still pass the existing download, validation, normalization and
durable-publish pipeline. A missing embedded candidate or gate remains a
terminal transition failure; no retry or target limit is widened.
