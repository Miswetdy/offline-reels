# ADR 009: Отдельный Collector image

Принято. Docker target `collector` содержит optional Playwright/yt-dlp,
Chromium, ffmpeg/ffprobe и tini. API image не содержит browser runtime.

Контейнер non-root; persistent profile отделён от временного workspace.
Entrypoint требует явной команды: fixture, sandbox-smoke, identity-diagnostic,
modal-lifecycle-diagnostic, live или handoff. По умолчанию live не стартует.

Synthetic fixture с PostgreSQL/MinIO доказывает упаковку и persistence;
он не доказывает работоспособность Instagram.
Stage 10 runtime security — [ADR 015](015-hardened-linux-chromium-collector.md).
