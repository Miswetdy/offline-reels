from pathlib import Path

import pytest

from app.services.videos import inspect_mp4_file


def test_inspect_mp4_file_hashes_content_without_loading_whole_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.mp4"
    file_path.write_bytes(b"test-video")

    result = inspect_mp4_file(file_path)

    assert result.byte_size == 10
    assert result.sha256 == "4195487bb892e9c9485808a64488f2f67091aceef0a7b118a1695c04c54fbc40"


@pytest.mark.parametrize("name,content", [("not-video.txt", b"video"), ("empty.mp4", b"")])
def test_inspect_mp4_file_rejects_invalid_seed_file(
    tmp_path: Path, name: str, content: bytes
) -> None:
    file_path = tmp_path / name
    file_path.write_bytes(content)

    with pytest.raises(ValueError):
        inspect_mp4_file(file_path)
