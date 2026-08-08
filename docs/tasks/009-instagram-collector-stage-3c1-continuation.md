# TASK-009: Stage 3C.1 Collector continuation

Stage 3C.1 adds a separately invoked, headed Windows operator command that
continues the preserved Stage 3B account from three to ten durable Reels. It is
not a container service and is never imported by FastAPI.

Before Chromium starts, the command reads the account UUID from the preserved
non-secret operator state, counts distinct durable Reels using only that
account's historical `source_committed` and `already_available` run items, and
checks the immutable metadata/object baseline. `--desired-total` accepts only
`10`; initial totals below three, above ten, or a DB/MinIO mismatch stop safely.
At ten it performs read-only verification and does not launch a browser.

`target_count` is the start-time deficit (`10 - initial`), not the final total.
A globally durable Reel without this account's history is linked through one
`already_available` item. An account-owned durable Reel produces only the safe
`duplicate_skipped` event; it creates no CookieJar, download or run item.
Duplicates therefore do not consume the acquisition target.

The continuation is bounded to 30 observed positions, 29 transitions, 58 wheel
actions, 100 MiB per source, 700 MiB new data and a 60-minute deadline. Each
download obtains a fresh session-first CookieJar. The final acquisition is
transactionally checked against an account durable total of exactly ten and
does not scroll. Cancellation preserves committed sources and makes the next
command recompute the actual deficit.

Run manually only after reviewing the read-only smoke state:

```powershell
.\scripts\run-collector-stage3c1.ps1
```

The controlled Stage 3C.1 continuation completed after implementation: it
started from three, committed seven new sources, confirmed six transitions and
ended with ten durable account-owned Reels. The first verifier result exposed a
transcript-only false negative (normal first-wheel confirmation was incorrectly
treated as requiring a retry); it was fixed, regression-tested, and the stored
safe transcript plus an already-satisfied read-only verifier both pass. No
source was re-downloaded during verification.
