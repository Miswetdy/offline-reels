from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.health import router as health_router
from app.api.management import install_management_error_handler
from app.api.management import router as management_router
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
    install_management_error_handler(app)

    @app.middleware("http")
    async def management_request_id(request: Request, call_next) -> Response:
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("X-Request-ID", request.state.request_id)
        if request.url.path.startswith(("/api/management/", "/api/instagram/", "/api/reserve/")):
            # Management and login-control DTOs can contain short-lived
            # capabilities.  They are never eligible for intermediary or SW
            # caching, including safe status polling responses.
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(
            {
                _origin
                for _origin in [
                    str(settings.frontend_origin).rstrip("/"),
                    str(settings.management_origin).rstrip("/"),
                ]
            }
        ),
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Range", "Cache-Control", "Idempotency-Key", "X-CSRF-Token", "Content-Type"],
        expose_headers=["Accept-Ranges", "Content-Range", "Content-Length", "Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(videos_router)
    app.include_router(management_router)
    return app


app = create_app()
