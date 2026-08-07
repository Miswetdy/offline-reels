"""Explicit Collector runtime settings, intentionally separate from API settings."""

import os
from dataclasses import dataclass
from pathlib import Path

from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode

MEBIBYTE = 1024 * 1024


@dataclass(frozen=True)
class CollectorRuntimeSettings:
    enabled: bool
    profile_root: Path | None
    workspace_root: Path | None
    headless: bool = False
    transition_polling_seconds: float = 0.25
    transition_timeout_seconds: float = 10.0
    maximum_reel_bytes: int = 100 * MEBIBYTE
    maximum_run_bytes: int = 1024 * MEBIBYTE
    maximum_target_count: int = 10
    cooldown_seconds: float = 0.5
    maximum_scroll_attempts: int = 30

    @classmethod
    def from_environment(
        cls,
        environment: dict[str, str] | None = None,
    ) -> CollectorRuntimeSettings:
        values = os.environ if environment is None else environment
        enabled = values.get("COLLECTOR_ENABLED", "false").strip().lower() == "true"
        profile = values.get("COLLECTOR_PROFILE_ROOT")
        workspace = values.get("COLLECTOR_WORKSPACE_ROOT")
        return cls(
            enabled=enabled,
            profile_root=Path(profile) if profile else None,
            workspace_root=Path(workspace) if workspace else None,
            headless=values.get("COLLECTOR_HEADLESS", "false").strip().lower() == "true",
            transition_polling_seconds=_float(values, "COLLECTOR_TRANSITION_POLLING_SECONDS", 0.25),
            transition_timeout_seconds=_float(values, "COLLECTOR_TRANSITION_TIMEOUT_SECONDS", 10.0),
            maximum_reel_bytes=_integer(values, "COLLECTOR_MAXIMUM_REEL_BYTES", 100 * MEBIBYTE),
            maximum_run_bytes=_integer(values, "COLLECTOR_MAXIMUM_RUN_BYTES", 1024 * MEBIBYTE),
            maximum_target_count=_integer(values, "COLLECTOR_MAXIMUM_TARGET_COUNT", 10),
            cooldown_seconds=_float(values, "COLLECTOR_COOLDOWN_SECONDS", 0.5),
            maximum_scroll_attempts=_integer(values, "COLLECTOR_MAXIMUM_SCROLL_ATTEMPTS", 30),
        )

    def require_live(self, *, repository_root: Path) -> CollectorRuntimeSettings:
        if not self.enabled:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        if self.profile_root is None or self.workspace_root is None:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        profile_root = _safe_root(self.profile_root, repository_root)
        workspace_root = _safe_root(self.workspace_root, repository_root)
        if _contains(profile_root, workspace_root) or _contains(workspace_root, profile_root):
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        if self.transition_polling_seconds <= 0 or self.transition_timeout_seconds <= 0:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        if self.maximum_reel_bytes <= 0 or self.maximum_run_bytes < self.maximum_reel_bytes:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        if self.maximum_target_count < 1 or self.maximum_scroll_attempts < 1:
            raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
        return self


def _safe_root(value: Path, repository_root: Path) -> Path:
    if not value.is_absolute():
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    resolved = value.resolve(strict=False)
    repository = repository_root.resolve(strict=False)
    forbidden = {
        Path(value.anchor).resolve(strict=False),
        Path.home().resolve(strict=False),
        repository,
    }
    if resolved in forbidden:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    # Collector state must never be created in a checkout.  resolve() follows
    # existing symlink/junction components before this containment test.
    if repository in resolved.parents:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED)
    return resolved


def _contains(parent: Path, child: Path) -> bool:
    return child == parent or parent in child.parents


def _integer(values: dict[str, str], key: str, default: int) -> int:
    try:
        return int(values.get(key, str(default)))
    except ValueError as error:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED) from error


def _float(values: dict[str, str], key: str, default: float) -> float:
    try:
        return float(values.get(key, str(default)))
    except ValueError as error:
        raise CollectorRuntimeError(RuntimeReasonCode.COLLECTOR_DISABLED) from error
