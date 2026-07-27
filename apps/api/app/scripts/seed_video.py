import argparse
import json
import logging
from pathlib import Path

from app.core.settings import get_settings
from app.db.session import create_session_factory
from app.media.errors import MediaNormalizationError
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService
from app.storage.minio import MinioVideoStorage

LOGGER = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed one MP4 video into Offline Reels.")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--format", choices=("id", "json"), default="id")
    arguments = parser.parse_args()

    settings = get_settings()
    service = VideoService(
        create_session_factory(settings),
        VideoRepository(),
        MinioVideoStorage(settings),
    )
    try:
        result = service.seed_file_with_result(arguments.file, arguments.title)
    except (MediaNormalizationError, OSError, ValueError) as error:
        parser.error(str(error))
    except Exception:
        LOGGER.exception("Unexpected seed failure")
        parser.exit(1, "Seeding failed.\n")
    if arguments.format == "json":
        print(
            json.dumps(
                {
                    "id": str(result.video.id),
                    "outcome": result.outcome,
                    "normalization_strategy": result.normalized_media.strategy.value,
                    "original_codec": result.normalized_media.original_probe.video_codec,
                    "normalized_codec": result.normalized_media.probe.video_codec,
                    "width": result.normalized_media.probe.width,
                    "height": result.normalized_media.probe.height,
                    "duration": result.normalized_media.probe.duration_seconds,
                    "file_size_bytes": result.normalized_file.byte_size,
                    "has_audio": bool(result.normalized_media.probe.audio_codecs),
                }
            )
        )
    else:
        print(result.video.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
