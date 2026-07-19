from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.videos import router as videos_router
from app.core.settings import get_settings
from app.db.session import create_session_factory
from app.repositories.videos import VideoRepository
from app.services.videos import VideoService
from app.storage.minio import MinioVideoStorage


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Offline Reels API", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings)
    app.state.video_service = VideoService(
        app.state.session_factory,
        VideoRepository(),
        MinioVideoStorage(settings),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.frontend_origin).rstrip("/")],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Range"],
        expose_headers=["Accept-Ranges", "Content-Range", "Content-Length"],
    )
    app.include_router(health_router)
    app.include_router(videos_router)
    return app


app = create_app()
