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

- Full-screen commit is tied to geometry rather than callback timing. It atomically marks the prior committed card and immediately checks cached intersection/root geometry, so either callback order starts one offscreen preparation. The card progresses from reset-required through reset-in-flight to prepared-at-zero, and becomes visible only after a decodable first frame. Device acceptance must still confirm WebKit retains that prepared frame offscreen.

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
- The active player and its immediate previous/next neighbours receive stream URLs. The active player uses `preload="auto"`; both neighbours use `preload="metadata"`; all other mounted cards have no media source and use `preload="none"`.
- Only one player is allowed to play at a time.
- The next page is fetched only when the sentinel approaches the viewport.

## Remaining limitation

Browser `preload` is advisory: Chromium can make open-ended Range requests even for metadata preload. Post-iPhone hardening block 2 keeps at most three stream URLs—previous/current/next—with metadata preload on both neighbours. Full DOM virtualization and removal of distant cards remain outside TASK-004. Their need must be measured on a real iPhone before introducing more complex scroll and ref management.

## Status

Open.

---

# Risk 8: Mobile autoplay can be refused by the browser

## Problem

Browser autoplay policies and device conditions can reject `HTMLMediaElement.play()`, especially the first audible attempt in an installed iOS PWA.

## Mitigation

The native feed retains muted-first behavior. Reels deliberately begins unmuted and catches every `play()` rejection. An audible `NotAllowedError` leaves the active Reels item paused and unmuted with an explicit Play button; it never performs a hidden muted fallback or retries in a loop. A user gesture can then request the same active item with sound. Other playback errors remain local to their item, while the rest of the feed stays usable.

## Status

Accepted limitation for TASK-004; validate manually in a desktop browser and later on iPhone.

---

# Risk 9: Input media compatibility

## Problem

The `.mp4` container extension does not guarantee browser-compatible codecs, profiles or encoding parameters. The earlier playback issue was reproduced only with particular third-party test MP4 files, not with real Instagram Reels. Real Reels passed the manual feed smoke scenario in both Chrome and Yandex Browser; backend streaming, cursor pagination and HTTP Range responses remain confirmed correct.

## Mitigation

The iPhone acceptance confirmed the risk: a VP9 MP4 did not play, while an
H.264 MP4 encoded as `yuv420p` with `faststart` did. Stages 1A–1B now apply a
typed ffprobe/decode-validation/remux-or-transcode boundary to every new
`seed_video` ingest before it reaches MinIO or PostgreSQL. The stored object is
always a verified normalized MP4, and a database failure after upload triggers
best-effort MinIO cleanup.

## Status

Open. Historical VP9/incompatible objects are intentionally not migrated and
must be deleted/reseeded manually. Long sessions and storage-pressure behavior
still need validation after normalized ingestion.

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

`/offline` reconciles local data before listing it, never falls back to Backend media, and supplies only validated synthetic URLs to the previous/current/next media window. The worker accepts only same-origin GET/HEAD requests with exact UUID paths, reads only `offline-reels-media-v1`, and returns a controlled miss rather than contacting the network. It supports a strict single `bytes` range and returns `416` instead of fabricating multipart or invalid partial responses.

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
- A waiting worker is surfaced through Serwist's lifecycle API. The user explicitly starts the documented message-based `SKIP_WAITING` activation, and only its subsequent `controllerchange` reloads once; the update UI does not access Cache Storage or IndexedDB.

## Remaining limitation

Development disables Service Worker registration. Production shell reload and offline media playback must be manually verified on desktop and iPhone. The remaining media-delivery limitations are full-file worker-memory slicing, unsupported multipart ranges, and unconfirmed long-session behavior. Native `esbuild` must remain available for Windows production builds.

## Status

Open, accepted for TASK-005 Block 4.1.

---

# Risk 15: iPhone PWA, storage eviction, and Range memory acceptance

## Problem

Desktop Chromium verification does not establish iPhone Safari/WebKit behavior. Service Worker control, Home Screen installation, Cache Storage/IndexedDB eviction, `StorageManager` diagnostics, video Range requests, app backgrounding, and the current full-file worker-memory slicing strategy can behave differently under iOS memory pressure. A LAN HTTP address is not a dependable secure context for the installed-PWA path.

## Mitigation

- Real-device acceptance uses one HTTPS Tailscale Funnel origin. `NEXT_PUBLIC_API_BASE_URL` is validated and required in the client, and `FRONTEND_ORIGIN` is configured for that same origin; neither value is a secret.
- The standalone manifest starts at `/offline`, and the worker serves the same-origin offline shell and `/offline-media/{id}` without a Backend fallback.
- The local summary presents exact library bytes, approximate origin usage/quota when available, and the non-invasive `navigator.storage.persisted()` result. It does not promise that iOS will retain data or request persistence automatically.
- Safari and the installed Home Screen PWA use distinct offline-storage contexts; users must install first and download media inside the installed PWA.
- Safe-area-aware controls, `100dvh`, `playsInline`, native scroll-snap, visibility handling, and previous/current/next source cleanup are in place. Native `/videos` remains muted-first; Reels starts with normal sound and leaves an iOS-blocked audible startup paused for an explicit user Play, without a silent workaround. The current window improves return to the previous item while bounding sources to three.
- `/offline` now uses the shared feed's Reels-like mode. One tokenized pointer state machine separates tap, centre hold, symmetric outer-10% edge hold and movement cancellation without `preventDefault` or pointer capture. Only tap-pause exposes controls; move/scroll/pointer cancellation can restore a still-active centre hold, while active-item and lifecycle cancellation cannot. Reels-only `touch-action: pan-y`, callout/selection suppression and drag prevention do not apply to `/videos`. The lower metadata → progress → glass-navigation layout uses scoped backdrop blur with an opaque fallback; its safe-area sizing and WebKit rendering still need device acceptance.
- The production startup path attempts guarded playback on `HAVE_METADATA` or `loadedmetadata`, which avoids the observed WebKit metadata/suspend deadlock without relying on `canplay`. A nonzero reset still waits for current `seeked`. Effective active selection only pauses/plays cards and is reversible while a drag is partial. A distinct commit requires ratio ≥ 0.999 and card/root geometry within 2 CSS px; only the previous committed card may reset after its ratio-zero, fully offscreen exit. A post-commit rapid return waits for the same guarded seek, while a pre-commit reversal retains its paused position.

## Remaining limitation

The required iPhone acceptance has run, but Browser quota and persistence APIs
remain hints, not retention guarantees; iOS may evict storage. Single-range
delivery materializes a complete MP4 in worker memory per request, so
20-minute and 50-swipe tests remain important targets. Multipart Range,
background download, and long-session behavior after a controlled shell update
remain follow-up work. For AAC MP4, iOS WebKit can briefly freeze or jump its
media clock at the 1×↔2× edge-hold boundary even with complete buffering; the
same experiment was observed through both Service Worker and Blob sources, and
short GOP/B-frames were not the root cause. A no-audio variant was much
smoother, while `preservesPitch=false` helped only partly and distorted speech.
The MVP therefore keeps normal audio and standard pitch preservation. Forced
short-GOP/no-B-frames transcoding is rejected because it adds storage, CPU and
quality costs without a complete fix; a future native AVPlayer remains the
full solution. Re-downloading unchanged server media does not by itself alter
this WebKit AAC limitation. Pointer Events, safe-area layout and gesture arbitration still
require block 4 testing in the installed iPhone PWA; desktop/JSDOM tests cannot
prove native scroll and touch behavior.

## Status

Open for long-session and post-normalization re-acceptance.

---

# Risk 14: Offline navigation and Service Worker updates

## Problem

The network hint from `navigator.onLine` is not a guarantee that the Backend is reachable. Service Worker updates can wait while several tabs remain open, and `/videos` must not present an old server feed as current content when offline.

## Mitigation

- `/videos` precaches only its application shell and keeps the Backend catalog request `cache: "no-store"`.
- A failed catalog request that is classified as a fetch-level network failure, or a request while the browser reports offline, renders a controlled state with an explicit link to `/offline`; there is no redirect. This avoids relying on `navigator.onLine` as an authoritative reachability signal.
- `/offline` is the sole navigation fallback. Unknown routes do not receive the offline-library document.
- The network indicator is informational and does not infer downloaded-video availability.
- `skipWaiting` is disabled and `reloadOnOnline=false`. A waiting update remains inert until the user selects **«Обновить»**; Serwist then activates only that waiting worker through its supported message API and the page reloads once after `controllerchange`.
- Shell cache lifecycle remains isolated from `offline-reels-media-v1`.

## Remaining limitation

Two open tabs can stay on different shell versions until a user accepts the update in each relevant client; there is no cross-tab coordination or background synchronization. Manual desktop and iPhone lifecycle testing remains required.

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

## Production-like VPS foundation

- The production Compose foundation keeps PostgreSQL, Redis and MinIO private, but it does not yet include automated backup, restore, monitoring, or a deployment script. A failed database migration therefore requires a deliberate operational rollback or restore procedure.
- PostgreSQL metadata and MinIO objects still do not share a transaction. The MinIO bootstrap job guarantees bucket/user setup, not cross-store consistency after an interrupted seed or infrastructure failure.
- Caddy is expected to preserve HTTP Range headers unchanged. Public deployment must still verify `206`, `Content-Range`, and playback through the real domain before iPhone acceptance.
- The web client compiles `NEXT_PUBLIC_API_BASE_URL` at image-build time. An incorrect public API origin requires a new web image; it cannot be corrected by changing only a running container environment variable.
- Production secrets initially remain in a VPS-local Compose env file. It is ignored by Git and must be permission-restricted; Docker secrets and off-VPS backups are follow-up hardening work.

## Public Tailscale Funnel staging

- Funnel is a public internet endpoint, not an authenticated private preview.
  The current MVP has no application authentication, so it must use fresh
  staging-only secrets, publish only Caddy, and be switched off after testing.
- The Windows host must stay online and connected to Tailscale. It is not a
  reliable long-running deployment target.
- `NEXT_PUBLIC_API_BASE_URL` is baked into the web image. Changing a Funnel
  hostname requires rebuilding the web image and matching `FRONTEND_ORIGIN`.
- Funnel terminates TLS before local Caddy. Public iPhone testing must still
  verify service-worker scope, CORS, and Range streaming over the final
  `*.ts.net` hostname.
