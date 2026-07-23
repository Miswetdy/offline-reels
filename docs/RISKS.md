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

If PostgreSQL fails after a successful upload, an orphan object can remain. Automatic orphan cleanup is outside TASK-003. If an object is deleted after metadata exists, the streaming endpoint returns the safe `video_object_not_found` error without exposing storage internals.

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
- Cache cleanup and startup reconciliation compensate for failed or interrupted writes.
- Queue concurrency is one. Abort and quota failures pause it; queued work requires explicit user continuation after reload or network recovery.
- Storage pre-checks use a 1.2 multiplier and a desired 50 MiB reserve, but estimates remain approximate.

## Remaining limitation

Multiple tabs can still create competing queue controllers because `navigator.locks` is deliberately deferred. There is no background download, automatic recovery, Service Worker delivery, cached-media Range support or iPhone memory/quota acceptance result yet. Large-file memory behavior must be measured manually on Chrome and an iPhone before later offline-playback work.

## Status

Open, accepted for TASK-005 Block 2.

Known dependency advisories:

- Next.js 16.2.10 currently resolves optional sharp 0.34.5, affected by GHSA-f88m-g3jw-g9cj.
- The application does not currently process untrusted images through sharp, so the known exploitation path is not used.
- Next.js also resolves nested postcss 8.4.31, affected by GHSA-qx2v-qp2m-jg93.
- The application does not accept or serialize untrusted user CSS.
- npm audit fix --force is prohibited because it proposes an incompatible downgrade to Next.js 9.3.3.
- Dependency remediation is tracked separately and must be completed before production deployment.

---

# Risk 11: Temporary offline Blob URL playback

## Problem

TASK-005 Block 3.2 uses `Response.blob()` and temporary object URLs because no Service Worker yet serves `/offline-media/{videoId}`. A Blob URL retains the cached MP4 in browser-managed memory for its lifetime and cannot provide HTTP Range semantics or survive a page reload.

## Mitigation

`/offline` reconciles local data before listing it, never falls back to Backend media, and creates object URLs only for the active player and its next neighbor. The shared feed revokes each URL when it leaves that window and on unmount.

## Remaining limitation

Offline page reload, application-shell delivery, cached-media Range playback and iPhone memory behavior are not confirmed. Service Worker delivery remains a required next stage.

## Status

Open, accepted temporarily for TASK-005 Block 3.2.

---

# Risk 12: Local cleanup is not cross-tab synchronized

`/offline` deletes media cache data before IndexedDB metadata and refreshes its own catalog after each operation. Reconciliation compensates if the metadata step fails, but another open tab will not receive a live update. Browser storage estimates can also remain nonzero or update with delay after deletion. This is accepted for TASK-005 Block 3.3; cross-tab synchronization is deferred.
