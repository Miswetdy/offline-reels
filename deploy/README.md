# Production-like VPS foundation

Stage 10 adds a separate hardened Ubuntu staging composition and a networkless
Chromium acceptance gate. Use the dedicated
[`Stage 10 Linux staging runbook`](../docs/operations/stage-10-linux-staging.md)
before any server deployment; do not infer Linux sandbox readiness from the
older Windows Docker Desktop workflows below.

Its opt-in `instagram-login` profile reuses the protected mobile login contract
without the older Stage 4 `seccomp=unconfined` exception. The hardened browser
shares only the persistent account profile with Collector, while the gateway
owns the same-origin `/connect/*` and `/remote/*` boundary. Neither service
publishes a host port and neither starts with the base application.

This directory is deliberately separate from the local-development
[`compose.yaml`](../compose.yaml). Do not use the production Compose file for
desktop development, and do not publish the local Compose data-service ports
on a VPS.

## Prerequisites

- Ubuntu VPS with current Docker Engine and the Docker Compose plugin.
- DNS `A`/`AAAA` records for `APP_DOMAIN` and `API_DOMAIN` pointing to the VPS.
- Firewall access only for SSH administration and TCP ports 80 and 443.
- A checkout of one reviewed Git revision. Use its immutable short SHA as
  `IMAGE_TAG`.

Caddy obtains and renews public TLS certificates automatically. Both domain
names must be public hostnames without a path or scheme, and ports 80 and 443
must reach Caddy.

## Create production environment

On the VPS, copy the committed template and restrict its permissions:

```sh
cp deploy/.env.production.example deploy/.env.production
chmod 600 deploy/.env.production
```

Replace every `REPLACE_WITH_*` value. Generate independent URL-safe passwords
for PostgreSQL and Redis, and independent root/application credentials for
MinIO. For example:

```sh
openssl rand -hex 32
openssl rand -base64 48
```

`NEXT_PUBLIC_API_BASE_URL` is not a secret. It is embedded in the browser
bundle during `web` image build and must be `https://API_DOMAIN`. Rebuild the
web image whenever it changes. `FRONTEND_ORIGIN` must be exactly
`https://APP_DOMAIN` without a trailing slash.

## Validate and build

Run all commands from the repository root:

```sh
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml config -q
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml build
```

The production file publishes only Caddy ports 80 and 443. PostgreSQL, Redis,
the MinIO API, and the MinIO Console are private to Docker networks.

## Local Docker Desktop smoke

For a local production-like runtime smoke only, create a separate ignored
`deploy/.env.production` with fresh local secrets and use the committed
`docker-compose.local-smoke.yml` override:

```sh
docker compose --env-file deploy/.env.production \
  -f deploy/docker-compose.prod.yml \
  -f deploy/docker-compose.local-smoke.yml config -q
```

The override mounts `Caddyfile.local`, which serves `http://app.localhost` and
`http://api.localhost` without ACME or public TLS. It is not an iPhone PWA or
VPS acceptance configuration. It retains the production network boundaries and
publishes only Caddy's HTTP port 80. Stop this local stack with `docker compose down`
without `-v` after its persistence checks complete.

## Public Tailscale Funnel staging (Windows host)

This is a temporary, public staging environment for iPhone PWA acceptance. It
is not a substitute for a VPS deployment: Funnel exposes the application to
the whole internet while the Windows host is online. Do not put real production
credentials in this environment, and turn Funnel off when testing ends.

Install the official Windows client, sign in to a Personal tailnet, and verify
the current CLI before publishing anything:

```powershell
tailscale status
tailscale funnel --help
```

The current supported Funnel syntax publishes HTTPS on the Tailscale hostname
and forwards to a loopback-only HTTP target. Create a separate ignored local
environment file using the host name reported by Tailscale (without a trailing
slash):

```powershell
Copy-Item deploy/.env.funnel.example deploy/.env.funnel
# Replace all placeholders, including the host in both public URL variables.
```

Set the public browser values as one origin:

```text
NEXT_PUBLIC_API_BASE_URL=https://YOUR_MACHINE.YOUR_TAILNET.ts.net/api
FRONTEND_ORIGIN=https://YOUR_MACHINE.YOUR_TAILNET.ts.net
```

The Funnel override keeps the production Compose topology, but replaces the
Caddyfile and binds Caddy only to `127.0.0.1:8080`. It strips the `/api` path
prefix before FastAPI, while all other paths go to Next.js. It does not expose
web, API, PostgreSQL, Redis, MinIO, or the MinIO Console directly.

```powershell
docker compose --env-file deploy/.env.funnel `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.funnel-smoke.yml config -q

docker compose --env-file deploy/.env.funnel `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.funnel-smoke.yml up -d --build

curl http://127.0.0.1:8080/api/health/ready
tailscale funnel --bg http://127.0.0.1:8080
tailscale funnel status
```

The first Funnel command can open the Tailscale approval flow; approve it only
for this staging tailnet. `--bg` persists across a Tailscale restart, so stop
it explicitly after the test (the exact stop form is shown by the installed
CLI; with the current CLI it is):

```powershell
tailscale funnel --https=443 off
docker compose --env-file deploy/.env.funnel `
  -f deploy/docker-compose.prod.yml `
  -f deploy/docker-compose.funnel-smoke.yml down
```

Verify the public URL from a non-local network before using an iPhone. Requests
to `/api/health/live`, `/api/videos`, and `/api/videos/VIDEO_ID/stream` must
stay on the same `*.ts.net` origin. The final stream check must still produce
`206` and `416` for valid and invalid ranges. Do not expose administrative
endpoints, MinIO, or database ports through Funnel.

The completed iPhone acceptance established two operational rules: Safari and
the installed Home Screen PWA have separate local-storage contexts, so install
the PWA before downloading videos; and incoming MP4 codec parameters matter.
The observed compatible form was H.264 with `yuv420p` and `faststart`; media
normalization is the next application stage. Funnel remains temporary public
staging, not a permanent deployment target.

## First launch

Start stateful services and wait for their healthchecks:

```sh
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d postgres redis minio
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml ps
```

Create the MinIO bucket and its limited application user. The job is safe to
run again with the same credentials:

```sh
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml run --rm minio-bootstrap
```

Run migrations as a controlled, one-shot operation. The API service itself
never performs migrations on startup. The production commands use `uv run
--no-sync`, so runtime startup never tries to download development dependencies:

```sh
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml run --rm migrate
```

Start the application and TLS proxy:

```sh
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --no-deps api web
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml ps
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --no-deps caddy
```

`--no-deps` is intentional at this point: PostgreSQL, Redis, MinIO, the
bootstrap job, and the migration job have already completed under operator
control. Do not use it before those steps. The Compose dependency conditions
remain a safe default for a fresh `up`.

## Verify production paths

After DNS and TLS are ready:

```sh
curl --fail https://API_DOMAIN/health/live
curl --fail https://API_DOMAIN/health/ready
curl --fail https://APP_DOMAIN/offline
curl -sS -D - -o /dev/null -H 'Origin: https://APP_DOMAIN' https://API_DOMAIN/videos
curl -sS -D - -o /dev/null -X OPTIONS https://API_DOMAIN/videos \
  -H 'Origin: https://APP_DOMAIN' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: Range'
```

Both CORS responses must contain `Access-Control-Allow-Origin: https://APP_DOMAIN`.
The preflight response must allow `GET` and `Range`; no other browser origin is
permitted.

For a seeded video ID, verify that Caddy preserves backend Range behavior:

```sh
curl --fail --range 0-1023 -D - -o /dev/null https://API_DOMAIN/videos/VIDEO_ID/stream
```

Expect `206 Partial Content`, `Accept-Ranges: bytes`, `Content-Range`, and a
matching `Content-Length`. Do not add a Caddy media cache or a Range rewrite.

## Operational safety

- Never commit `deploy/.env.production` or copy it to support channels.
- Never run `docker compose down -v` against this production file: it removes
  persistent PostgreSQL, Redis, MinIO, and Caddy state volumes.
- The `migrate` service should be run deliberately before an application
  rollout. Automatic rollback of Alembic migrations is intentionally not part
  of this foundation.
- This block does not yet provide backup, restore, or automated deploy scripts.
