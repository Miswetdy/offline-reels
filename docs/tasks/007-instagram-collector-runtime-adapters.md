# TASK-007: Instagram Collector Stage 3A runtime adapters

## Goal

Implement optional production adapter boundaries without enabling a live
Collector run.

## Implemented

- Lazy Playwright persistent-profile feed control with centre-video identity,
  controlled scroll and two-sample transition confirmation.
- Conservative account-derived profile lock and runtime roots that cannot be a
  repository, home/drive root, repository child or overlap each other.
- Minimal, per-attempt in-memory Instagram session CookieJar; its separate
  yt-dlp HTTP CookieJar copy is cleared after every attempt.
- Session-first yt-dlp adapter with no cookiefile, browser-cookie import,
  Authorization/Cookie headers or anonymous fallback.
- ffprobe source validator that accepts only a real `mp4` container reported
  by ffprobe (not a filename suffix), and prefix-bound MinIO source adapter.
- Local synthetic `file://` browser fixture and fake downloader/MinIO tests.

## Security boundary

The ordinary API dependency set and FastAPI startup do not import Playwright or
yt-dlp. The optional `collector` extra is needed only by a future operator
runtime. No browser profile, cookie, media URL, header or page content is
persisted or logged.

Prepare the optional local runtime explicitly; this does not create a live run:

```powershell
uv --directory apps/api sync --extra collector --frozen
$env:PLAYWRIGHT_BROWSERS_PATH = '.playwright-browsers'
uv --directory apps/api run playwright install chromium
```

## Not implemented

There is no live command, Instagram login, account-connection flow, scheduler,
worker, normalizer worker, public Collector API or frontend UI. Live Stage 3B
requires separate review and explicit operator authorization.
