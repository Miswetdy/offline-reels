import argparse
import json
from pathlib import Path

from app.core.settings import get_settings
from app.db.session import create_session_factory
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService
from app.storage.minio import MinioVideoStorage


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
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if arguments.format == "json":
        print(json.dumps({"id": str(result.video.id), "outcome": result.outcome}))
    else:
        print(result.video.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
