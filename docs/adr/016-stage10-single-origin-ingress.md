# ADR 016: Stage 10 single-origin loopback ingress

## Status

Accepted. Public Funnel routing was accepted; login-path routing is amended by
[ADR 017](017-hardened-stage10-instagram-login.md).

## Context

OfflineReels requires one browser origin because the management client uses
same-origin `/api/*` requests, same-origin credentials, and strict Backend
Host/Origin validation. Tailscale path mounts strip their mount prefix, while
the Backend intentionally owns both root paths such as `/videos` and prefixed
paths such as `/api/management/*`. Separate public ports would make management
cross-origin.

The former Next.js `/videos` page only redirected to `/`, but it collided with
the Backend catalog's exact `GET /videos` path. A reverse proxy cannot route
both representations on one method and path without an additional implicit
contract.

## Decision

Remove the obsolete frontend `/videos` route and its application-shell entry.
The canonical frontend routes remain `/` and `/offline`; `/videos` and its
subpaths belong exclusively to the Backend and remain excluded from Service
Worker shell caching.

Add a Stage-10-only Caddy ingress on container port 8080, published only as
`127.0.0.1:13080`. It forwards `/videos`, `/videos/*`, `/health/*`, and
`/api/*` to FastAPI without rewriting. ADR 017 adds opt-in `/connect/*` and
`/remote/*` routing to the isolated login gateway; remaining paths go to
Next.js. It joins `caddy_web`, `caddy_api`, and the login-only ingress network.
The included
production Caddy is disabled and has its host ports reset only in the Stage 10
Compose model; the production Compose file and Caddyfile remain unchanged.
The derived ingress image uses pinned Caddy 2.11.4 and removes its unnecessary
`cap_net_bind_service` file capability because it listens above port 1024;
the runtime can therefore retain `cap_drop: ALL`.

Use one external HTTPS origin for `NEXT_PUBLIC_API_BASE_URL`,
`FRONTEND_ORIGIN`, and `MANAGEMENT_ORIGIN`. Tailscale Serve may later proxy
that origin to the loopback ingress. Funnel remains behind a separate operator
approval.

## Consequences

The web image must be rebuilt because the public API base and App Router tree
are build inputs. Existing installed PWAs can retain the retired `/videos`
shell until the waiting Service Worker update is explicitly activated. Local
and tailnet acceptance must confirm the new worker before `/videos` is treated
as exclusively Backend-owned.

Caddy performs no path rewrite, response caching, or compression. Range and
streaming headers remain end-to-end Backend semantics and require acceptance
with seeded media when available.
