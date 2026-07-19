# ADR 002: Stream video through Backend API

## Status

Accepted.

## Context

The first video vertical slice needs HTML5 playback and seeking from S3-compatible storage while the frontend remains isolated from internal infrastructure.

## Decision

The frontend receives metadata from the Backend API and builds a Backend stream URL. `GET /videos/{id}/stream` proxies one byte range from MinIO in chunks. Presigned MinIO URLs are not used.

## Consequences

- Frontend never receives storage credentials or directly accesses MinIO.
- API owns Range validation, safe error mapping and CORS policy.
- Backend carries media traffic for this initial slice; scaling or direct delivery can be reconsidered only in a later task.
