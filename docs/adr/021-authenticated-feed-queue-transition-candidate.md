# ADR 021: Authenticated feed-queue transition candidate

## Context

In the Stage-10 mobile Chromium presentation, a bounded input can produce a
stable change to the central media identity and a new authenticated Instagram
JSON response while the visible card exposes no safe DOM/URL mapping to its
canonical Reel code. Requiring a code observed only after the gesture then
rejects a genuine transition even though the current authenticated Reels feed
already supplied unused, canonical candidates before that checkpoint.

## Decision

The Collector resets its bounded in-memory feed candidate catalog immediately
before navigating to the fixed `/reels/` URL. After both the stable-media and
post-input JSON gates pass, it first prefers a different canonical code from
the existing safe central-video DOM probe, then a different canonical code
observed after the input checkpoint.

If and only if the media identity has changed stably and at least one
authenticated JSON response arrived after the bounded input, it may instead
reserve the next unused, different candidate from that same current-navigation
catalog. The fallback is one-shot: a reserved code is removed from the queue,
the queue is bounded, and candidates are never recovered from a prior browser
page, URL parsing, DOM attributes, logs, or persistent storage.

The transition diagnostic records only the aggregate booleans
`canonical_dom_confirmation_observed` and
`canonical_queue_fallback_observed`. Native-touch admission, wheel/keyboard
fallbacks, timeouts, retry bounds, source validation and durable persistence
are unchanged.

## Consequences

The fallback proves that the next download is a unique canonical Reel supplied
by the authenticated current feed, not that a mobile MSE DOM node can be
bijectively mapped to that exact visible card. This is sufficient for the
personalized feed collection contract but is deliberately not represented as a
DOM-derived visible-card identifier. A missing stable media change or a missing
post-input JSON observation remains fail-closed.
