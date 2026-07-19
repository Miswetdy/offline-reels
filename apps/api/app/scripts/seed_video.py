import argparse
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
    arguments = parser.parse_args()

    settings = get_settings()
    service = VideoService(
        create_session_factory(settings),
        VideoRepository(),
        MinioVideoStorage(settings),
    )
    try:
        video = service.seed_file(arguments.file, arguments.title)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(video.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
