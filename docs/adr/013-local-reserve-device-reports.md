# ADR 013: Local reserve remains device-authoritative

Stage 8 keeps completed Reel truth in PWA IndexedDB plus Cache Storage. The
backend stores only a safe, account-owned last report per generated non-secret
device UUID: enabled flag, counts, thresholds and timestamp. It stores no media
objects, Cache URLs, browser internals, cookies or credentials.

Migration `0008` is needed because reports must survive API restart and
concurrent sessions. Copying media lifecycle into PostgreSQL would introduce a
conflicting source of truth.
