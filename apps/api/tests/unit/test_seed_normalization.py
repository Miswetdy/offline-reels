from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.media.errors import MediaProbeError
from app.media.models import MediaProbe, NormalizationStrategy, NormalizedMedia
from app.repositories.videos import VideoUpsertResult
from app.services.videos import SeedFile, VideoService
from app.storage.base import ObjectMetadata, StorageObjectNotFound


def make_probe(codec: str) -> MediaProbe:
    return MediaProbe(
        path=Path("fixture.mp4"),
        video_codec=codec,
        pixel_format="yuv420p",
        audio_codecs=(),
        duration_seconds=1.25,
        width=128,
        height=72,
        video_profile="Main",
        video_level=41,
    )


def make_normalized_media(output_path: Path, strategy: NormalizationStrategy) -> NormalizedMedia:
    original_codec = "h264" if strategy is NormalizationStrategy.REMUX else "vp9"
    return NormalizedMedia(
        source_path=Path("source.mp4"),
        output_path=output_path,
        strategy=strategy,
        original_probe=make_probe(original_codec),
        probe=make_probe("h264"),
    )


@contextmanager
def normalized_scope(result: NormalizedMedia) -> Iterator[NormalizedMedia]:
    result.output_path.write_bytes(b"normalized")
    try:
        yield result
    finally:
        result.output_path.unlink(missing_ok=True)


def make_service(
    session: MagicMock,
    repository: MagicMock,
    storage: MagicMock,
) -> VideoService:
    @contextmanager
    def session_scope() -> Iterator[MagicMock]:
        yield session

    return VideoService(lambda: session_scope(), repository, storage)


@pytest.mark.parametrize(
    ("strategy", "original_codec"),
    [
        (NormalizationStrategy.REMUX, "h264"),
        (NormalizationStrategy.TRANSCODE, "vp9"),
    ],
)
def test_seed_uploads_only_normalized_media_and_persists_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    strategy: NormalizationStrategy,
    original_codec: str,
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "normalized.mp4"
    source.write_bytes(b"source")
    normalized = make_normalized_media(output, strategy)
    session = MagicMock()
    repository = MagicMock()
    video = SimpleNamespace(id=UUID(int=1))
    repository.upsert.return_value = VideoUpsertResult(video=video, created=True)
    storage = MagicMock()
    storage.stat.side_effect = StorageObjectNotFound

    def upload_while_output_is_owned(
        _object_key: str, uploaded_path: Path, _content_type: str
    ) -> None:
        assert uploaded_path == output
        assert uploaded_path.exists()
        assert uploaded_path.read_bytes() == b"normalized"

    storage.upload_file.side_effect = upload_while_output_is_owned
    service = make_service(session, repository, storage)
    original_file = SeedFile(source, byte_size=6, sha256="original-hash")
    normalized_file = SeedFile(output, byte_size=10, sha256="normalized-hash")

    monkeypatch.setattr(
        "app.services.videos.normalize_video", lambda _path: normalized_scope(normalized)
    )
    monkeypatch.setattr(
        "app.services.videos.inspect_mp4_file",
        lambda path: original_file if path == source else normalized_file,
    )

    result = service.seed_file_with_result(source, "Fixture")

    storage.upload_file.assert_called_once_with(
        "videos/normalized-hash.mp4", output, "video/mp4"
    )
    assert output.exists() is False
    assert result.normalized_media.strategy is strategy
    assert repository.upsert.call_args.kwargs["original_video_codec"] == original_codec
    assert repository.upsert.call_args.kwargs["normalized_video_codec"] == "h264"
    assert repository.upsert.call_args.kwargs["file_size_bytes"] == 10
    session.commit.assert_called_once()


def test_normalization_failure_does_not_upload_or_open_a_database_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    session = MagicMock()
    repository = MagicMock()
    storage = MagicMock()
    service = make_service(session, repository, storage)

    @contextmanager
    def fail_normalization(_path: Path) -> Iterator[NormalizedMedia]:
        raise MediaProbeError("Media is invalid.")
        yield  # pragma: no cover

    monkeypatch.setattr("app.services.videos.normalize_video", fail_normalization)

    with pytest.raises(MediaProbeError):
        service.seed_file_with_result(source)

    storage.ensure_bucket.assert_not_called()
    storage.upload_file.assert_not_called()
    repository.upsert.assert_not_called()
    session.commit.assert_not_called()


def test_upload_failure_does_not_create_a_database_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "normalized.mp4"
    source.write_bytes(b"source")
    normalized = make_normalized_media(output, NormalizationStrategy.REMUX)
    session = MagicMock()
    repository = MagicMock()
    storage = MagicMock()
    storage.stat.side_effect = StorageObjectNotFound
    storage.upload_file.side_effect = RuntimeError("storage unavailable")
    service = make_service(session, repository, storage)
    original_file = SeedFile(source, byte_size=6, sha256="original-hash")
    normalized_file = SeedFile(output, byte_size=10, sha256="normalized-hash")
    monkeypatch.setattr(
        "app.services.videos.normalize_video", lambda _path: normalized_scope(normalized)
    )
    monkeypatch.setattr(
        "app.services.videos.inspect_mp4_file",
        lambda path: original_file if path == source else normalized_file,
    )

    with pytest.raises(RuntimeError, match="storage unavailable"):
        service.seed_file_with_result(source)

    assert not output.exists()
    repository.upsert.assert_not_called()
    session.commit.assert_not_called()
    storage.remove.assert_called_once_with("videos/normalized-hash.mp4")


def test_database_failure_rolls_back_and_removes_new_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "normalized.mp4"
    source.write_bytes(b"source")
    normalized = make_normalized_media(output, NormalizationStrategy.REMUX)
    session = MagicMock()
    session.commit.side_effect = RuntimeError("database unavailable")
    repository = MagicMock()
    repository.upsert.return_value = VideoUpsertResult(
        video=SimpleNamespace(id=UUID(int=1)), created=True
    )
    storage = MagicMock()
    storage.stat.side_effect = StorageObjectNotFound
    service = make_service(session, repository, storage)
    original_file = SeedFile(source, byte_size=6, sha256="original-hash")
    normalized_file = SeedFile(output, byte_size=10, sha256="normalized-hash")
    monkeypatch.setattr(
        "app.services.videos.normalize_video", lambda _path: normalized_scope(normalized)
    )
    monkeypatch.setattr(
        "app.services.videos.inspect_mp4_file",
        lambda path: original_file if path == source else normalized_file,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.seed_file_with_result(source)

    session.rollback.assert_called_once()
    storage.remove.assert_called_once_with("videos/normalized-hash.mp4")
    assert not output.exists()


def test_database_failure_does_not_remove_an_existing_content_addressed_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "normalized.mp4"
    source.write_bytes(b"source")
    normalized = make_normalized_media(output, NormalizationStrategy.REMUX)
    session = MagicMock()
    session.commit.side_effect = RuntimeError("database unavailable")
    repository = MagicMock()
    repository.upsert.return_value = VideoUpsertResult(
        video=SimpleNamespace(id=UUID(int=1)), created=False
    )
    storage = MagicMock()
    storage.stat.return_value = ObjectMetadata(byte_size=10, content_type="video/mp4")
    service = make_service(session, repository, storage)
    original_file = SeedFile(source, byte_size=6, sha256="original-hash")
    normalized_file = SeedFile(output, byte_size=10, sha256="normalized-hash")
    monkeypatch.setattr(
        "app.services.videos.normalize_video", lambda _path: normalized_scope(normalized)
    )
    monkeypatch.setattr(
        "app.services.videos.inspect_mp4_file",
        lambda path: original_file if path == source else normalized_file,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.seed_file_with_result(source)

    storage.upload_file.assert_not_called()
    storage.remove.assert_not_called()
    session.rollback.assert_called_once()
    assert not output.exists()


def test_compensation_failure_is_logged_without_hiding_database_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "normalized.mp4"
    source.write_bytes(b"source")
    normalized = make_normalized_media(output, NormalizationStrategy.REMUX)
    session = MagicMock()
    session.commit.side_effect = RuntimeError("database unavailable")
    repository = MagicMock()
    repository.upsert.return_value = VideoUpsertResult(
        video=SimpleNamespace(id=UUID(int=1)), created=True
    )
    storage = MagicMock()
    from app.storage.base import StorageObjectNotFound

    storage.stat.side_effect = StorageObjectNotFound
    storage.remove.side_effect = RuntimeError("cleanup unavailable")
    service = make_service(session, repository, storage)
    original_file = SeedFile(source, byte_size=6, sha256="original-hash")
    normalized_file = SeedFile(output, byte_size=10, sha256="normalized-hash")
    monkeypatch.setattr(
        "app.services.videos.normalize_video", lambda _path: normalized_scope(normalized)
    )
    monkeypatch.setattr(
        "app.services.videos.inspect_mp4_file",
        lambda path: original_file if path == source else normalized_file,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.seed_file_with_result(source)

    assert "Could not compensate a failed video seed object upload." in caplog.text
