"""Attempt-owned Collector workspace lifecycle."""

import shutil
from pathlib import Path
from uuid import UUID

from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode


def attempt_workspace(workspace_root: Path, run_token: UUID) -> Path:
    """Create one isolated, removable workspace below an already safe root."""

    root = workspace_root.resolve(strict=False)
    candidate = (root / "attempts" / str(run_token)).resolve(strict=False)
    if root not in candidate.parents:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    try:
        candidate.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED) from error
    return candidate


def cleanup_attempt_workspace(workspace_root: Path, candidate: Path) -> None:
    root = workspace_root.resolve(strict=False)
    resolved = candidate.resolve(strict=False)
    attempts = (root / "attempts").resolve(strict=False)
    if attempts not in resolved.parents or root not in resolved.parents:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    shutil.rmtree(resolved, ignore_errors=True)
