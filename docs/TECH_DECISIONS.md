# Technical Decisions

This document contains important technical decisions made during project development.

Each decision should describe:
- what was decided;
- why this approach was chosen;
- what alternatives were considered;
- current status.

---

# Decision 1: MVP target platform

## Decision

The first version targets iOS devices through a PWA approach.

Android and desktop support are not part of the initial MVP.

## Reason

The primary use case is personal offline viewing of Reels on mobile devices.

Starting with one platform allows faster validation of the core experience:
- synchronization;
- offline playback;
- storage management;
- feed experience.

## Alternatives considered

- Native iOS application.
- Cross-platform mobile application.
- Supporting iOS and Android simultaneously.

## Status

Accepted.

---

# Decision 2: Instagram integration isolation

## Decision

Instagram interaction must be isolated inside a dedicated Instagram Collector component.

Backend and frontend must not depend on Instagram-specific implementation details.

## Reason

Instagram integration is an external dependency that may change.

The system should allow replacing the implementation without rewriting the core application.

## Alternatives considered

- Putting Instagram automation directly into Backend.
- Using Instagram logic throughout the application.

## Status

Accepted.

---

# Decision 3: Server-side preparation of content

## Decision

The server prepares the user's offline feed:
- discovers Reels;
- downloads videos;
- prepares metadata.

The client only synchronizes prepared content.

## Reason

Server-side processing gives more control over:
- reliability;
- retries;
- storage;
- background processing.

## Alternatives considered

- Downloading directly on the phone.
- Fully client-side Instagram automation.

## Status

Accepted.

---

# Decision 4: Backend as the only client communication layer

## Decision

The client communicates only with Backend API.

The client should not directly interact with internal services.

## Reason

This keeps:
- security boundaries clear;
- infrastructure replaceable;
- business logic centralized.

## Status

Accepted.

---

# Decision 5: Offline storage approach

## Decision

For the MVP, store downloaded video files in Cache Storage and store ready-video metadata in IndexedDB.

The exact saved-video size is calculated only from ready video `byteSize` values in IndexedDB. Browser storage usage is an approximate origin-wide diagnostic value and is displayed separately.

## Experiment result

TASK-001 was completed on an iPhone 16 Pro running iOS 26.5.2 with 44.2 GB of free device storage.

- The PWA was installed successfully on the Home Screen.
- A 13,864,238-byte video downloaded and played while online.
- The saved video remained available after a full PWA restart.
- The PWA started in Airplane Mode and played the video offline; a second offline launch also worked.
- Deletion worked: the exact saved-video size immediately became `0 B`, and the removed video did not return after restarting the PWA.
- Approximate browser storage can remain non-zero after deletion because it also includes the app shell, service worker, IndexedDB, and other origin data.

## Remaining validation

This experiment does not confirm long-term persistence, behavior near the storage quota, or behavior with a large number of videos.

## Status

Accepted.

---

# Decision 6: iPhone media compatibility and installed-PWA storage

## Decision

Treat media codec compatibility as an ingestion concern and test offline
downloads only from the installed Home Screen PWA.

## Reason

The iPhone acceptance run showed that Safari and the installed PWA have
separate offline-storage contexts. A VP9 MP4 failed on iPhone, while H.264
with `yuv420p` and `faststart` played correctly. The next stage will add media
normalization before stored media reaches playback.

## Status

Accepted; implementation is pending.
