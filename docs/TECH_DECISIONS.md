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

The exact offline video storage mechanism is not finalized yet.

Possible approaches:
- Cache Storage for video files.
- IndexedDB for metadata and state.

A technical experiment on real iOS devices is required.

## Status

Open.