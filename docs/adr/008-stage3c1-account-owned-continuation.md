# ADR 008: Account-owned Collector continuation

## Status

Accepted.

## Decision

An account's Collector reserve is the distinct set of durable Reels represented
by its historical successful acquisition run items. A globally durable
`instagram_reels` row does not imply ownership by another account. Stage 3C.1
therefore creates an `already_available` item only when a durable global Reel
is new to the current account; prior account ownership is a no-write
`duplicate_skipped` observation.

The continuation run stores the start-time deficit as `target_count`. Final
completion uses a fresh total recheck in the same transaction that marks the
run completed. This uses migration 0004 unchanged and preserves its existing
run-item uniqueness invariant.

## Consequences

Interrupted runs retain committed acquisitions. A future run derives a new
deficit rather than replaying prior shortcodes. Browser state, cookies and
credentials remain outside database history and safe result JSON.
