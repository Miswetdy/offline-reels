from collections.abc import Iterator
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.schemas.videos import VideoResponse
from app.media.ranges import RangeNotSatisfiable, parse_single_range
from app.services.videos import CHUNK_SIZE, VideoNotFound, VideoObjectNotFound, VideoService

router = APIRouter(tags=["videos"])


def get_video_service(request: Request) -> VideoService:
    return request.app.state.video_service


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.get("/videos", response_model=list[VideoResponse])
def list_videos(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[VideoResponse]:
    return get_video_service(request).list(limit)


@router.get("/videos/{video_id}", response_model=VideoResponse)
def get_video(request: Request, video_id: UUID) -> VideoResponse:
    try:
        return get_video_service(request).get(video_id)
    except VideoNotFound:
        raise error(status.HTTP_404_NOT_FOUND, "video_not_found", "Video was not found.") from None


@router.get("/videos/{video_id}/stream")
def stream_video(
    request: Request,
    video_id: UUID,
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    service = get_video_service(request)
    try:
        stream_info = service.get_stream_info(video_id)
    except VideoNotFound:
        raise error(status.HTTP_404_NOT_FOUND, "video_not_found", "Video was not found.") from None
    except VideoObjectNotFound:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "video_object_not_found",
            "Video media is unavailable.",
        ) from None

    total_size = stream_info.object_metadata.byte_size
    try:
        byte_range = parse_single_range(range_header, total_size)
    except RangeNotSatisfiable:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{total_size}"},
            detail={
                "code": "range_not_satisfiable",
                "message": "Requested range is not satisfiable.",
            },
        ) from None

    start = byte_range.start if byte_range is not None else 0
    end = byte_range.end if byte_range is not None else total_size - 1
    try:
        upstream = service.open_stream(stream_info.video.object_key, start, end - start + 1)
    except VideoObjectNotFound:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "video_object_not_found",
            "Video media is unavailable.",
        ) from None

    def stream_chunks() -> Iterator[bytes]:
        try:
            yield from upstream.stream(CHUNK_SIZE)
        finally:
            upstream.close()
            upstream.release_conn()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    response_status = status.HTTP_200_OK
    if byte_range is not None:
        response_status = status.HTTP_206_PARTIAL_CONTENT
        headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"

    return StreamingResponse(
        stream_chunks(),
        status_code=response_status,
        media_type=stream_info.video.content_type,
        headers=headers,
    )
