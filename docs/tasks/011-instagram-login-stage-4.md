# TASK-011: Stage 4 protected mobile Instagram connection

`login-gateway` is separate from normal FastAPI startup. An operator creates a
1–15 minute link with `app.scripts.stage4_login create-link`; its token prints
once and only its SHA-256 hash is durable. Reuse, expiry, cancel and concurrent
active links are safely rejected. Gateway CSP, no-store, frame, Host/Origin,
cookie and WebSocket rules protect the remote display.

`login-browser` runs headed Chromium as UID 10002. CDP/VNC are internal only.
The controller checks only Instagram boundary, login/checkpoint state, central
Reels availability and permitted cookie names; values are neither logged nor
exported. On success it transitions the account to `connected`, stops browser
processes and preserves the dedicated browser profile.

The mobile gateway is mobile-first: its local preparation, challenge and result
screens fit the phone viewport. It reveals no remote browser except while the
user must operate Instagram's own login/2FA/CAPTCHA page. Once browser state is
ready, a fixed server-side Reels probe replaces the remote surface with local
“checking connection” and then “Instagram connected”; the authenticated feed
is not shown to the user.

No Collector run, downloader, normalizer, dashboard control, credential API,
CAPTCHA bypass or `videos` change is part of this task. See ADR 010.

Future dashboard integration is deliberately out of scope until a protected
management API exists. Its agreed shape is **Подключить Instagram** → one-time
session → preparation → real Instagram login/challenge only when required →
local success with **На главную**. The keyboard control is shown only for the
interactive remote page; the home link is fixed same-origin, with no user
controlled return URL.

The public edge is an opt-in official Tailscale Funnel sidecar. It receives a
restricted ephemeral identity, terminates HTTPS and proxies only to the Compose
internal login-gateway; no Docker port is published on Windows.

Functional iPhone acceptance is on Windows Docker Desktop. In that temporary
runtime only `login-browser` has `seccomp=unconfined`; it remains UID 10002 with
`cap_drop: ALL`. The exception does not apply to the gateway, PostgreSQL or
Tailscale. This task is functionally complete after its Windows acceptance, but
is not production-hardened: a real Linux deployment must independently validate
a restricted Chromium sandbox before it is public.
