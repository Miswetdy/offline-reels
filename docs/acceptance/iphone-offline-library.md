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
  Block 3 will add Reels-like controls.

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
4. Verify standalone presentation and that the initial route is `/offline`.
5. In Safari Web Inspector (when available), confirm the Service Worker has scope `/` and controls the page.

Expected: the manifest supplies the standalone name, colors, and icon; no online navigation is required merely to open `/offline`.

## B. Download

1. Online, open `/videos`.
2. Download at least ten different videos.
3. Request an already completed video again; confirm it is not downloaded twice.
4. Close the PWA during one active download, reopen it, and confirm the record becomes interrupted/failed with a manual retry path.
5. Record queue order, progress behavior, completed count, and exact library bytes.

Expected: one download is active at a time; only fully validated cache entries become `completed`; there is no automatic background resume.

## C. Full offline restart

1. While online, open `/offline` once and wait for the catalog.
2. Fully close the PWA from the app switcher.
3. Enable Airplane Mode.
4. Launch from the Home Screen and open `/offline`.
5. Play at least ten downloaded videos consecutively.

Expected: the Serwist application shell, IndexedDB catalog, and local media route work without Backend/API requests.

## D. Playback and lifecycle

1. Swipe quickly forward and backward through the offline feed.
2. Seek each tested video near the beginning, middle, and end.
3. Pause/resume and toggle sound.
4. Background the PWA and return.
5. Lock the screen for 30 seconds, unlock, and verify the resulting controlled playback state.
6. Confirm only one video plays audibly/visibly at a time.

Expected: the previous/current/next media window holds at most three `src` values, videos use `playsInline`, return from background does not force forbidden autoplay, and a failed card remains terminal without blocking neighbouring cards.

## E. Long offline session

1. Watch offline for at least 20 minutes.
2. Make at least 50 forward/backward swipes.
3. Record memory-pressure symptoms, reloads, white screens, crash, playback stalls, or visible degradation.

Expected target (not yet a release blocker): no material degradation. This specifically measures the known full-file Service Worker Range-slicing memory cost.

## F. Delete and clear

1. Delete the current video, then the next video.
2. Restart the PWA and verify both deletions persist.
3. Clear the offline library.
4. Close the PWA, enable Airplane Mode, and open it again.

Expected: local media and metadata disappear together (or reconciliation repairs a partial operation), the empty state appears, and the application shell remains available. Online catalog records and server objects are never deleted.

## G. Service Worker update

1. Keep an older installed PWA window open.
2. Produce a new frontend build revision and open it online.
3. Observe a waiting worker if old clients remain open.
4. Close older windows, reopen the app, and confirm the new worker controls it.
5. Verify `offline-reels-media-v1` and downloaded videos remain intact.

Expected: no forced `skipWaiting`, automatic reload loop, or media-cache deletion.

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
- [ ] Delete and clear survive restart.
- [ ] Storage inconsistency is reconciled.
- [ ] Worker update preserves media cache.
- [ ] No crash, reload loop, or white screen occurs.

Targets that are valuable but not currently blocking:

- [ ] Twenty minutes of playback without degradation.
- [ ] Fifty swipes without memory-pressure symptoms.
- [ ] Controlled return after lock screen.
- [ ] Useful quota/persistence diagnostics.
