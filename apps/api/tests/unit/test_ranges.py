import pytest

from app.media.ranges import ByteRange, RangeNotSatisfiable, parse_single_range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-4", ByteRange(0, 4)),
        ("bytes=3-", ByteRange(3, 9)),
        ("bytes=-4", ByteRange(6, 9)),
        ("bytes=8-99", ByteRange(8, 9)),
    ],
)
def test_parse_supported_single_ranges(header: str, expected: ByteRange) -> None:
    assert parse_single_range(header, 10) == expected


@pytest.mark.parametrize(
    "header",
    ["bytes=", "bytes=10-", "bytes=3-2", "bytes=-0", "bytes=0-1,2-3", "items=0-1"],
)
def test_parse_rejects_invalid_or_multipart_ranges(header: str) -> None:
    with pytest.raises(RangeNotSatisfiable):
        parse_single_range(header, 10)


def test_no_range_returns_none() -> None:
    assert parse_single_range(None, 10) is None
