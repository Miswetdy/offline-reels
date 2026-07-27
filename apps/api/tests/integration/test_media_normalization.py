import shutil
import subprocess
from pathlib import Path

import pytest

from app.media.compatibility import is_canonical_media
from app.media.errors import MediaProbeError
from app.media.models import NormalizationStrategy
from app.media.normalize import normalize_video
from app.media.probe import probe_media


@pytest.fixture(autouse=True)
def isolated_test_data() -> None:
    """This file tests local ffmpeg only and intentionally needs no MinIO/DB."""


def run_ffmpeg(*arguments: str) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.fail("The API image must provide ffmpeg and ffprobe for media normalization.")
    subprocess.run(["ffmpeg", "-y", "-v", "error", *arguments], check=True)


def create_h264_fixture(path: Path, *, with_audio: bool = False) -> None:
    arguments = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x72:rate=24",
    ]
    if with_audio:
        arguments.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=44100",
            ]
        )
    arguments.extend(["-t", "1", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        arguments.extend(["-c:a", "aac"])
    arguments.append(str(path))
    run_ffmpeg(*arguments)


def create_vp9_fixture(path: Path, *, with_audio: bool = False) -> None:
    arguments = [
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=128x72:rate=24",
    ]
    if with_audio:
        arguments.extend(
            [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=44100",
            ]
        )
    arguments.extend(["-t", "1", "-shortest", "-c:v", "libvpx-vp9", "-b:v", "250k"])
    if with_audio:
        arguments.extend(["-c:a", "libopus"])
    arguments.extend(["-pix_fmt", "yuv420p", str(path)])
    run_ffmpeg(*arguments)


def test_h264_source_without_audio_is_remuxed_and_verified(tmp_path: Path) -> None:
    source = tmp_path / "source-h264.mp4"
    create_h264_fixture(source)

    with normalize_video(source) as result:
        output_path = result.output_path
        assert output_path.stat().st_size > 0
        assert result.strategy is NormalizationStrategy.REMUX
        assert result.probe.video_codec == "h264"
        assert result.probe.pixel_format == "yuv420p"
        assert result.probe.audio_codecs == ()
        assert is_canonical_media(result.probe)

    assert not output_path.exists()


def test_vp9_source_is_transcoded_to_canonical_h264(tmp_path: Path) -> None:
    source = tmp_path / "source-vp9.mp4"
    create_vp9_fixture(source)

    with normalize_video(source) as result:
        output_probe = probe_media(result.output_path)
        assert result.strategy is NormalizationStrategy.TRANSCODE
        assert output_probe.video_codec == "h264"
        assert output_probe.pixel_format == "yuv420p"
        assert output_probe.video_profile == "Main"
        assert output_probe.video_level == 41
        assert output_probe.width is not None and output_probe.width > 0
        assert output_probe.height is not None and output_probe.height > 0
        assert output_probe.duration_seconds is not None and output_probe.duration_seconds > 0
        assert output_probe.audio_codecs == ()
        assert is_canonical_media(output_probe)

    assert not result.output_path.exists()


def test_h264_source_with_aac_is_remuxed(tmp_path: Path) -> None:
    source = tmp_path / "source-h264-aac.mp4"
    create_h264_fixture(source, with_audio=True)

    with normalize_video(source) as result:
        assert result.strategy is NormalizationStrategy.REMUX
        assert result.probe.audio_codecs == ("aac",)
        assert is_canonical_media(result.probe)



def test_corrupt_input_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.mp4"
    source.write_bytes(b"not a media file")

    with pytest.raises(MediaProbeError, match="ffprobe"):
        with normalize_video(source):
            pytest.fail("Corrupt input must not yield a normalized output.")
