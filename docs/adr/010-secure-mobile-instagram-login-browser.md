# ADR 010: Mobile Instagram login through server Chromium

## Status

Accepted for the functional Windows Docker Desktop Stage 4 runtime. Production
Linux sandbox acceptance is deliberately pending.

## Decision

Stage 4 uses a separate non-root `login-browser` service with headed Chromium,
Xvfb, x11vnc and noVNC/websockify. VNC, X11 and CDP remain internal to isolated
Docker networks. An isolated same-origin HTTPS gateway validates a short-lived
one-time token and proxies the remote display/WebSocket after Secure,
HttpOnly, SameSite cookie, Host and Origin validation. An opt-in Tailscale
Funnel sidecar terminates public HTTPS and reaches only the internal gateway;
Docker publishes no host ports.

Safari or the installed PWA is sufficient; Chrome on iPhone is not required.
Credentials, 2FA and CAPTCHA are entered directly into the real Instagram page
inside server Chromium. The application business API does not request, log or
persist them. CAPTCHA is not automated. The gateway/noVNC transport relays
keyboard and pointer events and is therefore a trusted credential-input
infrastructure boundary, but it does not inspect or retain those events.

The database stores only session/account UUIDs, timestamps/status, compact
reason code and a SHA-256 launch-token hash. It never stores passwords,
cookies, storage state, HTML, media URLs or raw browser errors. The account
profile volume is sensitive persistent state. Completion, expiry and
cancellation retain it; destructive reset needs the exact account UUID and an
explicit operator acknowledgement. The public gateway never mounts it.

The gateway hides the remote display after a valid login, or a retained-profile
check, while it performs fixed server-side verification. It then shows its own
local completion view rather than an authenticated Instagram feed.

For the current Windows Docker Desktop compatibility runtime,
`seccomp=unconfined` applies to `login-browser` only. That container remains
non-root and drops all Linux capabilities. `--no-sandbox`, `SYS_ADMIN`, a root
browser, host VNC/CDP/X11 ports, automatic login and automatic CAPTCHA solving
remain forbidden. This narrow exception is not a production-hardening claim.

## Consequences

- Link creation remains operator CLI only until a protected management API
  exists; the dashboard has no connection button in Stage 4.
- The launch token is after a URL fragment and is activated only by a
  user-initiated same-origin POST, so link-preview GET requests cannot consume
  it.
- A future protected dashboard flow may add “Подключить Instagram”. It must
  create the same one-time session, use only a fixed same-origin post-success
  route and never accept an arbitrary `return_url`.
- Production deployment needs a separate real-Linux validation of Chromium’s
  restricted seccomp/sandbox configuration before enabling any public login.
- Collector, normalizer, Reels/jobs and `videos` are not started or changed.
