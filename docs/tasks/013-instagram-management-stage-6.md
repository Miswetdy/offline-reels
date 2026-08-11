# TASK-013: Protected Instagram Collector management API

## Scope

Stage 6 adds device pairing, protected management session/cookie/CSRF checks,
safe Instagram status, login-session commands, queued collection commands,
normalization counters and durable auto-collection settings. It does not add a
dashboard UI, scheduler, live Instagram execution or worker startup from API.

## Contract

- `POST /api/management/pairing/exchange`; `GET`/`DELETE /api/management/session`
- `GET /api/instagram/status`
- `POST`/`GET`/`cancel` login sessions
- `POST`/`GET`/`cancel` collection runs
- `GET /api/instagram/normalization-status`
- `GET`/`PUT /api/instagram/collection-settings`

Every management mutation requires exact configured HTTPS Origin, session-bound
CSRF header and an ASCII bounded `Idempotency-Key`. The CLI, rather than a
public endpoint, creates pairing challenges and revokes all account sessions.
Responses use a stable safe envelope with a correlation ID. Launch capability
is returned exactly once with `Cache-Control: no-store`; it has no arbitrary
return URL and never becomes a stored result.

## Explicit follow-up

The next stage supplies the dashboard UI. Auto-collection remains disabled by
execution design even when its stored setting is enabled: no scheduler exists.
