# Technical Risks

---

# Risk 18: Normalizer publication is a cross-system saga

## Problem

MinIO final-object publication and PostgreSQL `videos`/Reel/job completion are
not one distributed transaction. Worker loss can also leave a running lease or
a source object after a durable success.

## Mitigation

Stage 5 uses immutable SHA-256 final keys, validates final size/hash/media
before the database transaction, and removes a final object only when the
current attempt created it and no durable `videos` reference exists. Existing
objects are verified and never overwritten/deleted. Each job has a bounded lease
and attempt-owned staging prefix; reconciliation records stale history, retries
at most three attempts, cleans staging best-effort, and retries only ready-source
cleanup. Source deletion starts strictly after the ready/completed commit.

## Remaining limitation

Object-store availability and ffmpeg capacity limit throughput. The worker
defaults to one concurrent process; scaling requires lease/capacity monitoring.

## Status

Mitigated by Stage 5; production operational acceptance remains pending.

This document tracks known technical risks and mitigation plans.

---

# Risk 17: Stage 4 Windows runtime is not production-hardened

Stage 10 now prepares, but has not yet executed, the Linux mitigation. The
Collector launch explicitly enables Chromium sandboxing; its Ubuntu staging
Compose uses a pinned default-deny seccomp profile with only the Playwright
user-namespace syscall delta and an enforcing Collector-only AppArmor profile
with `userns,`. A standalone networkless smoke will require `/proc` evidence
for the Chromium user namespace and its own seccomp-BPF layer before any
application deployment. Risk 17 remains open until that proof passes on the
actual Ubuntu 24.04 staging kernel; repository/static checks are not runtime
evidence.

The Stage 4 browser UX and account connection were accepted on Windows Docker
Desktop with iPhone Safari. That functional evidence does not prove a hardened
Linux deployment. The current Windows-compatible Compose configuration gives
`seccomp=unconfined` only to `login-browser`, which remains UID 10002; gateway,
Collector, PostgreSQL and Tailscale do not receive that exception. Raw
VNC/CDP/X11 are still internal and `--no-sandbox`, root browser, privileged
containers, `SYS_ADMIN`, automatic login and automatic CAPTCHA solving remain
forbidden.

The Ubuntu 22.04 VirtualBox experiment passed host preflight and static
container assertions, but did not complete the synthetic Chromium runtime
check. It is therefore neither a production-readiness proof nor a reason to
weaken the future Linux sandbox further. The sensitive Windows Docker profile
was not and must not be copied to Linux.

## Mitigation

- Keep `seccomp=unconfined` scoped to the current Windows `login-browser`
  only; never add `--no-sandbox`, a root browser, privileged container,
  `SYS_ADMIN`, host VNC/CDP/X11 ports or automated
  credential/CAPTCHA handling.
- On Linux staging, load only the enforcing `offline-reels-collector`
  AppArmor profile, keep the Ubuntu-wide userns restriction enabled, and run
  the Stage 10 read-only preflight plus networkless synthetic smoke before
  enabling public login or live collection.
- Treat remote keyboard/pointer transport as a credential-input trust boundary:
  it must not log, inspect or retain events. The business API must continue to
  receive neither credentials nor cookies.
- Keep the Funnel disabled outside an active operator test and verify public
  DNS/HTTPS from the phone network before issuing a link.

## Status

Open. Stage 4 real remote login is functionally accepted on Windows Docker
Desktop but is not production-hardened. The full retained-profile → Collector
→ normalizer → PWA chain is not accepted there: isolated non-root Chromium,
including direct private CDP, closed before browser readiness under Docker
Desktop. Stage 10 repository controls are ready, but their synthetic runtime
proof has not run on the Ubuntu staging host. No sandbox-bypass workaround was
applied; the server remains gated on that proof.

---

# Risk 16: remote-login profile and public HTTPS exposure

The Chromium profile is sensitive authenticated state and a mobile display link
is a capability. Stage 4 stores only a token hash and compact status; links are
single-use, time-limited and operator-created. The profile is in a separate
volume and is never exported. Secure cookies, Host/Origin/WebSocket checks and
CSP protect the gateway; VNC/CDP/X11 are not published. Credentials are not
accepted by application forms or persistence, but remote VNC necessarily
relays keyboard/pointer events and is therefore inside the trusted browser
infrastructure boundary; it must not log, inspect or retain them. A future
management API must authenticate link creation. Final acceptance requires a
Linux host with unprivileged user namespaces: Docker Desktop configurations
that block `unshare(CLONE_NEWUSER)` cannot safely run the Chromium sandbox.

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
- use explicit account and Reel pipeline states with safe reason codes;
- stop on checkpoint, CAPTCHA, reauthentication or temporary limits;
- keep browser profiles and the minimal in-memory CookieJar outside database,
  logs and client devices;
- make collector replaceable.

## Status

Partially mitigated at the architecture level and by a network-free fixture
Collector engine plus locally mocked runtime adapters only. No live production
Instagram runtime has been enabled; web changes, session loss and account
restrictions remain open operational risks. The MinIO `stat -> put` path is not
a cross-system transaction; until a concurrent runner and reconciler exist, the
future operator runner remains globally sequential.

Stage 3C.1 limits repeat observations to 30 and records account-owned repeats
without a download, but a finite feed may still exhaust its observation budget
before reaching the desired reserve. The operator must inspect the safe result
and rerun later; the next run recomputes the actual durable total. Live Instagram
behaviour, account restrictions and browser-profile recovery remain operational
risks.

Stage-10 live evidence now shows a concrete transition failure: one real Reel
can be downloaded and committed, but the browser cannot confirm the next
canonical feed card after its bounded container/keyboard/wheel cascade. This
blocks any claim that a PWA command can fill a device reserve from one live
collection. TASK-016 requires a 3/3 transition repair before enabling the
sequential 50-Reel Stage-10 scenario. No retry-limit or sandbox-bypass
workaround is permitted.

The runtime now rejects a DOM-only apparent change: it requires two stable
central-media observations plus a different canonical code from authenticated
feed JSON received after the action's in-memory checkpoint. This prevents
preloaded or stale feed responses from being counted as movement, but it still
needs a new bounded 3/3 Linux run as live evidence; the 50-Reel scenario
remains blocked until then.

The first post-change Linux verification saw the stable DOM/media half of that
condition but no post-action canonical JSON candidate. It terminated
`TRANSITION_FAILED` as designed. The remaining investigation is therefore
whether the input action truly advances Instagram's feed request, not whether a
stale DOM/response can be accepted as a false transition.

The first bounded native-touch attempt found no ordinary scrollable DOM owner
or document root on the live Reels page, so it correctly sent no touch event.
The next implementation must safely support a hit-testable central-video
gesture target for CSS-locked React feeds; it must not fall back to DOM
`scrollBy`, overlays or a sandbox bypass.

The runtime now replaces JavaScript `scrollBy` with one verified native touch
swipe on the active mobile scroll owner, or directly on the hit-testable
central video when a CSS-locked feed has no owner. This removes the known
DOM-only movement mechanism without adding an API request, state mutation,
retry or sandbox exception. Its effectiveness still requires a fresh bounded
Linux 3/3 run; absence of post-action JSON remains terminal and continues to
block the 50-Reel acceptance.

The first ownerless-target Linux run still returned no available input target
and therefore sent no touch, despite later observing active-media changes.
The ambiguity between a probe-evaluation failure and no visible central video
must be exposed only as safe aggregate state, and target selection must stay
aligned with media selection. Until then, the native-gesture repair remains
unproven and the 50-Reel acceptance is blocked.

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
- The Turbopack glob manifest contains static assets but not literal App Router page URLs. `/`, `/offline`, and `/manifest.webmanifest` are therefore explicitly precached with deterministic SHA-256 revisions derived from application-shell build inputs.
- Navigation fallback is restricted to same-origin `GET /` and `/offline`; `/videos` is Backend-owned and explicitly excluded from shell caching together with its subpaths.
- iOS can retain an old Home Screen launch URL after a manifest `start_url` change. The app deliberately has no runtime redirect because a precached `/offline` document is also a valid offline navigation target; users must reinstall once to adopt the new `/` launch route.
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
- The standalone manifest starts at `/`, and the worker serves the same-origin dashboard shell and `/offline-media/{id}` without a Backend fallback.
- The dashboard presents only a percentage derived from `navigator.storage.estimate()`; this remains a hint and does not promise retention or request persistence automatically.
- Safari and the installed Home Screen PWA use distinct offline-storage contexts; users must install first and download media inside the installed PWA.
- Safe-area-aware controls, `100dvh`, `playsInline`, native scroll-snap, visibility handling, and previous/current/next source cleanup are in place. `/videos` is reserved for the Backend API; Reels starts with normal sound and leaves an iOS-blocked audible startup paused for an explicit user Play, without a silent workaround. The current window improves return to the previous item while bounding sources to three.
- `/offline` now uses the shared feed's Reels-like mode. One tokenized pointer state machine separates tap, centre hold, symmetric outer-10% edge hold and movement cancellation without `preventDefault` or pointer capture. Only tap-pause exposes controls; an activated centre hold retains a scoped pause lock through move/scroll and iOS `pointercancel`, then resumes only after the actual touch ends if its original item remains active and unchanged. Lifecycle and source cleanup clear that lock without autoplay. Reels-only `touch-action: pan-y`, callout/selection suppression and drag prevention do not apply to the dashboard. The lower progress → glass-navigation layout uses scoped backdrop blur with an opaque fallback; its safe-area sizing and WebKit rendering still need device acceptance.
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

The network hint from `navigator.onLine` is not a guarantee that the Backend is reachable. Service Worker updates can wait while several tabs remain open, and the `/` dashboard must not claim that a failed catalog is ready for download.

## Mitigation

- `/` precaches its application shell and keeps the Backend catalog request `cache: "no-store"`; `/videos` belongs exclusively to the Backend API.
- A failed catalog request renders a controlled dashboard state. This avoids relying on `navigator.onLine` as an authoritative reachability signal.
- `/` and `/offline` are the only navigation fallbacks. Unknown and Backend-owned routes do not receive a shell document.
- The network indicator is informational and does not infer downloaded-video availability.
- `skipWaiting` is disabled and `reloadOnOnline=false`. A waiting update remains inert until the user selects **«Обновить»**; Serwist then activates only that waiting worker through its supported message API and the page reloads once after `controllerchange`.
- Shell cache lifecycle remains isolated from `offline-reels-media-v1`.

## Remaining limitation

Two open tabs can stay on different shell versions until a user accepts the update in each relevant client; there is no cross-tab coordination or background synchronization. Manual desktop and iPhone lifecycle testing remains required.

## Status

Open, accepted for TASK-005 Block 4.2.

---

# Risk 12: Local cleanup is not cross-tab synchronized

The dashboard cancels the singleton queue, waits for its pump, then clears media cache data before IndexedDB metadata. Reconciliation compensates if the metadata step fails, but another open tab will not receive a live update. Browser storage estimates can also remain nonzero or update with delay after deletion. Cross-tab synchronization is deferred.

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

## Linux Collector runtime

- Stage 3C.2 proves a synthetic Linux container flow only. Chromium packaging,
  ffmpeg/ffprobe, PostgreSQL and MinIO have been exercised, but live Instagram
  session longevity, proxy/network policy and remote operator login remain
  unverified until Stage 4.
- Windows Chromium profiles are deliberately not portable to the Linux
  container. A future mobile-login/remote-browser flow must create Linux state
  in the dedicated persistent profile mount; it must not import Windows state.

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
# Risk 18: Management device/session loss

## Problem

A paired owner device can be lost while its management cookie is still valid.

## Mitigation

Sessions expire, can be revoked individually, and the local operator CLI can
revoke all sessions for an account. Pairing challenges are short-lived,
single-use and hashed at rest. Mutations need Host/Origin, CSRF and DB-backed
idempotency checks; no static frontend admin secret exists.

## Remaining limitation

Rate limiting uses PostgreSQL fixed windows keyed by a non-reversible scope
hash, so API workers share the same pairing and session-mutation boundary
without retaining IP or user-agent data.

## Status

Open; acceptable for the single-owner MVP.

---
# Risk 19: Stage 7 end-to-end environment acceptance

## Problem

The automated fixture proves the browser-connected chain across the separate
fixture gateway, Collector, normalizer and paginated catalog. It cannot prove
iPhone Safari/PWA Cache Storage, iOS gesture constraints, or deployment TLS
behavior. A same-origin `/connect` proxy deployment is still required for the
launch-URL restriction to be exercised on the real device.

## Mitigation

Stage 7 keeps management responses network-only/no-store, constrains launch
navigation to HTTPS same-origin `/connect/{id}`, and uses cancellable bounded
polling with stale-response guards. The mobile-viewport fixture covers the
synthetic flow, cancellation, reauthentication/revoke, offline behavior,
pagination/deduplication, technical-data redaction and no-cache headers. The
manual worksheet remains required before any real iPhone test.

## Status

Partially mitigated: automated disposable fixture acceptance passed and its
resources were removed; synthetic iPhone Stage 7 PWA acceptance also passed.
Stage 4 real remote login passed separately. The complete retained Stage 4
profile → Collector → normalizer → PWA flow is not accepted on Windows Docker
Desktop because the isolated non-root Chromium/CDP preflight closed before
browser readiness. It requires repeat acceptance on Linux staging or a real
server. No `--no-sandbox`, root browser, privileged container or `SYS_ADMIN`
workaround was applied. Stage 4 Risk 17 remains independently open.

---
