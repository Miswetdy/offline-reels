# 014. Viewed Reel lifecycle is local-first and account-scoped

## Decision

A Reel becomes viewed only when a user pointer/touch swipe from its active,
full-screen card commits a transition to a different full-screen card. A short
transition token binds the gesture to source A and is consumed by the matching
A → B commit. Autoplay, `currentTime`, watch duration, ended events, visibility,
reloads, preloads, pagination, layout, internal React updates and programmatic
navigation are not viewed decisions. Accessibility navigation is not included
in this MVP decision.

The first qualifying event writes `viewedAt`, `deleteAfter` (`viewedAt + 1h`),
a deletion tombstone and a sync-outbox entry in the same IndexedDB transaction
before any request. It is monotonic: subsequent playback never changes the
first time. One hour later the foreground lifecycle marks deletion started,
deletes only the Cache Storage object, then commits a retained `deleted`
tombstone. A closed iOS PWA performs overdue work on its next launch,
foreground or network return; it does not claim background execution.

Backend persistence is `instagram_reel_views`, unique by `(account_id,
reel_id)`. Its first `viewed_at` is immutable server time. The management batch API
accepts only bounded canonical video UUIDs, resolves account ownership through
collection run items, and is idempotent. The account-ready catalog excludes
confirmed views. Global canonical MP4s and other accounts are unaffected.

## Consequences

The single `offlineVideos` IndexedDB store retains tombstones/outbox records;
`cancelAndClear` removes eligible local media but not viewed history. The
download queue and reserve candidates reject tombstoned IDs, including a late
download completion. Deletion reconciliation is single-flight and never starts
refill. Stage 8 infrastructure remains in the codebase but automatic refill is
temporarily disabled for the MVP by a production-false compile-time gate.
`viewed` is lifecycle data only: the ordinary Reels UI does not expose a watched
marker or technical timestamps.
