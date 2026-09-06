# ADR 020: Narrow mobile feed-shell swipe surface

## Context

On Stage 10, the authenticated mobile Reels page can place an inert,
full-viewport semantic `main` surface above the selected central video. The
video remains in the hit stack, but demanding that `elementFromPoint()` return
the video itself rejects a gesture a real mobile user sends to the feed shell.

## Decision

The Collector may use that surface for its existing one bounded native-touch
swipe only if every condition holds at both endpoints: the exact same hit
element is `main` or `[role=main]`; it covers the viewport; it is neither a
control nor within a dialog; it is not hidden, inert or pointer-events-none;
and the selected central video is directly below it in the point stack. The
surface identifier and coordinates remain process-local. Diagnostics contain
only aggregate booleans.

Direct video hits remain preferred. Any child of the semantic shell, unknown
overlay, control, dialog, other-video relation, or missing stack evidence is
rejected. The native-touch action, stable media identity requirement,
post-action authenticated JSON gate, canonical validation, retry bound and
timeouts are unchanged.
