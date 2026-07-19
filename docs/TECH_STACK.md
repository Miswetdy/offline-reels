# Technology Stack

## Frontend

Technology:
- Next.js
- TypeScript
- Tailwind CSS
- PWA
- IndexedDB

Purpose:
Build the mobile-friendly offline feed interface.

---

## Backend

Technology:
- Python
- FastAPI
- SQLAlchemy
- Alembic

Purpose:
Provide API, business logic, synchronization, and application state management.

---

## Database

Technology:
- PostgreSQL

Purpose:
Store users, videos metadata, feed states, and synchronization information.

---

## Background Processing

Technology:
- Redis
- Celery

Purpose:
Handle asynchronous tasks:
- collecting Reels;
- downloading videos;
- synchronization jobs.

---

## Storage

Technology:
- S3-compatible storage
- MinIO for local development

Purpose:
Store video files and media assets.

---

## Instagram Integration

Technology:
- Playwright

Purpose:
Automate browser interaction with Instagram through isolated server-side sessions.

---

## Development

Technology:
- Docker Compose
- GitHub

Purpose:
Provide reproducible local development environment and version control.