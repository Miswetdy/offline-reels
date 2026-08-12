# TASK-014: PWA Instagram dashboard (Stage 7)

## Scope

The canonical `/` PWA dashboard joins the protected Stage 6 management API to
the existing local offline-library queue. It does not start Instagram,
Collector, normalizer, Funnel, or a PWA by itself.

- An unpaired device receives an operator-created one-time code and exchanges
  it directly with the management API. The code is input-only: it is cleared
  after success and is never put in storage, a URL, analytics, or logs.
- The HttpOnly management cookie stays same-origin. The client keeps the CSRF
  capability only in memory, clears it after a revoked/expired session, and
  gets a fresh capability from `GET /api/management/session` after a PWA
  restart.
- Instagram connection is created through the Stage 6 command. A one-time
  launch capability is accepted only for the fixed same-origin HTTPS
  `/connect/{uuid}#…` Stage 4 gateway route; it is never rendered, saved, or
  reused as a return URL. Stage 4 completes only by returning to fixed `/`.
- A connected device starts a bounded collection run, waits for confirmed
  normalization readiness, reads every existing video-catalog cursor page, and
  passes the deduplicated result to the unchanged sequential local queue.
- Collection and local-download percentages use confirmed counters. The
  normalization stage intentionally has no percentage because Stage 6 exposes
  no per-run denominator.
- Cancelling aborts client polling and prevents late continuations. It asks
  Stage 6 to cancel a collection, stops normalization waiting without touching
  server jobs, or uses the existing `cancelBatch` during local download.

## Security and offline policy

Management requests are relative same-origin requests with `credentials:
"same-origin"` and `cache: "no-store"`. Serwist has no runtime cache and its
route policy explicitly forbids management, pairing, login capability, CSRF and
collection paths. The shell still precaches `/` and `/offline`; while offline
the dashboard displays only the disconnected state, disables management actions
and retains local cleanup and offline playback.

No dashboard text renders account/session/run/login IDs, shortcodes, object
keys, media bytes/codecs, backend reason codes, HTTP statuses, or raw errors.
`scheduler_active` remains false, so the dashboard displays only “Автопополнение
будет доступно позже”.

## Disposable fixture/manual acceptance

The implementation includes unit/API compatibility tests and a combined web +
API + PostgreSQL + MinIO + fixture gateway + fixture Collector + fixture
normalizer mobile-viewport E2E composition. The automated acceptance passed
using synthetic catalog media only; it never contacted Instagram or Funnel.
The composition uses its own project resources and removes its containers,
network and volumes after acceptance.

The remaining operator-assisted manual sequence is: preflight; start the
disposable services; create a pairing code locally; enter it in the PWA;
complete fixture login; observe fixture collection and normalization; verify
durable local completion and `/offline`; exercise cancellation, reconnect and
device revoke; then clean up the exact disposable project. Do not paste a
pairing code, launch capability, credential, cookie or token into chat.

For real-device coverage before any live Instagram test, the same synthetic
fixture may be published temporarily through a loopback-only Caddy and a
separately authorized Tailscale Funnel. It remains a distinct Compose project,
uses fixture-only login/Collector/normalizer behavior, and is removed together
with the Funnel after acceptance.

The disposable fixture and synthetic iPhone Stage 7 PWA acceptance passed.
Stage 4 real remote login passed separately. The full retained Stage 4 profile
→ Collector → normalizer → PWA chain was attempted on Windows Docker Desktop
but is not accepted: isolated non-root Chromium, including direct private CDP,
closed before browser readiness because of sandbox incompatibility. Repeat it
on Linux staging or a real server. `--no-sandbox`, root browser, privileged
containers and `SYS_ADMIN` were not used; Stage 4 Risk 17 remains open.
