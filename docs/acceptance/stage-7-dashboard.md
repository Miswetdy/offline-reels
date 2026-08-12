# Stage 7 dashboard acceptance worksheet

Run only against a disposable fixture environment. The pairing code is created
by an operator CLI; enter it locally in the PWA and never record it here.

1. Run the disposable preflight command supplied by that environment. It sets
   the exact random loopback public origin for both management and catalog
   build URLs; do not substitute a different port after preflight.
2. Start its web, API, PostgreSQL, fixture login controller, Collector and
   normalizer services.
3. Create one pairing code locally, enter it in **Подключить это устройство**,
   and confirm that the field clears after success.
4. Confirm the dashboard reports Instagram disconnected, then select
   **Подключить Instagram**. The only accepted navigation is the fixed secure
   fixture `/connect/{id}` route; complete fixture login and return to `/`.
5. Select **Загрузить Reels**. Record only the visible stages: collection,
   video preparation, local download percentage and final `/offline` route.
6. Repeat cancellation once in each stage. Verify server Reels survive, no late
   promise restarts the flow, and the next operation can start cleanly.
7. Revoke the device session, reconnect fixture Instagram, switch offline and
   verify `/` shell/local cleanup and `/offline` playback independently.
8. Stop and remove only the disposable fixture infrastructure.

Expected: there are no UUIDs, technical media fields, raw error codes,
credentials, cookies or capabilities in the visible UI or test record. Never
run a real Stage 4/Funnel/Instagram flow without a separate explicit approval.

## Real-iPhone synthetic fixture staging

After the disposable local fixture passes, a real iPhone may test the same
synthetic Stage 7 services through the separate Funnel override. It uses
`docker-compose.stage7-fixture.yml` plus
`docker-compose.stage7-funnel-fixture.yml`, a unique Compose project, and one
public `STAGE7_PUBLIC_ORIGIN`. Tailscale Funnel terminates public TLS and
forwards only to Caddy bound on Windows loopback; PostgreSQL, Redis, MinIO,
fixture workers and gateway remain unpublished. The public origin must be set before
the web image is built because it is also the catalog API base and the exact
management Host/Origin allowlist.

This phase uses only the fixture gateway and synthetic media. It does not
start a real Stage 4 browser, Instagram, Funnel login, or saved Collector
smoke. Stop Funnel and remove the exact Compose project's containers, network
and volumes immediately after acceptance.

## Recorded acceptance result

The disposable mobile-viewport fixture and synthetic iPhone Stage 7 PWA
acceptance passed; their fixture resources were removed. Stage 4 real remote
login passed as a separate acceptance. The retained-profile Stage 4 →
Collector → normalizer → PWA chain is not accepted on Windows Docker Desktop:
an isolated non-root Chromium preflight, including direct private CDP, closed
before browser readiness because of sandbox incompatibility. Re-run that chain
on Linux staging or a real server. `--no-sandbox`, root browser, privileged
containers and `SYS_ADMIN` were not used.
