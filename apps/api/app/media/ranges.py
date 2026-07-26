from dataclasses import dataclass


class RangeNotSatisfiable(ValueError):
    pass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_single_range(value: str | None, total_size: int) -> ByteRange | None:
    if value is None:
        return None
    if total_size <= 0 or not value.startswith("bytes="):
        raise RangeNotSatisfiable

    specifier = value.removeprefix("bytes=").strip()
    if not specifier or "," in specifier or specifier.count("-") != 1:
        raise RangeNotSatisfiable

    start_value, end_value = (item.strip() for item in specifier.split("-", maxsplit=1))
    try:
        if not start_value:
            suffix_length = int(end_value)
            if suffix_length <= 0:
                raise RangeNotSatisfiable
            start = max(total_size - suffix_length, 0)
            return ByteRange(start=start, end=total_size - 1)

        start = int(start_value)
        if start < 0 or start >= total_size:
            raise RangeNotSatisfiable
        end = total_size - 1 if not end_value else min(int(end_value), total_size - 1)
        if end < start:
            raise RangeNotSatisfiable
        return ByteRange(start=start, end=end)
    except ValueError:
        raise RangeNotSatisfiable from None
