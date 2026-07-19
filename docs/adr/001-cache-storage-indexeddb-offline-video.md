# ADR-001: Use Cache Storage and IndexedDB for MVP offline video storage

## Status

Accepted.

## Context

The iOS PWA must download videos, keep them available after restarting the app, play them without network access, show the exact size of saved videos, and allow users to delete them.

## Decision

For the MVP:

- Store downloaded video files in Cache Storage.
- Store metadata for ready videos in IndexedDB.
- Calculate the exact saved-video size as the sum of ready-video `byteSize` values in IndexedDB.
- Display browser storage usage separately as an approximate origin-wide value; it can include the app shell, service worker, IndexedDB, and other origin data.

## Evidence

TASK-001 passed on an iPhone 16 Pro running iOS 26.5.2 with 44.2 GB free device storage. A 13,864,238-byte video was downloaded, played online and offline, remained after full PWA restarts, and was deleted permanently. The PWA also launched and played the video in Airplane Mode.

## Consequences

- The mobile app can use locally stored files for offline playback without direct interaction with Instagram.
- Deletion must remove both the Cache Storage entry and its IndexedDB metadata.
- Browser storage is not a reliable measure of only saved videos and must not be expected to become zero after video deletion.
- Long-term persistence, quota behavior, storage eviction, and large offline libraries remain open risks and need further validation.
