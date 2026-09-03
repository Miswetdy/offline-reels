# ADR 017: Hardened Stage 10 Instagram login boundary

## Status

Accepted for Linux staging acceptance; production-domain acceptance remains pending.

## Context

The Stage 6/7 management flow already creates a single-use, same-origin
`/connect/{id}` launch capability, while the Stage 4 remote browser already
keeps credentials inside a non-root Chromium boundary. The old Stage 4 Compose
project is Windows-compatible and isolated from staging data, uses
`seccomp=unconfined`, and owns a different profile volume. It therefore cannot
create the authenticated profile consumed by the hardened Stage 10 Collector.

The personal MVP has one Instagram account and permits only one process to own
that account's Chromium profile. This is not a multi-tenant browser scheduler.

## Decision

Add opt-in `instagram-login` services only to the Stage 10 Compose overlay.
`login-browser` runs as UID/GID 10001 with a read-only root filesystem, all
capabilities dropped, no-new-privileges, the pinned Chromium seccomp policy and
the enforcing `offline-reels-collector` AppArmor policy. It publishes no host
port. CDP stays on container loopback; VNC and the safe controller are reachable
only by `login-gateway` on an internal network.

The browser mounts `collector_profile_stage10` at `/login-profiles`; Collector
mounts the same named volume at `/collector/profile`. Both resolve the same
account UUID subdirectory. The login browser enforces UID/GID 10001 and mode
0700, and atomically owns the existing `.collector.lock` for its full lifetime.
The Linux kernel lock is released automatically if either container exits or
crashes; the harmless lock inode may persist without blocking the next owner.
Consequently a live Collector fails closed while login is active, and login
fails closed while Collector owns the profile.

Login and Collector use the same pinned Chrome for Testing artifact
(`151.0.7922.34`) for this shared persistent profile. Collector drives it
through Playwright with `chromium_sandbox=True`; login launches the same binary
headed under Xvfb. Neither side uses `--no-sandbox` or suppresses the Chromium
user-namespace sandbox.

Stage 10 Caddy forwards only `/connect/*` and `/remote/*` to the gateway on the
existing public origin. WebSocket upgrades pass through that route, but VNC,
CDP, the browser controller, Docker socket, database, and profile volume are
never published. The production Caddyfile is unchanged.

The login services are started only for initial connection or reauthentication.
After the gateway confirms the authenticated Reels boundary, it shuts down the
browser normally and the persistent profile remains for Collector. Credentials,
cookies, launch tokens, DOM content and raw Instagram responses are not logged.

## Consequences

- The Stage 10 profile is reusable for the personal production topology rather
  than a disposable test fixture.
- Two new independent staging secrets protect the gateway cookie signature and
  its private browser controller.
- Operators must start and preflight the opt-in login services before pressing
  the dashboard connection button.
- A profile created with a different Chromium release must not be force-opened
  or downgraded. The opt-in `instagram-profile-reset` service reuses the
  existing guarded reset contract and removes only the named account directory
  after explicit operator confirmation and no active login session. It then
  transitions that account to `disconnected`, so the management UI cannot
  claim a usable login after its browser profile has been removed.
- A future multi-user product requires per-account jobs, isolated volumes,
  concurrency quotas and lifecycle orchestration; this decision does not claim
  that capability.
