# ADR 019: Operator handoff в том же Chromium process

Принято. Opt-in collector-handoff приостанавливается до collection input,
download и persistence. Защищённый gateway показывает оператору private noVNC
того же процесса; confirm продолжает работу без перезапуска браузера.

Доступ: одноразовый token, подписанная HttpOnly cookie, fixed HTTPS Host/Origin,
короткий TTL. State volume хранит безопасное состояние и token hash;
raw grant существует временно в private 0600 file и удаляется при активации.
VNC/CDP/profile/controller не публикуются.

Cancel/expiry/disconnect закрывают браузер без запуска сбора.
После confirm действуют durable commit и strict candidate contracts;
актуальный source-only advance описан в [ADR 022](022-embedded-reels-feed-candidate-queue.md).
