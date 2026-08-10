"""Read-only ffprobe/full-decode verification of one catalog canonical object."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.core.settings import get_settings
from app.db.models.video import Video
from app.db.session import create_session_factory
from app.media.compatibility import is_canonical_media
from app.media.normalize import validate_decode
from app.media.probe import probe_media
from app.storage.minio import MinioVideoStorage


def main() -> int:
    try:
        settings = get_settings()
        with create_session_factory(settings)() as session:
            object_key = session.scalar(
                select(Video.object_key).order_by(Video.created_at).limit(1)
            )
        if object_key is None:
            print(json.dumps({"event": "failed", "reason_code": "SOURCE_MISSING"}))
            return 1
        with tempfile.TemporaryDirectory(prefix="offline-reels-verify-") as directory:
            media_path = Path(directory) / "canonical.mp4"
            MinioVideoStorage(settings).download_file(object_key, media_path)
            probe = probe_media(media_path)
            validate_decode(media_path)
        if not probe.audio_codecs or not is_canonical_media(probe):
            print(json.dumps({"event": "failed", "reason_code": "INCOMPATIBLE_OUTPUT"}))
            return 1
        print(
            json.dumps(
                {
                    "audio_codecs": list(probe.audio_codecs),
                    "duration_positive": probe.duration_seconds is not None
                    and probe.duration_seconds > 0,
                    "full_decode": True,
                    "pixel_format": probe.pixel_format,
                    "video_codec": probe.video_codec,
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(json.dumps({"event": "failed", "reason_code": "FULL_DECODE_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
