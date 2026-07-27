import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.media.errors import MediaDecodeError, MediaNormalizationCommandError
from app.media.models import MediaProbe, NormalizationStrategy
from app.media.normalize import (
    _remux_command,
    _run_normalization,
    _transcode_command,
    normalize_video,
    validate_decode,
)


def canonical_probe(path: Path) -> MediaProbe:
    return MediaProbe(
        path=path,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codecs=(),
        duration_seconds=1.0,
        width=720,
        height=1280,
    )


def test_decode_validation_maps_ffmpeg_failure_to_typed_error() -> None:
    failed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stdout="", stderr="broken")

    with patch("app.media.normalize.subprocess.run", return_value=failed):
        with pytest.raises(MediaDecodeError):
            validate_decode(Path("input.mp4"))


def test_normalization_command_maps_ffmpeg_failure_to_typed_error(tmp_path: Path) -> None:
    failed = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stdout="", stderr="broken")

    with patch("app.media.normalize.subprocess.run", return_value=failed):
        with pytest.raises(MediaNormalizationCommandError):
            _run_normalization(
                tmp_path / "input.mp4",
                tmp_path / "temporary.mp4",
                NormalizationStrategy.REMUX,
                timeout_seconds=1,
            )


def test_remux_and_transcode_commands_preserve_canonical_output_contract(tmp_path: Path) -> None:
    source = tmp_path / "input.mp4"
    output = tmp_path / "output.mp4"

    remux = _remux_command(source, output)
    transcode = _transcode_command(source, output)

    assert ["-c", "copy"] == remux[remux.index("-c") : remux.index("-c") + 2]
    assert "+faststart" in remux
    assert ["-c:v", "libx264"] == transcode[
        transcode.index("-c:v") : transcode.index("-c:v") + 2
    ]
    assert ["-profile:v", "main"] == transcode[
        transcode.index("-profile:v") : transcode.index("-profile:v") + 2
    ]
    assert ["-level:v", "4.1"] == transcode[
        transcode.index("-level:v") : transcode.index("-level:v") + 2
    ]
    assert ["-pix_fmt", "yuv420p"] == transcode[
        transcode.index("-pix_fmt") : transcode.index("-pix_fmt") + 2
    ]
    assert ["-crf", "23"] == transcode[transcode.index("-crf") : transcode.index("-crf") + 2]
    assert ["-c:a", "aac"] == transcode[transcode.index("-c:a") : transcode.index("-c:a") + 2]
    assert ["-b:a", "128k"] == transcode[
        transcode.index("-b:a") : transcode.index("-b:a") + 2
    ]
    assert "+faststart" in transcode


def test_normalize_video_keeps_output_readable_only_inside_controlled_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.mp4"
    source.write_bytes(b"source")

    def fake_run(
        source_path: Path, temporary_path: Path, *_args: object, **_kwargs: object
    ) -> None:
        assert source_path == source.resolve()
        temporary_path.write_bytes(b"normalized")

    monkeypatch.setattr(
        "app.media.normalize.probe_media", lambda path, **_kwargs: canonical_probe(path)
    )
    monkeypatch.setattr("app.media.normalize.validate_decode", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.media.normalize._run_normalization", fake_run)

    with normalize_video(source) as result:
        output_path = result.output_path
        assert result.strategy is NormalizationStrategy.REMUX
        assert output_path.exists()
        assert output_path.read_bytes() == b"normalized"

    assert not output_path.exists()


def test_normalize_video_cleans_output_after_exception_inside_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.mp4"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        "app.media.normalize.probe_media", lambda path, **_kwargs: canonical_probe(path)
    )
    monkeypatch.setattr("app.media.normalize.validate_decode", lambda *_args, **_kwargs: None)

    def write_output(
        _source: Path, temporary_path: Path, *_args: object, **_kwargs: object
    ) -> None:
        temporary_path.write_bytes(b"normalized")

    monkeypatch.setattr("app.media.normalize._run_normalization", write_output)

    with pytest.raises(RuntimeError, match="upload failed"):
        with normalize_video(source) as result:
            output_path = result.output_path
            assert output_path.exists()
            assert output_path.read_bytes() == b"normalized"
            raise RuntimeError("upload failed")

    assert not output_path.exists()
