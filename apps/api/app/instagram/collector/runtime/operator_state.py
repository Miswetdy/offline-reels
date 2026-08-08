"""Non-secret, local operator state for the bounded live Collector command."""

import json
from pathlib import Path
from uuid import UUID, uuid4

from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode


def load_or_create_account_id(workspace_root: Path) -> UUID:
    """Persist only an internal UUID outside the repository and browser profile."""

    path = workspace_root.resolve(strict=False) / "operator-state" / "account.json"
    try:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("account_id"), str):
                return UUID(payload["account_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        account_id = uuid4()
        path.write_text(json.dumps({"account_id": str(account_id)}) + "\n", encoding="utf-8")
        return account_id
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED) from error
