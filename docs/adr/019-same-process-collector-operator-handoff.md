# ADR 019: Same-process Collector operator handoff

## Decision

The opt-in Stage-10 `collector-handoff` profile opens the persistent Collector
Chromium context once, then pauses before any Collector input or data-plane
operation. A separate hardened gateway relays only its internal noVNC endpoint.
The gateway grants access with a one-time token and signed HttpOnly cookie at
the fixed HTTPS origin; confirmation or cancellation is written to a private
shared state volume. Confirmation resumes the already-open feed object; it
does not relaunch Chromium or navigate again.

## Consequences

The handoff state contains only state codes, expiry and a launch-token hash.
The raw launch token is a transient 0600 volume file and is removed at
activation. VNC/CDP/profile/cookie ports remain unpublished. Expiry and cancel
close the browser without starting persistence, download, Redis or MinIO work.
After confirmation the existing direct-hit, native-touch, JSON and bounded
3/3 gates remain the authority for collection.
