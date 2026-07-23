# ADR-005: Serwist Turbopack application shell

## Status

Accepted for TASK-005 Block 4.1.

## Context

The browser-only `/offline` library already stores its catalog in IndexedDB and MP4 responses in `offline-reels-media-v1`. It could not reliably reload without a network connection because the Next.js application shell was not cached. The project uses Next.js production builds with Turbopack on Windows.

## Decision

Use `@serwist/turbopack`, `serwist`, and native `esbuild` to build one worker from `apps/web/app/sw.ts`. The worker is dynamically available at `/serwist/sw.js`; `SerwistProvider` automatically registers it with scope `/` only in production. `reloadOnOnline=false` prevents connection recovery from forcing a page reload.

The injected revisioned Next build manifest provides static asset entries, but it does not contain literal App Router page URLs such as `/offline`. The worker explicitly adds `/offline` through `additionalPrecacheEntries` with a deterministic SHA-256 revision derived from the offline shell's build inputs. This creates Serwist's revisioned cache key and establishes the invariant required before binding `/offline` as navigation fallback. `/manifest.webmanifest` is not needed for this fallback and remains outside the precache. The navigation fallback is `/offline`, allowlisted only for same-origin `GET /offline` requests. No runtime caching is configured: Backend API responses, streams, cross-origin media, Blob URLs and non-GET requests are excluded.

Serwist's own precache cache is separate from `offline-reels-media-v1`. Activation cleanup handles only outdated Serwist precaches; offline-library delete and clear operations continue to touch only the media cache and IndexedDB metadata.

## Consequences

After a production user has visited `/offline`, the page shell can be reloaded offline and read the local IndexedDB catalog. Development intentionally disables worker registration. Native `esbuild` must be available for production builds on Windows.

This block does not serve `/offline-media/{videoId}`, implement cached HTTP Range responses, replace Blob URL playback, or guarantee storage persistence. Those capabilities remain for Block 4.2 and later validation on iPhone.
