# iPhone offline library acceptance worksheet

## Preconditions and test record

Use the one-origin HTTPS Tailscale Funnel staging workflow. Safari treats
`localhost` specially only on the device itself; it is not the development
computer. Build with `NEXT_PUBLIC_API_BASE_URL=https://HOST.ts.net/api` and
set `FRONTEND_ORIGIN=https://HOST.ts.net`. Do not put secrets in either value.

## Confirmed acceptance findings

- Safari and the installed Home Screen PWA do not share an offline-storage
  context. Install first, then download media inside the installed PWA.
- A VP9 MP4 failed on iPhone. H.264 with `yuv420p` and `faststart` played;
  media normalization is required before the next acceptance run.
- Post-iPhone hardening block 2 now keeps a previous/current/next preload
  window to improve return to the prior item while bounding resource use.
- Post-iPhone hardening block 3 enables Reels-like controls only on
  `/offline`. `/videos` is now reserved for the Backend API; block 4B is the
  installed-PWA real-device acceptance for this lifecycle.

| Field | Value |
| --- | --- |
| iPhone model | |
| iOS version | |
| Safari version | |
| Test mode (installed PWA / Safari tab) | |
| Public HTTPS origin | |
| API base URL | |
| Git commit / build identifier | |
| Date and time | |
| Number of downloaded videos | |
| Exact media size (metadata) | |
| Browser estimate usage / quota | |
| `navigator.storage.persisted()` result | |

For every scenario record the expected result, actual result, pass/fail, screenshot or screen recording, defect link, and severity (`blocker`, `high`, `medium`, or `low`). Do not include credentials, cookies, tunnel tokens, or real user data in the record.

| Scenario | Expected | Actual | Pass / Fail | Screenshot / video | Defect | Severity |
| --- | --- | --- | --- | --- | --- | --- |
| A — installation | | | | | | |
| B — download | | | | | | |
| C — offline restart | | | | | | |
| D — playback | | | | | | |
| E — long session | | | | | | |
| F — delete and clear | | | | | | |
| G — worker update | | | | | | |
| H — storage recovery | | | | | | |

## A. Installation

1. Open the frontend HTTPS URL in Safari.
2. Use **Share → Add to Home Screen**.
3. Start the new icon from the Home Screen.
4. Verify standalone presentation and that the initial route is `/`. If this PWA was installed before the start-route migration, remove that Home Screen icon and install it once again; there is intentionally no runtime redirect from `/offline`.
5. In Safari Web Inspector (when available), confirm the Service Worker has scope `/` and controls the page.

Expected: the manifest supplies the standalone name, colors, icon, `id`, scope, and `/` start route. No online navigation is required to move between the precached `/` and `/offline` shells.

## B. Download

1. Online, open `/`.
2. Download at least ten different videos.
3. Request an already completed video again; confirm it is not downloaded twice.
4. Close the PWA during one active download, reopen it, and confirm the record becomes interrupted/failed with a manual retry path.
5. Record queue order, progress behavior, completed count, and exact library bytes.

Expected: one download is active at a time; only fully validated cache entries become `completed`; there is no automatic background resume.

## C. Full offline restart

1. While online, open `/` once, then open `/offline` and wait for the local library.
2. Fully close the PWA from the app switcher.
3. Enable Airplane Mode.
4. Launch from the Home Screen, then use **Рилсы** to open `/offline`.
5. Play at least ten downloaded videos consecutively.

Expected: the Serwist application shell, IndexedDB catalog, and local media route work without Backend/API requests.

## D. Playback and lifecycle

1. Cold-launch the installed PWA at `/`, then open `/offline`. Confirm the first active reel requests playback with sound enabled. If iOS blocks audible autoplay, it must remain unmuted and paused with the central Play control visible; tap it once and confirm the same item starts with sound. The app must not silently switch to muted playback.
2. Short-tap the central video area twice. Confirm the first tap pauses and reveals one central SVG play control with one smaller SVG sound control above it. Resume with both the play button and a second short surface tap; controls must disappear only after playback actually resumes, and remain available if iOS rejects play.
3. Tap sound directly. Confirm only mute changes and the tap does not also pause, resume or trigger a hold.
4. While a video is playing, hold the centre for at least 250 ms without moving. Confirm temporary pause and release-to-resume without showing tap controls. Repeat while already paused and confirm release does not start playback or show new controls.
5. Hold the outer left 10%, then outer right 10%. Confirm a nearby `2×` indicator, temporary double speed, restoration on release, and no playback start when already paused. Confirm touches immediately inside the remaining central 80% use centre-hold behaviour instead.
6. Begin each hold and then move vertically more than roughly 12 CSS px, both before and after the hold threshold. Confirm no tap is synthesized and native vertical scrolling remains smooth. After an activated centre hold, the original card must remain paused throughout the same touch—even if iOS emits `pointercancel`—while a newly active card can play normally. If the drag reverses before release, the original card remains paused; it resumes only after release when it is active and was playing before the hold.
7. Start with A fully snapped. Drag toward B until B becomes active but does not fill the viewport, then reverse to A; repeat A↔B several times without releasing into a full snap. Each card must resume from its own paused position and retain its frame—no seek to 0 or black frame. Then let B fully fill the feed, wait for A to leave completely, and return to A: it must start at 0:00 without a stale-frame flash. Repeat symmetrically from B back to A. Full commit is expected only at an effectively full card (observer ratio at least 0.999 with geometry tolerance), never at a partial 50–99% overlap.
8. Confirm video fills the viewport without letterboxing (symmetric crop is acceptable). Check the lower order is thin non-seekable progress, then glass bottom navigation; technical title, size, summary, and delete controls must not be visible. The video should remain visible but blurred only behind that lower navigation zone. Confirm progress tracks only the active video, resets at the start, and does not overlap navigation or the iPhone safe area. Check `/offline` marks **Рилсы** active and `/` marks **Главная** active; both links must remain tappable without triggering playback gestures. Author/caption UI is intentionally not present yet.
9. During pending and active holds, test normal release, system gesture/pointer cancellation where reproducible, background/foreground, and a 30-second screen lock. Confirm no stuck `2×`, text selection, magnifier, copy callout, stale overlay, old-video resume or forbidden autoplay.

Expected: `/offline` has no native video controls, retains `playsInline`, looping and native vertical scroll-snap, keeps the previous/current/next window to at most three `src` values, and never plays two videos simultaneously. Gesture controls remain safe-area-aware and accessible, return from background does not force autoplay, and a failed card remains terminal without blocking neighbouring cards. Interactive horizontal seeking is intentionally not part of block 3.

### Lower visual layout

The floating navigation should sit visibly above the home indicator in both the
installed PWA and Safari, with a bounded adaptive gap rather than a single
device-specific height. On `/`, confirm dashboard controls remain above the same
reserved footprint. On `/offline`, confirm the order is transparent pointer-inert
progress over one continuous
blurred backdrop, navigation pill, then safe-area gap. The video itself must
remain sharp outside that shared glass zone; this visual tuning must not change tap, hold, swipe or
playback behaviour.

### Accepted edge-rate limitation

Keep normal audio and standard pitch preservation enabled. On iOS WebKit, AAC
MP4 can show a short frame freeze or clock jump at the temporary `1× → 2× →
1×` edge-hold boundary. This was reproduced with both Service Worker and Blob
sources while fully buffered; short GOP and B-frames were not the root cause.
A no-audio variant was much smoother, but disabling pitch preservation only
partly helped and distorted speech. Record the symptom in acceptance evidence,
but do not replace it with a forced short-GOP/no-B-frames transcode in the PWA
MVP. Re-downloading unchanged server media alone is not expected to remove this
platform behavior.

After a full B snap, immediately reverse to A without waiting for a further
scroll callback. Test both directions and repeat with a short pause after the
snap. A must already be prepared at 0:00 and play without a black frame,
activation-time seek or hidden-to-visible flash. This must hold whether the
old card's zero-overlap observer callback was delivered before or after the
new card's full-screen callback.

## E. Long offline session

1. Watch offline for at least 20 minutes.
2. Make at least 50 forward/backward swipes.
3. Record memory-pressure symptoms, reloads, white screens, crash, playback stalls, or visible degradation.

Expected target (not yet a release blocker): no material degradation. This specifically measures the known full-file Service Worker Range-slicing memory cost.

## F. Dashboard download and clear

1. Open the installed PWA at `/`. Confirm **Offline Reels**, network status, and storage fill are shown only as percentages; no video player, UUID, byte size, or catalog count is visible.
2. While online, select **Загрузить Reels**. Confirm all available catalog Reels download sequentially and the batch percentage never decreases. Cancel once during a transfer, then select **Повторить** and let the batch finish.
3. Select **Очистить библиотеку** and confirm the exact prompt **Вы точно хотите удалить все скачанные Reels?**. Confirm the batch stops, `/offline` shows **Пока нет скачанных Reels**, and **Перейти на главную** opens `/`.
4. Close the PWA, enable Airplane Mode, and reopen `/offline`. Confirm the empty shell remains available without server content.
5. While online, confirm navigation uses only `/` and `/offline`; `/videos` is not an application-shell destination.

Expected: clear removes local media and metadata together (or reconciliation repairs a partial operation), never deletes server records or objects, and no late download restores a cleared local record. Future watched-retention is not implemented: a later policy may delete watched media locally after one hour and refill only when the app is open online; iOS cannot guarantee work while the PWA is fully closed.

## G. Service Worker update

1. Keep an older installed PWA window open.
2. Produce a new frontend build revision and open it online.
3. In the installed PWA, observe the compact **«Доступна новая версия»** notification with **«Обновить»**. Confirm that no reload happens before the button is pressed, including while a video is playing or a download is active.
4. Select **«Обновить»** once. Confirm one reload after the worker takes control, then confirm that the notification does not create a reload loop.
5. Verify the new shell controls the reopened PWA, `offline-reels-media-v1` and downloaded videos remain intact, and the offline catalog still contains its completed records.

Expected: `skipWaiting` is not forced during install. The user alone starts the message-based activation of the waiting worker; exactly one post-`controllerchange` reload occurs, with no media-cache or IndexedDB deletion.

## H. Storage recovery

1. In a controlled development inspection, delete one entry from `offline-reels-media-v1` while leaving its completed metadata record.
2. Open `/offline` and record reconciliation’s controlled result.
3. Separately remove metadata while leaving one media cache entry.
4. Open `/offline` and verify orphan cleanup.

Expected: no Backend fallback occurs; invalid completed metadata is not presented as playable and orphan media is removed. Record exact observations before treating this as a pass.

## Completion thresholds for TASK-005

The following are required before TASK-005 can be declared complete:

- [ ] Installed PWA starts after a full close in Airplane Mode.
- [ ] `/offline` opens without Backend access.
- [ ] At least ten videos play consecutively.
- [ ] Range seek works.
- [ ] Fast swipes do not break the feed.
- [ ] Two videos never play simultaneously.
- [ ] Dashboard batch download, cancel, and clear survive restart.
- [ ] Storage inconsistency is reconciled.
- [ ] Worker update preserves media cache.
- [ ] No crash, reload loop, or white screen occurs.

Targets that are valuable but not currently blocking:

- [ ] Twenty minutes of playback without degradation.
- [ ] Fifty swipes without memory-pressure symptoms.
- [ ] Controlled return after lock screen.
- [ ] Useful quota/persistence diagnostics.
