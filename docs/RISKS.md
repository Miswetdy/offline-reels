# Technical Risks

This document tracks known technical risks and mitigation plans.

---

# Risk 1: iOS PWA storage limitations

## Problem

Browser storage on iOS may have limitations.
The system can restrict available storage or remove cached data.

## Impact

Users may lose prepared offline videos.

This directly affects the main product value.

## Mitigation

The baseline offline flow was confirmed on an iPhone 16 Pro running iOS 26.5.2: a 13,864,238-byte video survived a PWA restart and played in Airplane Mode. Deletion also persisted across restart.

The following risks remain open:
- iOS can still evict origin data under storage pressure or according to its storage policy;
- behavior near the storage quota has not been measured;
- the capacity and performance of storing a large number of videos have not been measured;
- a cleanup policy is still required before production implementation.

## Status

Partially mitigated: basic offline storage behavior is confirmed; quota, eviction, and large-library behavior remain open.

---

# Risk 2: Background synchronization limitations

## Problem

PWA applications cannot guarantee background execution when closed.

## Impact

The application cannot rely on automatic background downloads.

## Mitigation

Design synchronization as resumable:
- server prepares content independently;
- client downloads when opened;
- interrupted downloads can continue.

## Confirmed limitation

The PWA offline flow works after the user opens the app, but the experiment does not provide or rely on background synchronization while the PWA is closed. Background downloads and synchronization must remain resumable and user-initiated when the app is opened.

## Status

Open.

---

# Risk 3: Instagram automation instability

## Problem

Instagram automation may break because of:
- UI changes;
- expired sessions;
- CAPTCHA;
- rate limits;
- account restrictions.

## Impact

The system may stop collecting new Reels.

## Mitigation

- isolate Instagram Collector;
- implement clear error handling;
- store session status;
- make collector replaceable.

## Status

Open.

---

# Risk 4: Video storage and synchronization complexity

## Problem

Large video files require careful handling.

Potential issues:
- storage limits;
- duplicate downloads;
- interrupted transfers;
- outdated files.

## Mitigation

Implement:
- file validation;
- download states;
- retry mechanisms;
- storage cleanup policies.

## Status

Open.

---

# Risk 5: Synchronization conflicts

## Problem

The system needs to define behavior when:
- user watches videos offline;
- multiple devices are used;
- local state conflicts with server state.

## Mitigation

Define synchronization rules before production implementation.

## Status

Open.

---

# Risk 6: PostgreSQL and object storage are not one transaction

## Problem

Creating a video requires an object in MinIO and a metadata record in PostgreSQL. These systems do not share an atomic transaction.

## Mitigation

TASK-003 creates or verifies the object first and then upserts metadata by the deterministic object key. Repeating the seed repairs a missing object or missing database record without creating duplicates.

## Remaining limitation

If PostgreSQL fails after a successful upload, an orphan object can remain. Automatic orphan cleanup is outside TASK-003. PostgreSQL can also retain ready video metadata after its MinIO object is deleted; the catalog can therefore list a video whose stream is unavailable. The streaming endpoint returns the safe `video_object_not_found` error without exposing storage internals. The frontend turns that media failure into a terminal per-card state, clears its source and does not retry or fall back to Backend storage, but it does not automatically reconcile PostgreSQL and MinIO.

## Status

Accepted limitation for the first vertical slice.

---

# Risk 7: Long feed sessions can increase browser memory use

## Problem

TASK-004 keeps every loaded feed item and its `video` element mounted to validate scroll-snap and playback UX before introducing virtualization. Long sessions can therefore increase DOM, media metadata and browser memory usage.

## Mitigation

- The frontend requests only five metadata records per page.
- Only the active player and its next neighbor receive a stream URL. The active player uses `preload="auto"`; the next player uses `preload="metadata"`; all other mounted cards have no media source and use `preload="none"`.
- Only one player is allowed to play at a time.
- The next page is fetched only when the sentinel approaches the viewport.

## Remaining limitation

Browser `preload` is advisory: Chromium can make open-ended Range requests even for metadata preload. The active-plus-next media window limits the number of stream URLs to two, but full DOM virtualization and removal of distant cards remain outside TASK-004. Their need must be measured on a real iPhone before introducing more complex scroll and ref management.

## Status

Open.

---

# Risk 8: Mobile autoplay can be refused by the browser

## Problem

Browser autoplay policies and device conditions can reject `HTMLMediaElement.play()` even for a muted video.

## Mitigation

The feed begins muted and catches every `play()` rejection. A playback error is local to that item; the rest of the feed remains usable through scrolling and native controls.

## Status

Accepted limitation for TASK-004; validate manually in a desktop browser and later on iPhone.

---

# Risk 9: Input media compatibility

## Problem

The `.mp4` container extension does not guarantee browser-compatible codecs, profiles or encoding parameters. The earlier playback issue was reproduced only with particular third-party test MP4 files, not with real Instagram Reels. Real Reels passed the manual feed smoke scenario in both Chrome and Yandex Browser; backend streaming, cursor pagination and HTTP Range responses remain confirmed correct.

## Mitigation

Future ingestion must validate incoming media. If validation identifies incompatible output, the downloader or ingestion pipeline may need normalization or transcoding. The safe target format for MVP must be defined in a separate task; transcoding is outside TASK-004.

## Status

Open, non-blocking for TASK-004. Safari on iPhone and long media sessions still need a separate compatibility validation stage.

---

# Risk 10: Local download queue and browser storage behavior

## Problem

TASK-005 Block 2 stores an MP4 through one `TransformStream` and one Cache Storage consumer to avoid the extra buffering risk of `ReadableStream.tee()`. Browser Cache Storage implementations can still use substantial internal memory or storage while handling a large response, especially on iOS. IndexedDB and Cache Storage remain non-transactional, and the queue guarantees one worker only within one browser tab.

## Mitigation

- The downloader validates type and size, writes no per-chunk progress to IndexedDB, and marks `completed` only after cache validation.
- Cache cleanup and idempotent startup reconciliation compensate for failed or interrupted writes. A cache entry is considered owned only by a validated completed metadata record; zero-byte, invalid, orphan and failed-record media is removed.
- Queue concurrency is one. Abort and quota failures pause it; queued work requires explicit user continuation after reload or network recovery.
- Storage pre-checks use a 1.2 multiplier and a desired 50 MiB reserve, but estimates remain approximate.

## Remaining limitation

Multiple tabs can still create competing queue controllers because `navigator.locks` is deliberately deferred. There is no background download or automatic recovery, and iPhone memory/quota acceptance has not been completed. Large-file memory behavior, Cache Storage eviction, quota-exceeded recovery and long sessions must be measured manually on Chrome and an iPhone.

## Status

Open, accepted for TASK-005 Block 2.

Known dependency advisories:

- Next.js 16.2.11 currently resolves optional sharp 0.34.5, affected by GHSA-f88m-g3jw-g9cj.
- The application does not currently process untrusted images through sharp, so the known exploitation path is not used.
- Next.js also resolves nested postcss 8.4.31, affected by GHSA-qx2v-qp2m-jg93 and GHSA-6g55-p6wh-862q.
- The application does not accept or serialize untrusted user CSS.
- `npm audit` and `npm audit --omit=dev` currently report three high findings (sharp plus the two PostCSS advisories) and no critical finding.
- npm audit fix --force is prohibited because it proposes an incompatible downgrade to Next.js 9.3.3.
- Dependency remediation is tracked separately and must be completed before production deployment.

---

# Risk 11: Service Worker offline media Range slicing memory cost

## Problem

Browser manual smoke after TASK-005 Block 5.1 confirmed that `<video>` sends a `Range` header on its first offline media request. A full-response-only handler therefore prevented playback. Block 5.2 now implements single-range responses by reading a cached MP4 fully into worker memory and slicing it.

## Mitigation

`/offline` reconciles local data before listing it, never falls back to Backend media, and supplies only validated synthetic URLs to the active-plus-next media window. The worker accepts only same-origin GET/HEAD requests with exact UUID paths, reads only `offline-reels-media-v1`, and returns a controlled miss rather than contacting the network. It supports a strict single `bytes` range and returns `416` instead of fabricating multipart or invalid partial responses.

## Remaining limitation

The parser and response headers are covered by unit tests, and the handler reads a cached body only once per request without cloning, rewriting or retaining slices. It still materializes the full MP4 in Service Worker memory before slicing. Browser seek behavior, repeated seek memory pressure, iPhone Safari behavior, quota eviction and long-session stability remain unconfirmed and are explicit Block 6.3 acceptance checks. Multipart ranges remain unsupported by design.

## Status

Open, accepted for TASK-005 Block 5.2 pending manual desktop and iPhone validation.

---

# Risk 13: Service Worker application-shell lifecycle

## Problem

TASK-005 Block 4.1 precaches the production application shell so a previously visited `/offline` route can reload without a network connection. Service Worker updates are asynchronous, browser storage can still be evicted, and the shell does not yet serve cached MP4 requests.

## Mitigation

- One Turbopack-built Serwist worker is served at `/serwist/sw.js` with scope `/` and automatic registration by `SerwistProvider`.
- The Turbopack glob manifest contains static assets but not literal App Router page URLs. `/offline`, `/videos`, and `/manifest.webmanifest` are therefore explicitly precached with deterministic SHA-256 revisions derived from application-shell build inputs; the fallback cannot bind until the `/offline` entry exists.
- Navigation fallback is restricted to same-origin `GET /offline`; the Backend API, video streams and media are not runtime-cached.
- Serwist's precache cleanup is isolated from `offline-reels-media-v1`; local-library delete/clear also targets only that media cache.
- `reloadOnOnline=false` prevents a connection change from forcing an application reload.

## Remaining limitation

Development disables Service Worker registration. Production shell reload and offline media playback must be manually verified on desktop and iPhone. The remaining media-delivery limitations are full-file worker-memory slicing, unsupported multipart ranges, and unconfirmed long-session behavior. Native `esbuild` must remain available for Windows production builds.

## Status

Open, accepted for TASK-005 Block 4.1.

---

# Risk 14: Offline navigation and Service Worker updates

## Problem

The network hint from `navigator.onLine` is not a guarantee that the Backend is reachable. Service Worker updates can wait while several tabs remain open, and `/videos` must not present an old server feed as current content when offline.

## Mitigation

- `/videos` precaches only its application shell and keeps the Backend catalog request `cache: "no-store"`.
- A failed catalog request that is classified as a fetch-level network failure, or a request while the browser reports offline, renders a controlled state with an explicit link to `/offline`; there is no redirect. This avoids relying on `navigator.onLine` as an authoritative reachability signal.
- `/offline` is the sole navigation fallback. Unknown routes do not receive the offline-library document.
- The network indicator is informational and does not infer downloaded-video availability.
- `skipWaiting` is disabled and `reloadOnOnline=false`; the application does not force worker updates or page reloads.
- Shell cache lifecycle remains isolated from `offline-reels-media-v1`.

## Remaining limitation

Two open tabs can stay on different shell versions until the older clients close. There is deliberately no update banner, cross-tab coordination, forced activation or background synchronization. Manual desktop and iPhone lifecycle testing remains required.

## Status

Open, accepted for TASK-005 Block 4.2.

---

# Risk 12: Local cleanup is not cross-tab synchronized

`/offline` deletes media cache data before IndexedDB metadata and refreshes its own catalog after each operation. Reconciliation compensates if the metadata step fails, but another open tab will not receive a live update. Browser storage estimates can also remain nonzero or update with delay after deletion. This is accepted for TASK-005 Block 3.3; cross-tab synchronization is deferred.

Next.js 16.2.11 transitively includes sharp 0.34.5 and postcss 8.4.31,
which remain reported by npm audit.

No force downgrade or unverified dependency override is applied.

Current application does not process untrusted user images through Sharp,
so practical exposure is limited for the local MVP.

Before public production deployment:
- upgrade to a compatible Next.js release containing patched transitive versions;
- or apply an officially supported dependency resolution;
- rerun npm audit and production smoke tests.
