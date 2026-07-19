# iOS offline video storage spike

This is an isolated technical experiment for TASK-001. It is not the production frontend and does not use the project's Next.js stack, backend, Instagram integration, or server-side services.

The PWA stores successful MP4 downloads in Cache Storage and stores only completed video metadata in IndexedDB. Download-in-progress state exists only in React memory.

## Prerequisites

- Node.js 22 or newer.
- A small, licensed MP4 no larger than 100 MB.
- For the acceptance test: a real iPhone and an HTTPS host with a certificate trusted by that iPhone.

Do not commit test media, personal videos, credentials, or production data. The repository ignores `public/media/*.mp4`.

## Add a test video

Place a small licensed file at:

```text
public/media/sample.mp4
```

The default URL is `/media/sample.mp4`. Alternatively, set `VITE_SAMPLE_VIDEO_URL` to another **same-origin** path. Cross-origin URLs are intentionally rejected by the spike.

## Local development

```bash
npm install
npm run dev
```

Open the displayed local URL to exercise the interface. This is useful for UI and storage development, but it is not the iPhone PWA acceptance test.

## Tests and production build

```bash
npm test
npm run build
```

`dist/` is the static production build. The test suite covers Cache Storage persistence, IndexedDB metadata persistence, duplicate prevention, and Cache Storage cleanup when the metadata write fails.

## HTTPS deployment for iPhone testing

1. Build the app with `npm run build`.
2. Deploy the contents of `dist/` as a static site on a dedicated HTTPS origin. The certificate must be trusted by the iPhone.
3. Copy the test MP4 to the deployed `/media/sample.mp4` path. Do not upload private content.
4. Open the HTTPS URL in Safari on the iPhone while online.
5. Wait for the first load to complete, then refresh once so the service worker can activate.

Do not use a plain HTTP LAN address for the final PWA check. Service worker and offline behavior must be tested on HTTPS.

## Install on iPhone

1. In Safari, open the deployed HTTPS URL.
2. Use Share, then choose **Add to Home Screen**.
3. Open the installed app from the Home Screen.
4. Download the test MP4 and confirm that the size and saved-video card appear.

For debugging from a Mac, enable **Settings → Apps → Safari → Advanced → Web Inspector** on the iPhone, connect it to the Mac, and inspect the Home Screen web app in Safari.

## Offline verification scenario

1. Launch the installed PWA while online and download the test MP4.
2. Play it once to confirm that the file is valid.
3. Close the PWA completely.
4. Enable Airplane Mode, disabling both Wi-Fi and mobile data.
5. Relaunch the PWA from the Home Screen.
6. Confirm the saved card is restored and the video plays using local storage.
7. Close and reopen the PWA again while still offline.
8. Use **Delete**, confirm the card and total saved size disappear, then relaunch once more.

Record the iPhone model, iOS version, available device storage, Cache Storage/IndexedDB behavior, and any failures. These observations are required before Decision 5 in `docs/TECH_DECISIONS.md` can be finalized.

## Known limits

- Browser storage can be evicted by iOS; this spike does not prove long-term persistence.
- The PWA does not download in the background while closed.
- `Saved video files (exact)` is only the sum of `byteSize` for ready metadata records in IndexedDB, so it becomes `0 B` after the last saved video is deleted.
- `Approximate browser storage used` is a separate origin-wide estimate. It can remain non-zero after video deletion because it includes the app shell, service worker, IndexedDB, and other origin data.
