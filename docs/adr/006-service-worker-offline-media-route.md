# ADR-006: Service Worker offline media route

## Status

Accepted for TASK-005 Block 5.1.

## Context

Completed offline records already point to deterministic Cache Storage keys in the form `/offline-media/{uuid}`. Before this decision, `/offline` converted each cached response to a Blob URL, which copied a full MP4 into browser-managed memory and could not be used as a durable same-origin media address.

## Decision

The existing Serwist worker owns same-origin `GET /offline-media/{uuid}`. A custom route accepts only exact validated UUID paths without query parameters, opens only `offline-reels-media-v1`, and returns the matching cached `Response` unchanged. This preserves media headers and makes Cache Storage the direct byte source for the browser media pipeline.

The handler does not call `fetch`, write to any cache, use Serwist's shell cache, or fall back to the Backend. A missing entry returns `404`; an invalid path is not matched; and a Cache Storage failure returns `503`.

Block 5.2 adds a strict single `bytes` range parser. The handler supports `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength`; a valid request receives `206`, `Accept-Ranges: bytes`, an inclusive `Content-Range`, and an exact slice length. Invalid, unsatisfiable, zero-size and multipart ranges receive `416` with `Content-Range: bytes */total`; multipart response generation is deliberately out of scope. HEAD returns matching metadata without a body.

`OfflineVideoList` passes the synthetic URL directly to `VerticalVideoFeed`. The former playback-source Blob adapter is removed. If the page has no controlling worker, the UI reports a controlled readiness state instead of silently using a Blob or Backend fallback.

## Consequences

Offline MP4 playback no longer requires `Response.blob()`, `URL.createObjectURL`, or `URL.revokeObjectURL`. Media cache and Serwist shell-cache lifecycle remain isolated: library delete/clear affects only `offline-reels-media-v1`, and worker activation does not remove it.

The worker uses `Response.arrayBuffer()` and `Uint8Array.slice()` to form each response. This preserves the Cache Storage entry and avoids React Blob URLs, but temporarily requires O(full MP4 size) worker memory for a Range request. Browser-specific initial and seek behavior, repeated seeking, and iPhone memory validation remain required before TASK-005 is complete.
