# ADR 005: Один Serwist worker для PWA

Принято. `@serwist/turbopack`, Serwist и esbuild собирают worker
из `apps/web/app/sw.ts`; production регистрирует `/serwist/sw.js` со scope `/`.

Revisioned precache включает static assets, `/`, `/offline` и manifest.
Navigation fallback ограничен пользовательскими offline-маршрутами.
API, management, streams и бывший frontend `/videos` не являются shell cache.

Shell cache отделён от media cache и IndexedDB. Новый worker активируется
только по кнопке «Обновить»: SKIP_WAITING, controllerchange и один reload.
Offline library сохраняется. Development worker не регистрирует.
