import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.media.errors import MediaProbeError
from app.media.models import MediaProbe, NormalizationStrategy, NormalizedMedia
from app.services.videos import SeedFile, SeedResult


def make_result() -> SeedResult:
    probe = MediaProbe(
        path=Path("normalized.mp4"),
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codecs=("aac",),
        duration_seconds=1.25,
        width=128,
        height=72,
        video_profile="Main",
        video_level=41,
    )
    media = NormalizedMedia(
        source_path=Path("source.mp4"),
        output_path=Path("normalized.mp4"),
        strategy=NormalizationStrategy.TRANSCODE,
        original_probe=MediaProbe(
            path=Path("source.mp4"),
            video_codec="vp9",
            pixel_format="yuv420p",
            audio_codecs=(),
            duration_seconds=1.25,
            width=128,
            height=72,
        ),
        probe=probe,
    )
    return SeedResult(
        video=SimpleNamespace(id=UUID(int=1)),
        outcome="created",
        original_file=SeedFile(Path("source.mp4"), 5, "source-hash"),
        normalized_file=SeedFile(Path("normalized.mp4"), 10, "normalized-hash"),
        normalized_media=media,
    )


@pytest.mark.parametrize("output_format", ["id", "json"])
def test_seed_video_cli_preserves_id_and_expands_json_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    from app.scripts import seed_video

    service = MagicMock()
    service.seed_file_with_result.return_value = make_result()
    monkeypatch.setattr(seed_video, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(seed_video, "create_session_factory", lambda _settings: MagicMock())
    monkeypatch.setattr(seed_video, "VideoRepository", MagicMock)
    monkeypatch.setattr(seed_video, "MinioVideoStorage", lambda _settings: MagicMock())
    monkeypatch.setattr(seed_video, "VideoService", lambda *_args: service)
    monkeypatch.setattr(
        sys,
        "argv",
        ["seed_video", "--file", "source.mp4", "--format", output_format],
    )

    assert seed_video.main() == 0
    captured = capsys.readouterr()
    stdout = captured.out
    assert captured.err == ""
    if output_format == "id":
        assert stdout == f"{UUID(int=1)}\n"
        return

    payload = json.loads(stdout)
    assert stdout == f"{json.dumps(payload)}\n"
    assert payload == {
        "id": str(UUID(int=1)),
        "outcome": "created",
        "normalization_strategy": "transcode",
        "original_codec": "vp9",
        "normalized_codec": "h264",
        "width": 128,
        "height": 72,
        "duration": 1.25,
        "file_size_bytes": 10,
        "has_audio": True,
    }


def test_seed_video_cli_reports_expected_media_errors_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.scripts import seed_video

    service = MagicMock()
    service.seed_file_with_result.side_effect = MediaProbeError("Media is invalid.")
    monkeypatch.setattr(seed_video, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(seed_video, "create_session_factory", lambda _settings: MagicMock())
    monkeypatch.setattr(seed_video, "VideoRepository", MagicMock)
    monkeypatch.setattr(seed_video, "MinioVideoStorage", lambda _settings: MagicMock())
    monkeypatch.setattr(seed_video, "VideoService", lambda *_args: service)
    monkeypatch.setattr(sys, "argv", ["seed_video", "--file", "corrupt.mp4"])

    with pytest.raises(SystemExit) as exited:
        seed_video.main()

    assert exited.value.code == 2
    stderr = capsys.readouterr().err
    assert "Media is invalid." in stderr
    assert "Traceback" not in stderr
