# ADR 017: Linux login и общий профиль

Принято. Opt-in login-browser/login-gateway используют защищённый remote
login contract. Browser и Collector работают с одним pinned Chrome for Testing
и одним profile volume, UUID account directory и atomic lock.
Profile принадлежит 10001:10001, mode 0700. Одновременный доступ запрещён.

Browser использует те же non-root/seccomp/AppArmor ограничения, что Collector.
Gateway не монтирует профиль. CDP loopback; VNC/controller внутренние.

Verification-навигация в /reels/ выполняется не более одного раза за сессию.
Authenticated account pages вне Reels остаются видимыми для ручного решения;
только Reels boundary завершает подключение. После успеха browser закрывается,
profile сохраняется для Collector.

Профиль другой версии браузера нельзя force-open/downgrade.
Guarded reset требует явного подтверждения и отсутствия активной login session;
сбрасывается только выбранный account profile, account становится disconnected.
Многопользовательский browser scheduler этим решением не вводится.
