"""Read-only, safe Stage 3B baseline capture and post-run verification."""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramNormalizationJob,
    InstagramReel,
)
from app.db.models.video import Video
from app.instagram.contracts import (
    AccountStatus,
    DownloadAuthMode,
    NormalizationJobStatus,
    ReelPipelineStatus,
    RunItemOutcome,
)

SOURCE_PREFIX = "instagram-sources/"


@dataclass(frozen=True)
class BaselineObject:
    object_key: str
    byte_size: int
    sha256: str
    content_type: str


@dataclass(frozen=True)
class RunBaseline:
    video_count: int
    video_ids_sha256: str
    source_object_keys_sha256: str
    source_objects: tuple[BaselineObject, ...]

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "video_count": self.video_count,
            "video_ids_sha256": self.video_ids_sha256,
            "source_object_keys_sha256": self.source_object_keys_sha256,
            "source_objects": [asdict(item) for item in self.source_objects],
        }

    @classmethod
    def from_safe_dict(cls, payload: object) -> RunBaseline | None:
        if not isinstance(payload, dict):
            return None
        try:
            video_count = payload["video_count"]
            video_fingerprint = payload["video_ids_sha256"]
            object_fingerprint = payload["source_object_keys_sha256"]
            raw_objects = payload["source_objects"]
            if not isinstance(video_count, int) or video_count < 0:
                return None
            if not _is_digest(video_fingerprint) or not _is_digest(object_fingerprint):
                return None
            if not isinstance(raw_objects, list):
                return None
            objects: list[BaselineObject] = []
            for raw in raw_objects:
                if not isinstance(raw, dict):
                    return None
                item = BaselineObject(
                    object_key=raw["object_key"],
                    byte_size=raw["byte_size"],
                    sha256=raw["sha256"],
                    content_type=raw["content_type"],
                )
                if (
                    not isinstance(item.object_key, str)
                    or not item.object_key.startswith(SOURCE_PREFIX)
                    or not isinstance(item.byte_size, int)
                    or item.byte_size < 0
                    or not _is_digest(item.sha256)
                    or not isinstance(item.content_type, str)
                ):
                    return None
                objects.append(item)
            if len({item.object_key for item in objects}) != len(objects):
                return None
            if _fingerprint(item.object_key for item in objects) != object_fingerprint:
                return None
            return cls(video_count, video_fingerprint, object_fingerprint, tuple(objects))
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class VerificationResult:
    run_id: UUID
    verified: bool
    source_committed_count: int
    video_count_unchanged: bool
    object_set_unchanged_except_expected: bool
    workspace_clean: bool
    transcript_valid: bool
    items: tuple[dict[str, object], ...]
    reason_code: str | None = None


def capture_run_baseline(
    sessions: sessionmaker[Session], minio_client: Any, bucket: str
) -> RunBaseline:
    with sessions() as session:
        video_ids = [str(value) for value in session.scalars(select(Video.id)).all()]
    objects = tuple(_snapshot_objects(minio_client, bucket))
    return RunBaseline(
        video_count=len(video_ids),
        video_ids_sha256=_fingerprint(video_ids),
        source_object_keys_sha256=_fingerprint(item.object_key for item in objects),
        source_objects=objects,
    )


class CollectorPostRunVerifier:
    def __init__(self, sessions: sessionmaker[Session], minio_client, bucket: str) -> None:
        self._sessions = sessions
        self._client = minio_client
        self._bucket = bucket

    def verify(
        self,
        run_id: UUID,
        *,
        baseline: RunBaseline,
        transcript: list[dict[str, object]],
        workspace_root: Path,
    ) -> VerificationResult:
        with self._sessions() as session:
            run = session.get(InstagramCollectionRun, run_id)
            if run is None:
                return VerificationResult(
                    run_id, False, 0, False, False, False, False, (), "RUN_NOT_FOUND"
                )
            rows = session.execute(
                select(InstagramCollectionRunItem, InstagramReel)
                .join(InstagramReel, InstagramReel.id == InstagramCollectionRunItem.reel_id)
                .where(InstagramCollectionRunItem.run_id == run_id)
                .order_by(InstagramCollectionRunItem.position)
            ).all()
            account = session.get(InstagramAccount, run.account_id)
            video_ids = [str(value) for value in session.scalars(select(Video.id)).all()]
            video_unchanged = (
                len(video_ids) == baseline.video_count
                and _fingerprint(video_ids) == baseline.video_ids_sha256
            )
            items: list[dict[str, object]] = []
            valid = (
                account is not None
                and account.status == AccountStatus.CONNECTED.value
                and run.status == "completed"
                and run.target_count == 3
                and run.source_committed_count == 3
                and run.already_available_count == 0
                and run.failed_count == 0
                and len(rows) == 3
                and video_unchanged
            )
            expected_keys: set[str] = set()
            for position, (item, reel) in enumerate(rows, start=1):
                if reel.source_object_key:
                    expected_keys.add(reel.source_object_key)
                object_valid = self._object_matches(
                    reel.source_object_key,
                    reel.source_sha256,
                    reel.source_byte_size,
                )
                pending_jobs = session.scalar(
                    select(func.count()).select_from(InstagramNormalizationJob).where(
                        InstagramNormalizationJob.reel_id == reel.id,
                        InstagramNormalizationJob.status == NormalizationJobStatus.PENDING.value,
                    )
                )
                item_valid = (
                    item.position == position
                    and item.outcome == RunItemOutcome.SOURCE_COMMITTED.value
                    and item.download_auth_mode == DownloadAuthMode.SESSION_FIRST.value
                    and reel.pipeline_status == ReelPipelineStatus.SOURCE_READY.value
                    and reel.video_id is None
                    and pending_jobs == 1
                    and object_valid
                )
                valid = valid and item_valid
                items.append(
                    {
                        "position": position,
                        "shortcode": reel.shortcode,
                        "object_key": reel.source_object_key,
                        "byte_size": reel.source_byte_size,
                        "sha256": reel.source_sha256,
                        "valid": item_valid,
                    }
                )

        current_objects = {
            item.object_key: item for item in _snapshot_objects(self._client, self._bucket)
        }
        baseline_objects = {item.object_key: item for item in baseline.source_objects}
        expected_after = set(baseline_objects) | expected_keys
        exact_delta = set(current_objects) == expected_after
        baseline_unchanged = all(
            current_objects.get(key) == value for key, value in baseline_objects.items()
        )
        clean_object_names = all(not _is_temporary_name(key) for key in current_objects)
        object_set_valid = exact_delta and baseline_unchanged and clean_object_names
        workspace_clean = _workspace_is_clean(workspace_root)
        transcript_valid = validate_event_transcript(transcript, status=run.status, target_count=3)
        valid = valid and object_set_valid and workspace_clean and transcript_valid
        return VerificationResult(
            run_id,
            bool(valid),
            3 if valid else 0,
            video_unchanged,
            object_set_valid,
            workspace_clean,
            transcript_valid,
            tuple(items),
            None if valid else "POST_RUN_VERIFICATION_FAILED",
        )

    def _object_matches(
        self, key: str | None, expected_sha: str | None, expected_size: int | None
    ) -> bool:
        if not key or not expected_sha or not expected_size:
            return False
        try:
            item = _snapshot_object(self._client, self._bucket, key)
            return (
                item.byte_size == expected_size
                and item.content_type == "video/mp4"
                and item.sha256 == expected_sha
            )
        except Exception:
            return False


def _snapshot_objects(client: Any, bucket: str) -> list[BaselineObject]:
    objects: list[BaselineObject] = []
    try:
        listed = client.list_objects(bucket, prefix=SOURCE_PREFIX, recursive=True)
        keys = sorted(
            item.object_name
            for item in listed
            if isinstance(getattr(item, "object_name", None), str)
        )
        for key in keys:
            objects.append(_snapshot_object(client, bucket, key))
    except Exception:
        raise RuntimeError("MINIO_VERIFICATION_FAILED") from None
    return objects


def _snapshot_object(client: Any, bucket: str, key: str) -> BaselineObject:
    stat = client.stat_object(bucket, key)
    response = None
    try:
        response = client.get_object(bucket, key)
        digest = hashlib.sha256()
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
        return BaselineObject(
            key,
            int(stat.size),
            digest.hexdigest(),
            stat.content_type or "",
        )
    finally:
        if response is not None:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass


def _fingerprint(values) -> str:
    payload = "\n".join(sorted(values)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_temporary_name(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered.endswith((".part", ".ytdl", ".tmp"))
        or ".collector." in lowered
        or "staging" in lowered
        or "temporary" in lowered
    )


def _workspace_is_clean(workspace_root: Path) -> bool:
    root = workspace_root.resolve(strict=False)
    temporary = root / "temporary"
    if temporary.exists() and any(path.is_file() for path in temporary.rglob("*")):
        return False
    return not any(
        path.is_file() and _is_temporary_name(path.name)
        for path in root.rglob("*")
        if "results" not in path.parts and "operator-state" not in path.parts
    )


def validate_event_transcript(
    events: list[dict[str, object]], *, status: str, target_count: int
) -> bool:
    committed_prefix = ["detect", "pause", "download", "validation", "publish", "db_commit"]
    transition_prefix = [*committed_prefix, "cooldown", "advance"]
    actual: dict[int, list[str]] = {}
    for item in events:
        position = item.get("position")
        event = item.get("event")
        if not isinstance(position, int) or not isinstance(event, str):
            return False
        actual.setdefault(position, []).append(event)
    positions = sorted(actual)
    if positions != list(range(1, len(positions) + 1)):
        return False
    for position, sequence in actual.items():
        if position == 3 and any(
            event in {"cooldown", "advance", "advance_retry"} for event in sequence
        ):
            return False
        if sequence[: len(committed_prefix)] != committed_prefix[: len(sequence)]:
            return False
        if len(sequence) <= len(committed_prefix):
            continue
        if (
            len(sequence) <= len(transition_prefix)
            and sequence != transition_prefix[: len(sequence)]
        ):
            return False
        if (
            len(sequence) > len(transition_prefix)
            and sequence[: len(transition_prefix)] != transition_prefix
        ):
            return False
        suffix = sequence[len(transition_prefix) :]
        if suffix not in (
            [],
            ["transition_confirmed"],
            ["advance_retry"],
            ["advance_retry", "transition_confirmed"],
        ):
            return False
        if suffix.count("advance_retry") > 1:
            return False
        if "advance" in sequence and "db_commit" not in sequence:
            return False
    # A later Reel can only be detected after the previous transition is confirmed.
    for position in positions[:-1]:
        if actual[position][-1:] != ["transition_confirmed"]:
            return False
    if status == "completed":
        if target_count != 3 or positions != [1, 2, 3]:
            return False
        return (
            actual[1][-1:] == ["transition_confirmed"]
            and actual[2][-1:] == ["transition_confirmed"]
            and actual[3] == committed_prefix
        )
    return status in {"failed", "cancelled"}
