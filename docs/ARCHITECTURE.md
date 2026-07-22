# Architecture

## Overview

Offline Reels is a personal application that allows users to prepare a personalized Instagram Reels feed in advance and watch it without an internet connection.

The system consists of several independent components:

1. Mobile App / PWA
2. Backend API
3. Feed Queue
4. Instagram Collector
5. Media Downloader
6. Video Storage

Each component has a clear responsibility and communicates only through defined interfaces.

---

# System Flow

The general data flow:

1. Instagram Collector accesses the user's personalized Instagram Reels feed through an authenticated server-side browser session.

2. Instagram Collector discovers new Reels and sends information about them to the Backend.

3. Backend creates and manages the user's feed queue.

4. Media Downloader downloads video files and validates downloaded media.

5. Video Storage stores prepared video files and related metadata.

6. Mobile App / PWA requests available videos from Backend and synchronizes them to local storage.

7. User watches videos from local storage without requiring an internet connection.

8. Watched status is synchronized back to Backend when the connection is available.

---

# Components

## Mobile App / PWA

Purpose:

Provide the user interface and offline viewing experience.

Responsibilities:

- Display the vertical Reels feed.
- Play locally stored videos.
- Manage offline mode.
- Store videos on the device.
- Track watched videos.
- Synchronize local state with Backend.
- Manage local storage limits.

Restrictions:

- The client must never store Instagram credentials.
- The client must communicate only with Backend API.
- The client must not directly interact with Instagram.

---

## Backend API

Purpose:

Serve as the main application layer between the client and internal services.

Responsibilities:

- Manage users.
- Manage feed state.
- Provide API endpoints for the mobile application.
- Track downloaded and watched videos.
- Manage synchronization between server and client.
- Coordinate background processes.

Restrictions:

- Backend should not contain Instagram-specific scraping logic.
- External integrations should be isolated in separate services.

---

## Feed Queue

Purpose:

Manage the order and availability of videos for each user.

Responsibilities:

- Store discovered Reels.
- Track video states.
- Prevent duplicate videos.
- Decide which videos should be synchronized to the device.
- Maintain the user's offline video buffer.

Possible video states:

- Discovered.
- Downloading.
- Ready on server.
- Downloaded to device.
- Watched.
- Deleted.

---

## Instagram Collector

Purpose:

Collect personalized Reels from Instagram.

Responsibilities:

- Maintain authenticated browser sessions.
- Open Instagram Reels.
- Discover new videos.
- Extract required metadata.
- Send discovered videos to Backend.

Restrictions:

- Instagram automation must be isolated from the rest of the system.
- Credentials and sessions must remain on the server.
- The collector should be replaceable without changing other components.

---

## Media Downloader

Purpose:

Download and prepare video files.

Responsibilities:

- Download video files.
- Validate downloaded files.
- Check file size and format.
- Handle download failures.
- Retry failed downloads.

Restrictions:

- Must support safe retries.
- Must avoid creating duplicate files.

---

## Video Storage

Purpose:

Store video files and metadata.

Responsibilities:

- Store downloaded videos.
- Store thumbnails if required.
- Provide access to Backend and synchronization services.
- Manage file lifecycle.

For the first video vertical slice, the Backend accesses MinIO through a replaceable storage adapter. The PWA receives video bytes only from `GET /videos/{id}/stream`; it never receives MinIO credentials or a direct object URL. The API streams a single HTTP byte range from storage in chunks.

For TASK-004, `GET /videos` is a Backend-owned cursor-paginated feed API. It signs opaque cursors with an application secret and uses the stable PostgreSQL order `created_at DESC, id DESC`; the PWA treats cursors as opaque and continues to communicate only with the Backend API. The `/videos` UI uses native browser scrolling and `IntersectionObserver` to select one active player. This changes neither the storage boundary nor the rule that the client must not contact MinIO directly.

---

# Security Principles

The system must follow these rules:

- Instagram credentials, cookies, and sessions must never be stored on the client.
- Secrets must never be committed to GitHub.
- Real user credentials must never be used in tests.
- External data must always be validated.
- Logs must not contain sensitive information.

---

# Offline Mode

Offline mode should work independently from Instagram availability.

When the user has no internet connection:

- The application uses locally stored videos.
- The user can browse the feed.
- The user can watch downloaded videos.
- The application stores local actions for future synchronization.

Internet is only required for:

- downloading new videos;
- synchronizing state;
- updating the feed queue.

---

# Local Offline Library Foundation

TASK-005 Block 1 introduces an isolated client-side persistence boundary without changing the online feed. The `offline-reels` IndexedDB database stores local-video metadata and lifecycle state; the separate `offline-reels-media-v1` Cache Storage cache stores MP4 responses. Entries use validated same-origin synthetic paths in the form `/offline-media/{uuid}` and never store Backend URLs, cursors, credentials or blobs in IndexedDB.

IndexedDB and Cache Storage do not have a common transaction. A future downloader must write and validate media before marking its metadata `completed`; startup reconciliation compensates for stale downloads, missing or invalid cache entries, and orphan media entries. Service Worker delivery, an offline route and a download queue are not part of Block 1.

---

# Development Principles

The architecture should prioritize:

- simple solutions;
- clear separation of responsibilities;
- replaceable external integrations;
- testability;
- maintainability.

New features should not bypass existing boundaries between components.
