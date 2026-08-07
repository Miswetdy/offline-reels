"""Session-first, bounded yt-dlp adapter with no persisted browser state."""

import os
from collections.abc import Callable
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Protocol

from app.instagram.collector.canonical import validate_candidate
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.session_cookies import SessionCookieJar

MAX_RETRIES = 1
SOCKET_TIMEOUT_SECONDS = 30


class YtDlpFacade(Protocol):
    def download(
        self,
        candidate: ReelCandidate,
        cookie_jar: SessionCookieJar,
        temporary_path: Path,
        maximum_bytes: int,
    ) -> None: ...


class SessionFirstYtDlpDownloader:
    def __init__(
        self,
        cookie_jar: SessionCookieJar,
        *,
        maximum_bytes: int,
        facade: YtDlpFacade | None = None,
    ) -> None:
        self._cookie_jar = cookie_jar
        self._maximum_bytes = maximum_bytes
        self._facade = facade or PythonYtDlpFacade()

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        validate_candidate(candidate)
        try:
            self._facade.download(candidate, self._cookie_jar, temporary_path, self._maximum_bytes)
            if not temporary_path.is_file() or temporary_path.stat().st_size > self._maximum_bytes:
                raise CollectorRuntimeError(RuntimeReasonCode.DOWNLOAD_FAILED)
        except CollectorRuntimeError:
            _cleanup(temporary_path)
            raise
        except Exception as error:
            _cleanup(temporary_path)
            raise CollectorRuntimeError(RuntimeReasonCode.DOWNLOAD_FAILED) from error
        finally:
            self._cookie_jar.clear()


class PythonYtDlpFacade:
    def __init__(
        self,
        youtube_dl_factory: Callable[[dict[str, object]], object] | None = None,
    ) -> None:
        self._youtube_dl_factory = youtube_dl_factory

    def download(
        self,
        candidate: ReelCandidate,
        cookie_jar: SessionCookieJar,
        temporary_path: Path,
        maximum_bytes: int,
    ) -> None:
        factory = self._youtube_dl_factory
        if factory is None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError as error:
                raise CollectorRuntimeError(RuntimeReasonCode.DOWNLOAD_FAILED) from error
            factory = YoutubeDL
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        stem = f".{temporary_path.stem}.collector"
        template = str(temporary_path.parent / f"{stem}.%(ext)s")
        options = build_yt_dlp_options(template, maximum_bytes)
        http_cookie_jar = cookie_jar.to_http_cookiejar()
        ydl = None
        try:
            with factory(options) as ydl:
                ydl.cookiejar = http_cookie_jar
                ydl.extract_info(candidate.canonical_url, download=True)
            outputs = [
                path
                for path in temporary_path.parent.glob(f"{stem}.*")
                if path.is_file() and path.suffix not in {".part", ".ytdl"}
            ]
            if len(outputs) != 1:
                raise CollectorRuntimeError(RuntimeReasonCode.DOWNLOAD_FAILED)
            os.replace(outputs[0], temporary_path)
        finally:
            # The HTTP CookieJar is an attempt-local copy.  Do not leave it in
            # a facade or yt-dlp instance after this one bounded attempt.
            http_cookie_jar.clear()
            if ydl is not None:
                try:
                    ydl.cookiejar = CookieJar()
                except Exception:
                    pass
            for artifact in temporary_path.parent.glob(f"{stem}.*"):
                if artifact.is_file():
                    artifact.unlink(missing_ok=True)


def _format_selector() -> str:
    limit = "[width<=1080][height<=1920]"
    return (
        f"bestvideo[vcodec^=avc1]{limit}+bestaudio[acodec^=mp4a]/"
        f"best[vcodec^=avc1][acodec^=mp4a]{limit}/"
        f"bestvideo{limit}+bestaudio/best{limit}"
    )


def build_yt_dlp_options(output_template: str, maximum_bytes: int) -> dict[str, object]:
    """Return bounded anonymous-disabled options without cookie/header persistence knobs."""
    return {
        "noplaylist": True,
        "playlistend": 1,
        "format": _format_selector(),
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "max_filesize": maximum_bytes,
        "socket_timeout": SOCKET_TIMEOUT_SECONDS,
        "retries": MAX_RETRIES,
        "fragment_retries": MAX_RETRIES,
        "quiet": True,
        "no_warnings": True,
        "logger": _RedactingLogger(),
    }


class _RedactingLogger:
    def debug(self, message: str) -> None:
        del message

    def warning(self, message: str) -> None:
        del message

    def error(self, message: str) -> None:
        del message


def _cleanup(path: Path) -> None:
    path.unlink(missing_ok=True)
