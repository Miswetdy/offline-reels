"""Session-first, bounded yt-dlp adapter with redacted attempt diagnostics."""

import errno
import os
import shutil
import socket
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.instagram.collector.canonical import validate_candidate
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.session_cookies import (
    SessionCookieJar,
    SessionCookieProvider,
)

MAX_RETRIES = 1
SOCKET_TIMEOUT_SECONDS = 30

_YTDLP_ERROR_MODULE = "yt_dlp"
_SAFE_MESSAGE_MARKERS: tuple[tuple[RuntimeReasonCode, tuple[str, ...]], ...] = (
    (
        RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED,
        (
            "login required",
            "sign in",
            "authentication required",
            "cookies are required",
            "http error 401",
            "http error 407",
        ),
    ),
    (RuntimeReasonCode.DIRECT_DOWNLOAD_FORBIDDEN, ("http error 403", "forbidden")),
    (
        RuntimeReasonCode.DIRECT_DOWNLOAD_RATE_LIMITED,
        ("http error 429", "too many requests", "rate limit"),
    ),
    (RuntimeReasonCode.DIRECT_DOWNLOAD_TIMEOUT, ("timed out", "timeout")),
    (
        RuntimeReasonCode.DIRECT_DOWNLOAD_NETWORK_FAILED,
        (
            "network is unreachable",
            "connection reset",
            "connection refused",
            "temporary failure in name resolution",
        ),
    ),
    (
        RuntimeReasonCode.DIRECT_DOWNLOAD_FORMAT_UNAVAILABLE,
        ("requested format is not available", "no video formats", "no supported format"),
    ),
    (
        RuntimeReasonCode.DIRECT_DOWNLOAD_SIZE_LIMIT,
        ("max filesize", "max-filesize", "file is larger than"),
    ),
)


@dataclass
class DownloadAttemptDiagnostics:
    """Only aggregate, non-secret information for one downloader attempt."""

    session_cookie_present: bool = False
    csrf_cookie_present: bool = False
    accepted_cookie_count: int = 0
    stage: str = "cookie_extraction"
    reason_code: str | None = None
    output_file_count: int = 0
    cleaned_partial_artifacts: bool = False

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "session_cookie_present": self.session_cookie_present,
            "csrf_cookie_present": self.csrf_cookie_present,
            "accepted_cookie_count": self.accepted_cookie_count,
            "stage": self.stage,
            "reason_code": self.reason_code,
            "output_file_count": self.output_file_count,
            "cleaned_partial_artifacts": self.cleaned_partial_artifacts,
        }


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
        self._last_diagnostics = DownloadAttemptDiagnostics()

    @property
    def last_diagnostics(self) -> dict[str, object]:
        return self._last_diagnostics.to_safe_dict()

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        validate_candidate(candidate)
        safe_presence = getattr(self._cookie_jar, "safe_presence", None)
        if callable(safe_presence):
            session_present, csrf_present, accepted_count = safe_presence()
        else:
            session_present, csrf_present, accepted_count = False, False, 0
        self._last_diagnostics = DownloadAttemptDiagnostics(
            session_cookie_present=session_present,
            csrf_cookie_present=csrf_present,
            accepted_cookie_count=accepted_count,
            stage="metadata_extraction",
        )
        try:
            self._facade.download(candidate, self._cookie_jar, temporary_path, self._maximum_bytes)
            self._copy_facade_diagnostics()
            if not temporary_path.is_file():
                raise CollectorRuntimeError(RuntimeReasonCode.DIRECT_DOWNLOAD_OUTPUT_MISSING)
            if temporary_path.stat().st_size > self._maximum_bytes:
                raise CollectorRuntimeError(RuntimeReasonCode.DIRECT_DOWNLOAD_SIZE_LIMIT)
        except CollectorRuntimeError as error:
            self._copy_facade_diagnostics()
            self._last_diagnostics.reason_code = error.code.value
            self._last_diagnostics.cleaned_partial_artifacts |= _cleanup_attempt_files(
                temporary_path
            )
            raise
        except Exception as error:
            code = _classify_download_exception(error)
            self._last_diagnostics.reason_code = code.value
            self._last_diagnostics.cleaned_partial_artifacts |= _cleanup_attempt_files(
                temporary_path
            )
            raise CollectorRuntimeError(code) from error
        finally:
            self._cookie_jar.clear()

    def _copy_facade_diagnostics(self) -> None:
        safe = getattr(self._facade, "last_diagnostics", None)
        if not isinstance(safe, dict):
            return
        for key in ("stage", "reason_code", "output_file_count", "cleaned_partial_artifacts"):
            value = safe.get(key)
            if key == "stage" and value in {
                "metadata_extraction",
                "media_download",
                "merge",
                "output_discovery",
            }:
                self._last_diagnostics.stage = value
            elif key == "reason_code" and isinstance(value, str):
                self._last_diagnostics.reason_code = value
            elif key == "output_file_count" and isinstance(value, int) and value >= 0:
                self._last_diagnostics.output_file_count = value
            elif key == "cleaned_partial_artifacts" and isinstance(value, bool):
                self._last_diagnostics.cleaned_partial_artifacts |= value


class FreshSessionFirstYtDlpDownloader:
    """Create and clear one in-memory CookieJar for every Reel attempt."""

    def __init__(
        self,
        cookie_context: Callable[[], object],
        *,
        maximum_bytes: int,
        provider: SessionCookieProvider | None = None,
        facade_factory: Callable[[], YtDlpFacade] | None = None,
    ) -> None:
        self._cookie_context = cookie_context
        self._maximum_bytes = maximum_bytes
        self._provider = provider or SessionCookieProvider()
        self._facade_factory = facade_factory or PythonYtDlpFacade
        self._attempt_diagnostics: list[dict[str, object]] = []

    @property
    def attempt_diagnostics(self) -> list[dict[str, object]]:
        return [dict(item) for item in self._attempt_diagnostics]

    def download(self, candidate: ReelCandidate, temporary_path: Path) -> None:
        jar: SessionCookieJar | None = None
        downloader: SessionFirstYtDlpDownloader | None = None
        diagnostics = DownloadAttemptDiagnostics()
        try:
            jar = self._provider.get(self._cookie_context())
            safe_presence = getattr(jar, "safe_presence", None)
            if callable(safe_presence):
                session_present, csrf_present, accepted_count = safe_presence()
                diagnostics.session_cookie_present = session_present
                diagnostics.csrf_cookie_present = csrf_present
                diagnostics.accepted_cookie_count = accepted_count
            downloader = SessionFirstYtDlpDownloader(
                jar,
                maximum_bytes=self._maximum_bytes,
                facade=self._facade_factory(),
            )
            downloader.download(candidate, temporary_path)
            diagnostics = _diagnostics_from_safe_dict(downloader.last_diagnostics, diagnostics)
        except CollectorRuntimeError as error:
            if downloader is not None:
                diagnostics = _diagnostics_from_safe_dict(
                    downloader.last_diagnostics, diagnostics
                )
            diagnostics.reason_code = error.code.value
            diagnostics.cleaned_partial_artifacts |= _cleanup_attempt_files(temporary_path)
            raise
        except Exception as error:
            diagnostics.reason_code = RuntimeReasonCode.DOWNLOAD_FAILED.value
            diagnostics.cleaned_partial_artifacts |= _cleanup_attempt_files(temporary_path)
            raise CollectorRuntimeError(RuntimeReasonCode.DOWNLOAD_FAILED) from error
        finally:
            if jar is not None:
                jar.clear()
            if len(self._attempt_diagnostics) < 16:
                self._attempt_diagnostics.append(diagnostics.to_safe_dict())


class PythonYtDlpFacade:
    def __init__(
        self,
        youtube_dl_factory: Callable[[dict[str, object]], object] | None = None,
    ) -> None:
        self._youtube_dl_factory = youtube_dl_factory
        self._last_diagnostics = DownloadAttemptDiagnostics()

    @property
    def last_diagnostics(self) -> dict[str, object]:
        return self._last_diagnostics.to_safe_dict()

    def download(
        self,
        candidate: ReelCandidate,
        cookie_jar: SessionCookieJar,
        temporary_path: Path,
        maximum_bytes: int,
    ) -> None:
        factory = self._youtube_dl_factory
        self._last_diagnostics = DownloadAttemptDiagnostics(stage="metadata_extraction")
        if factory is None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError as error:
                self._last_diagnostics.reason_code = (
                    RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED.value
                )
                raise CollectorRuntimeError(
                    RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED
                ) from error
            factory = YoutubeDL
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_directory = Path(
            tempfile.mkdtemp(prefix=".collector-yt-dlp-", dir=temporary_path.parent)
        )
        template = str(attempt_directory / "reel.%(ext)s")
        options = build_yt_dlp_options(template, maximum_bytes)
        ytdlp_cookie_jar = None
        ydl = None
        try:
            ytdlp_cookie_jar = cookie_jar.to_ytdlp_cookiejar()
            with factory(options) as ydl:
                ydl.cookiejar = ytdlp_cookie_jar
                self._last_diagnostics.stage = "media_download"
                ydl.extract_info(candidate.canonical_url, download=True)
            self._last_diagnostics.stage = "output_discovery"
            outputs = [
                path
                for path in attempt_directory.iterdir()
                if path.is_file() and path.suffix.lower() == ".mp4"
            ]
            self._last_diagnostics.output_file_count = len(outputs)
            if not outputs:
                raise CollectorRuntimeError(RuntimeReasonCode.DIRECT_DOWNLOAD_OUTPUT_MISSING)
            if len(outputs) != 1:
                raise CollectorRuntimeError(RuntimeReasonCode.DIRECT_DOWNLOAD_OUTPUT_AMBIGUOUS)
            os.replace(outputs[0], temporary_path)
        except CollectorRuntimeError as error:
            self._last_diagnostics.reason_code = error.code.value
            raise
        except Exception as error:
            if type(error).__name__ == "PostProcessingError" and type(error).__module__.startswith(
                _YTDLP_ERROR_MODULE
            ):
                self._last_diagnostics.stage = "merge"
            elif type(error).__name__ == "ExtractorError" and type(error).__module__.startswith(
                _YTDLP_ERROR_MODULE
            ):
                self._last_diagnostics.stage = "metadata_extraction"
            code = _classify_download_exception(error)
            self._last_diagnostics.reason_code = code.value
            raise CollectorRuntimeError(code) from error
        finally:
            # The yt-dlp-native CookieJar is attempt-local.  It is never
            # persisted or shared with a future Reel attempt.
            if ytdlp_cookie_jar is not None:
                try:
                    ytdlp_cookie_jar.clear()
                except Exception:
                    pass
            if ydl is not None:
                try:
                    ydl.cookiejar = None
                except Exception:
                    pass
            self._last_diagnostics.cleaned_partial_artifacts = _cleanup_attempt_directory(
                attempt_directory
            )


def _format_selector() -> str:
    return (
        "bestvideo[vcodec^=avc1][width>=720][height>=1280][width<=1080][height<=1920]"
        "+bestaudio[acodec^=mp4a]/"
        "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]/"
        "bestvideo[width<=1080][height<=1920]+bestaudio/"
        "best[vcodec!=none][acodec!=none]"
    )


def build_yt_dlp_options(output_template: str, maximum_bytes: int) -> dict[str, object]:
    """Return spike-proven bounded options without persistence or auth headers."""
    return {
        "noplaylist": True,
        "playlistend": 1,
        "format": _format_selector(),
        "merge_output_format": "mp4",
        "keepvideo": False,
        "outtmpl": output_template,
        "overwrites": False,
        "nopart": False,
        "continuedl": False,
        "max_filesize": maximum_bytes,
        "socket_timeout": SOCKET_TIMEOUT_SECONDS,
        "retries": MAX_RETRIES,
        "fragment_retries": MAX_RETRIES,
        "extractor_retries": MAX_RETRIES,
        "file_access_retries": MAX_RETRIES,
        "sleep_interval": 0.5,
        "max_sleep_interval": 0.5,
        "usenetrc": False,
        "quiet": True,
        "no_warnings": True,
        "verbose": False,
        "logger": _RedactingLogger(),
        "writethumbnail": False,
        "writeinfojson": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "getcomments": False,
        "cachedir": False,
    }


class _RedactingLogger:
    def debug(self, message: str) -> None:
        del message

    def warning(self, message: str) -> None:
        del message

    def error(self, message: str) -> None:
        del message


def _classify_download_exception(error: Exception) -> RuntimeReasonCode:
    """Map narrowly recognized downloader failures to stable, non-secret codes."""

    status = _safe_http_status(error)
    if status in {401, 407}:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED
    if status == 403:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_FORBIDDEN
    if status == 429:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_RATE_LIMITED
    if status in {408, 504}:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_TIMEOUT
    if isinstance(error, TimeoutError | socket.timeout):
        return RuntimeReasonCode.DIRECT_DOWNLOAD_TIMEOUT
    if isinstance(error, OSError) and error.errno in {
        errno.ENETUNREACH,
        errno.ECONNRESET,
        errno.ECONNREFUSED,
        errno.EHOSTUNREACH,
    }:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_NETWORK_FAILED
    module = type(error).__module__
    name = type(error).__name__
    if not module.startswith(_YTDLP_ERROR_MODULE):
        return RuntimeReasonCode.DOWNLOAD_FAILED
    if name in {"UnsupportedError", "NoFormatsError"}:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_FORMAT_UNAVAILABLE
    if name == "PostProcessingError":
        return RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED
    if name not in {"DownloadError", "ExtractorError", "PostProcessingError"}:
        return RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED
    message = str(error).lower()
    for code, markers in _SAFE_MESSAGE_MARKERS:
        if any(marker in message for marker in markers):
            return code
    return RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED


def _safe_http_status(error: Exception) -> int | None:
    """Read only numeric allowlisted status attributes; never retain response data."""

    for source in (error, getattr(error, "response", None)):
        if source is None:
            continue
        for attribute in ("status", "status_code", "code"):
            value = getattr(source, attribute, None)
            if isinstance(value, int) and 100 <= value <= 599:
                return value
    return None


def _diagnostics_from_safe_dict(
    source: dict[str, object], baseline: DownloadAttemptDiagnostics
) -> DownloadAttemptDiagnostics:
    result = DownloadAttemptDiagnostics(
        session_cookie_present=baseline.session_cookie_present,
        csrf_cookie_present=baseline.csrf_cookie_present,
        accepted_cookie_count=baseline.accepted_cookie_count,
    )
    for key, value in source.items():
        if key == "stage" and value in {
            "cookie_extraction",
            "metadata_extraction",
            "media_download",
            "merge",
            "output_discovery",
        }:
            result.stage = value
        elif key == "reason_code" and isinstance(value, str):
            result.reason_code = value
        elif key == "output_file_count" and isinstance(value, int) and value >= 0:
            result.output_file_count = value
        elif key == "cleaned_partial_artifacts" and isinstance(value, bool):
            result.cleaned_partial_artifacts = value
    return result


def _cleanup(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def _cleanup_attempt_files(temporary_path: Path) -> bool:
    """Remove the Collector-owned published temporary path if failure occurred."""

    return _cleanup(temporary_path)


def _cleanup_attempt_directory(path: Path) -> bool:
    """Best-effort cleanup that never replaces the primary download failure."""

    if not path.exists():
        return False
    try:
        shutil.rmtree(path)
    except Exception:
        return False
    return True
