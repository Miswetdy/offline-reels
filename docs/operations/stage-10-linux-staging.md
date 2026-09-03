# Stage 10 Linux staging runbook

## Scope and stop gates

This runbook targets Ubuntu 24.04 LTS amd64 with Docker Engine 29.7.2 and
Docker Compose 5.5.0. It is written for a reviewed immutable repository
revision. It contains no host address, login name, or secret.

There are three separate gates:

1. install one Collector-only AppArmor profile and run read-only host checks;
2. build and run the networkless synthetic Chromium sandbox proof;
3. only after that proof is accepted, prepare secrets and deploy the staging
   application/data services.

Stop after gate 2 unless application deployment has separate approval. Do not
run the live `collector` service until an authenticated Linux staging profile
has also been created through an accepted login boundary. Never copy the old
Windows Docker Desktop profile.

## Minimal topology

The Stage 10 Compose file includes the existing production-like topology but
uses its own HTTP ingress. Only `stage10-ingress` publishes a host port, at
`127.0.0.1:13080`; the included production Caddy is disabled and has no Stage
10 host ports. The ingress joins only `caddy_web` and `caddy_api`. It cannot
reach the internal PostgreSQL, Redis, or MinIO network. The normalizer remains
browser-free and opt-in.

The ingress preserves request paths. `/videos`, `/videos/*`, `/health/*`, and
`/api/*` go to FastAPI; all other paths, including `/`, `/offline`, `/_next/*`,
`/serwist/*`, `/manifest.webmanifest`, and `/offline-media/*`, go to Next.js.
The former frontend `/videos` redirect was removed so `/videos` is
unambiguously the Backend catalog API. Its pinned Caddy image removes the
upstream binary's low-port file capability because the container listens on
8080; runtime capabilities remain fully dropped.

The live Collector is an explicit one-shot profile. It joins `app_private` for
PostgreSQL/MinIO and `collector_egress` for Instagram/media acquisition. It
publishes no port and mounts only its profile and workspace volumes. The
Stage 10 web build pins its manual collection target to three, matching the
only target accepted by this bounded Collector; the production default is
unchanged outside the overlay. The
synthetic service is a different standalone Compose project with no networks,
ports, secrets, persistent volumes, or data services.

The `instagram-login` profile is separately opt-in. Its non-root browser and
gateway publish no host ports. Caddy forwards same-origin `/connect/*` and
`/remote/*` to the gateway; the gateway alone reaches private VNC/browser
control. Login and Collector mount the same account profile and use one atomic
lock, so they cannot operate concurrently.

## Gate 0: review the checkout

Run from the repository root:

```sh
git status --short --branch
git rev-parse HEAD
git diff --check
```

The intended revision must be reviewed and the worktree must be clean. Do not
place Instagram cookies, profiles, environment files, or support dumps in the
checkout.

## Gate 1: install the narrow AppArmor policy

This is the only root-owned Stage 10 host policy change. It does not change a
sysctl and does not weaken unconfined host processes:

```sh
sudo install -o root -g root -m 0644 \
  deploy/security/offline-reels-collector.apparmor \
  /etc/apparmor.d/offline-reels-collector
sudo apparmor_parser --skip-cache -r -W /etc/apparmor.d/offline-reels-collector
sudo aa-status | grep offline-reels-collector
```

Keep `kernel.apparmor_restrict_unprivileged_userns=1` when that sysctl is
present. Keep `kernel.unprivileged_userns_clone=1` and a positive
`user.max_user_namespaces`. It is expected that a plain host-side non-root
`unshare` remains blocked: only processes carrying the
`offline-reels-collector` label receive AppArmor `userns` permission.

Run the repository's read-only preflight as the non-root Docker user:

```sh
sudo -v
sh scripts/stage10-linux-preflight.sh
```

The script uses the cached credential only for `sudo -n aa-status`; it never
prompts for a password. If the credential is unavailable or expired, preflight
fails closed and asks the operator to run `sudo -v` again.

It checks exact Docker/Compose versions, amd64, cgroup v2, kernel features,
sysctls, Docker seccomp/AppArmor support, the loaded enforcing profile, the
vendored seccomp delta, and standalone Compose validity. It does not build or
start a container and does not modify the host.

## Gate 2: synthetic sandbox acceptance

The Collector seccomp delta allows `chroot` without requiring
`CAP_SYS_CHROOT`. Chromium's namespace sandbox calls `chroot` during its
internal sandbox setup, while the outer container remains non-root with
`cap_drop: ALL` and `no-new-privileges`.

Run only the standalone smoke:

```sh
sh scripts/run-stage10-sandbox-smoke.sh
```

The build may download pinned image/package layers. The resulting runtime has
`network_mode: none`. The one-shot container renders in-memory HTML and exits;
it never contacts Instagram or the staging data plane.

Acceptance requires exit code 0 and one JSON result containing all of these
facts:

- `verified: true` and `container_uid: 10001`;
- AppArmor enforced under `offline-reels-collector`;
- effective capabilities zero for the container and every Chromium process
  sharing its outer `uid_map`;
- `NoNewPrivs=1` for every Chromium process;
- Docker seccomp filter active for every observed Chromium process;
- at least one Chromium child simultaneously has a different `uid_map`, zero
  effective capabilities, and more seccomp filters than the container process;
- no Chromium argument is `--no-sandbox`;
- zero HTTP(S) requests.

Capabilities reported for a Chromium zygote with a different `uid_map` are
relative to its Chromium-created user namespace and do not imply an outer
container capability. Such a zygote alone is not positive sandbox evidence;
the zero-capability nested child described above must also be present.

Also review recent kernel audit messages. Any denial associated with this run
must be understood before acceptance:

```sh
sudo journalctl -k --since '-10 minutes' --no-pager | grep -E 'apparmor|seccomp|DENIED'
```

Do not respond to failure with `seccomp=unconfined`, AppArmor unconfined mode,
`--no-sandbox`, root, `privileged`, `SYS_ADMIN`, host IPC/networking, or a
Docker socket mount. Preserve the safe JSON result and relevant redacted
kernel denial only; never collect a browser profile or environment dump.

## Gate 3: prepare and validate the application ingress later

After gate 2 is formally accepted, create the ignored environment file:

```sh
cp deploy/.env.stage10.example deploy/.env.stage10
chmod 600 deploy/.env.stage10
```

Replace every placeholder with independently generated staging-only values.
Use one Tailscale HTTPS origin for all three browser-facing settings; do not
commit the real hostname:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://<TAILSCALE_HOSTNAME>
FRONTEND_ORIGIN=https://<TAILSCALE_HOSTNAME>
MANAGEMENT_ORIGIN=https://<TAILSCALE_HOSTNAME>
LOGIN_GATEWAY_SESSION_SECRET=<INDEPENDENT_RANDOM_VALUE_AT_LEAST_32_CHARACTERS>
LOGIN_BROWSER_CONTROL_SECRET=<INDEPENDENT_RANDOM_VALUE_AT_LEAST_32_CHARACTERS>
```

`NEXT_PUBLIC_API_BASE_URL` is compiled into the web image, so changing it or
removing the legacy frontend `/videos` route requires a web rebuild.
`MANAGEMENT_ORIGIN` is an existing Backend setting; Stage 10 passes it to the
API without Python-specific staging logic. `COLLECTOR_ACCOUNT_ID` is a staging
UUID, not a credential. Validate the full model without starting it:

```sh
sudo -v
sh scripts/stage10-linux-preflight.sh deploy/.env.stage10
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml config --quiet
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml build stage10-ingress
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml run --rm --no-deps stage10-ingress \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

After the already-approved application/data services are healthy, rebuild only
the web image, recreate API/web, and start only the Stage 10 ingress. These
commands do not enable the Collector, login browser, Serve, or Funnel:

```sh
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml build web
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml up -d --no-deps --force-recreate web api
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml up -d --no-deps stage10-ingress
```

Run local ingress acceptance:

```sh
curl --fail --show-error http://127.0.0.1:13080/
curl --fail --show-error http://127.0.0.1:13080/videos
curl --fail --show-error http://127.0.0.1:13080/health/live
curl --fail --show-error http://127.0.0.1:13080/health/ready
curl --include http://127.0.0.1:13080/api/management/session
sudo ss -lntp
```

`/videos` must return the API catalog JSON, not HTML or a redirect. The
unauthenticated management session request should reach FastAPI and return its
controlled `401`; it must not return a Next.js page. Port `13080` must listen
only on `127.0.0.1`. API, web, PostgreSQL, Redis, and MinIO must have no host
listeners. Do not use `down -v`; the named volumes hold staging data.

If a synthetic or previously seeded video is available, verify Range through
the same ingress without running Collector or Instagram login:

```sh
curl --fail --range 0-1023 -D - -o /dev/null \
  http://127.0.0.1:13080/videos/<VIDEO_ID>/stream
```

Require `206`, `Accept-Ranges: bytes`, and a correct `Content-Range`.

### Tailscale Serve acceptance and public-exposure stop gate

Only after local acceptance, create a tailnet-only HTTPS listener:

```sh
tailscale serve --bg http://127.0.0.1:13080
tailscale serve status
```

From another tailnet device, verify `/`, `/offline`, `/videos`,
`/health/ready`, an unauthenticated `/api/management/session`, frontend catalog
loading, and Range when seeded media exists. Confirm the new Service Worker is
active before treating `/videos` as exclusively Backend-owned; an older
installed worker may retain the retired redirect until its update is accepted.

Confirm the explicit CORS allowlist without adding a wildcard:

```sh
curl --include --request OPTIONS \
  --header 'Origin: https://<TAILSCALE_HOSTNAME>' \
  --header 'Access-Control-Request-Method: GET' \
  https://<TAILSCALE_HOSTNAME>/videos
```

The unauthenticated management request proves routing and the authentication
boundary, but it does not exercise the mutation-only Host/Origin check. That
check remains gated with the authenticated management/login acceptance; do not
create a session or invoke Instagram during this ingress step.

**STOP here.** Serve is tailnet-only. Do not enable Funnel without separate
operator approval and a review of Funnel policy, exposure, and current Serve
status. Serve and Funnel cannot own HTTPS port 443 simultaneously. After that
approval, the documented transition is:

```sh
tailscale serve --https=443 off
tailscale funnel --https=443 --bg http://127.0.0.1:13080
tailscale funnel status
```

These Funnel commands are documentation only and must not be run during this
stage of acceptance.

The `collector` profile is configuration, not authorization to run live
Instagram collection. Before its first use, separately prove profile
ownership/permissions and the hardened Linux login flow, then invoke it as a
bounded one-shot and review its redacted post-run verifier.

### Hardened Instagram login gate

Use only the test Instagram account. Do not start this profile while Collector
is running. Build and start the opt-in login boundary before creating a login
session from the dashboard:

```sh
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml --profile instagram-login \
  build login-browser
docker compose --env-file deploy/.env.stage10 \
  -f deploy/docker-compose.stage10.yml --profile instagram-login \
  up -d --no-deps login-browser login-gateway
sh scripts/stage10-login-preflight.sh deploy/.env.stage10
```

The preflight is read-only. It requires no running Collector, both login
services running as UID/GID 10001 with read-only root filesystems and no host
ports, the browser's hardened security options, the shared named volume, an
account profile owned by 10001:10001 at mode 0700, and the active profile lock.
Only after `STAGE10_LOGIN_PREFLIGHT_OK` may the paired device press **Подключить
Instagram**.

The user enters credentials only inside the remote Chromium view. CAPTCHA,
2FA, checkpoints and challenges are manual stop points. On success the gateway
confirms the authenticated personal Reels boundary and requests graceful
browser shutdown. Verify that `login-browser` has exited before starting
Collector. The gateway may then be stopped without removing its network,
profile or any stateful volume.

## Cleanup and rollback

The synthetic container uses `run --rm`; it leaves no container, network, or
volume. Its locally built image may be retained for evidence/retest. Removing
that image is optional and unrelated to staging data.

Unload the AppArmor profile only when no Collector container exists and the
Stage 10 experiment is being abandoned:

```sh
sudo apparmor_parser -R /etc/apparmor.d/offline-reels-collector
sudo rm /etc/apparmor.d/offline-reels-collector
```

Do not remove or reset any staging volume as part of a browser-policy rollback.
