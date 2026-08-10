"""Read the existing FastAPI catalog in-process without starting a server."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def main() -> int:
    try:
        response = TestClient(create_app()).get("/videos?limit=30")
        if response.status_code != 200:
            print(json.dumps({"event": "failed", "reason_code": "POSTGRES_COMMIT_FAILURE"}))
            return 1
        payload = response.json()
        items = payload.get("items")
        if not isinstance(items, list):
            print(json.dumps({"event": "failed", "reason_code": "POSTGRES_COMMIT_FAILURE"}))
            return 1
        print(
            json.dumps(
                {
                    "catalog_items": len(items),
                    "has_next_cursor": payload.get("next_cursor") is not None,
                    "status_code": response.status_code,
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(json.dumps({"event": "failed", "reason_code": "POSTGRES_COMMIT_FAILURE"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
