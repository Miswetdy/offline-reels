# Открытые риски

Готовность проверок — в [STATUS](STATUS.md). Здесь только актуальные ограничения.

| Риск | Что уже сделано / что осталось |
| --- | --- |
| Нестабильная выдача Instagram | Строгая embedded JSON очередь, bounded refresh и дедупликация; текущий source-only live-run 3/3 ещё не принят |
| Сессии, checkpoints, CAPTCHA | Ручной login, закрытые профили и lock; повторная авторизация и последние login-fixes требуют live-проверки |
| Долговечность iOS storage | Cache/IndexedDB reconciliation; eviction, большой объём и длительные сессии требуют реального устройства |
| Память при offline Range | Источники плеера ограничены тремя; worker всё ещё читает целый MP4 для range response |
| Фоновая работа iOS | Просроченная очистка выполняется при следующем запуске/foreground; закрытая PWA не гарантирует работу |
| Viewed lifecycle | Unit/integration проверки есть; отдельная Stage 9 iPhone-приёмка открыта |
| PostgreSQL/MinIO не атомарны | Compensation, immutable keys, leases и reconciliation; потеря объекта вне приложения может оставить metadata |
| Производительность normalizer | Ограниченные retries и отдельный worker; ffmpeg capacity/lease monitoring нужны перед масштабированием |
| Доступ к management | Pairing, CSRF, HttpOnly sessions, rate limits и revoke; потерянное устройство требует отзыва сессии |
| Публичный staging | HTTPS ingress и внутренние service ports; Funnel публичен, секреты и временный доступ требуют контроля |
| Runtime security | Linux sandbox smoke ранее прошёл; после изменения host/browser/policies повторить. Windows seccomp exception не переносить на VPS |
| Эксплуатация | Нет завершённой автоматизации backup/restore, deployment и monitoring; production readiness не заявлена |

Состояние dependency advisories меняется. Старые audit-счётчики не являются
текущей проверкой: перед release нужен новый dependency/security audit.

Профили, cookies, environment files, одноразовые ссылки и raw Instagram
responses не должны попадать в Git, отчёты или логи.
