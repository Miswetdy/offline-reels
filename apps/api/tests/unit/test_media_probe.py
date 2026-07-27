import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.media.errors import MediaProbeError, MediaProbeTimeoutError
from app.media.probe import probe_media


def test_probe_media_parses_primary_video_and_audio_streams() -> None:
    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout=(
            '{"format":{"duration":"1.25"},"streams":['
            '{"codec_type":"video","codec_name":"h264","pix_fmt":"yuv420p",'
            '"profile":"Main","level":41,"width":720,"height":1280},'
            '{"codec_type":"audio","codec_name":"aac"}]}'
        ),
        stderr="",
    )

    with patch("app.media.probe.subprocess.run", return_value=completed) as run:
        result = probe_media(Path("input.mp4"), timeout_seconds=7)

    assert result.video_codec == "h264"
    assert result.pixel_format == "yuv420p"
    assert result.audio_codecs == ("aac",)
    assert result.duration_seconds == 1.25
    assert (result.width, result.height) == (720, 1280)
    assert result.video_profile == "Main"
    assert result.video_level == 41
    assert run.call_args.kwargs["timeout"] == 7
    assert "shell" not in run.call_args.kwargs


def test_probe_media_rejects_malformed_json() -> None:
    completed = subprocess.CompletedProcess(args=["ffprobe"], returncode=0, stdout="{", stderr="")

    with patch("app.media.probe.subprocess.run", return_value=completed):
        with pytest.raises(MediaProbeError, match="malformed JSON"):
            probe_media(Path("input.mp4"))


def test_probe_media_rejects_missing_video_stream() -> None:
    completed = subprocess.CompletedProcess(
        args=["ffprobe"],
        returncode=0,
        stdout='{"format":{"duration":"1"},"streams":[]}',
        stderr="",
    )

    with patch("app.media.probe.subprocess.run", return_value=completed):
        with pytest.raises(MediaProbeError, match="no video stream"):
            probe_media(Path("input.mp4"))


def test_probe_media_maps_timeout_to_typed_error() -> None:
    with patch(
        "app.media.probe.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1),
    ):
        with pytest.raises(MediaProbeTimeoutError):
            probe_media(Path("input.mp4"))
