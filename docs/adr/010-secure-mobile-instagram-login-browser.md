# ADR 010: Ручной login через серверный Chromium

Принято. Пользователь вводит пароль, 2FA и CAPTCHA в реальный Instagram
через защищённый remote-browser viewer. Бизнес-API не получает форму пароля;
gateway/VNC передаёт ввод, но не журналирует и не сохраняет его.

Одноразовый короткоживущий grant и подписанная Secure HttpOnly cookie
защищают HTTPS/WebSocket relay с проверкой Host/Origin.
VNC, X11, CDP, profile и browser controller не публикуются.
После подтверждения Reels readiness доступ закрывается; профиль сохраняется.

Login сам не создаёт collection run и не нормализует видео.
Нельзя обходить CAPTCHA или экспортировать cookies.
Актуальная Linux-реализация — [ADR 017](017-hardened-stage10-instagram-login.md);
ранний Windows seccomp exception не предназначен для production.
