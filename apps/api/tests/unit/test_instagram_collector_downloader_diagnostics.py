"""Redacted session-first downloader failure classification regressions."""

import errno
import json
from pathlib import Path

import pytest

from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.downloader import (
    FreshSessionFirstYtDlpDownloader,
    PythonYtDlpFacade,
    SessionFirstYtDlpDownloader,
    _classify_download_exception,
)
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.operator import SafeEventTranscript, safe_summary_json
from app.instagram.collector.runtime.session_cookies import SessionCookieProvider
from app.instagram.collector.service import CollectorSummary


def _candidate() -> ReelCandidate:
    return ReelCandidate("SAFE_CODE", "https://www.instagram.com/reel/SAFE_CODE/")


class _CookieContext:
    def cookies(self) -> list[dict[str, object]]:
        return [
            {
                "name": "sessionid",
                "value": "session-secret-value",
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "expires": -1,
            },
            {
                "name": "csrftoken",
                "value": "csrf-secret-value",
                "domain": "www.instagram.com",
                "path": "/",
                "secure": True,
                "expires": -1,
            },
        ]


_YtDlpDownloadError = type("DownloadError", (Exception,), {"__module__": "yt_dlp.utils"})
_YtDlpExtractorError = type("ExtractorError", (Exception,), {"__module__": "yt_dlp.utils"})
_YtDlpNoFormatsError = type("NoFormatsError", (Exception,), {"__module__": "yt_dlp.utils"})


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            _YtDlpDownloadError("login required: Cookie: session-secret-value"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED,
        ),
        (
            _YtDlpDownloadError("HTTP Error 403: https://cdn.invalid/signed-token"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_FORBIDDEN,
        ),
        (
            _YtDlpDownloadError("HTTP Error 429: rate limit"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_RATE_LIMITED,
        ),
        (
            _YtDlpDownloadError("timed out while reading"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_TIMEOUT,
        ),
        (
            _YtDlpDownloadError("network is unreachable"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_NETWORK_FAILED,
        ),
        (
            _YtDlpNoFormatsError("no supported format"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_FORMAT_UNAVAILABLE,
        ),
        (
            _YtDlpDownloadError("file is larger than max-filesize"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_SIZE_LIMIT,
        ),
        (
            _YtDlpExtractorError("extractor details"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_EXTRACTOR_FAILED,
        ),
        (
            OSError(errno.ECONNREFUSED, "https://cdn.invalid/signed-token"),
            RuntimeReasonCode.DIRECT_DOWNLOAD_NETWORK_FAILED,
        ),
        (
            RuntimeError("Cookie: session-secret-value Authorization: Bearer hidden"),
            RuntimeReasonCode.DOWNLOAD_FAILED,
        ),
    ],
)
def test_failure_classifier_returns_only_safe_allowlisted_codes(error, expected) -> None:
    assert _classify_download_exception(error) is expected


def test_cookie_missing_has_distinct_safe_reason() -> None:
    class MissingContext:
        def cookies(self) -> list[dict[str, object]]:
            return []

    with pytest.raises(CollectorRuntimeError) as error:
        SessionCookieProvider().get(MissingContext())
    assert error.value.code is RuntimeReasonCode.SESSION_COOKIE_MISSING


def test_facade_distinguishes_missing_and_ambiguous_output(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(_CookieContext())

    class MissingYdl:
        cookiejar = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def extract_info(self, _url: str, *, download: bool) -> None:
            assert download is True

    facade = PythonYtDlpFacade(lambda _options: MissingYdl())
    with pytest.raises(CollectorRuntimeError) as error:
        facade.download(_candidate(), jar, output, 1024)
    assert error.value.code is RuntimeReasonCode.DIRECT_DOWNLOAD_OUTPUT_MISSING
    assert facade.last_diagnostics["output_file_count"] == 0

    class AmbiguousYdl(MissingYdl):
        def __init__(self, options) -> None:
            self._template = options["outtmpl"]

        def extract_info(self, _url: str, *, download: bool) -> None:
            Path(str(self._template).replace("%(ext)s", "mp4")).write_bytes(b"one")
            (Path(self._template).parent / "second.mp4").write_bytes(b"two")

    jar = SessionCookieProvider().get(_CookieContext())
    facade = PythonYtDlpFacade(lambda options: AmbiguousYdl(options))
    with pytest.raises(CollectorRuntimeError) as error:
        facade.download(_candidate(), jar, output, 1024)
    assert error.value.code is RuntimeReasonCode.DIRECT_DOWNLOAD_OUTPUT_AMBIGUOUS
    assert facade.last_diagnostics["output_file_count"] == 2
    assert facade.last_diagnostics["cleaned_partial_artifacts"] is True


def test_fresh_downloader_reports_safe_attempt_diagnostics_and_cleans_files(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"

    class FailingFacade:
        def download(self, _candidate, _jar, path: Path, _maximum: int) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("partial", encoding="utf-8")
            (path.parent / ".SAFE_CODE.collector.mp4.part").write_text("partial", encoding="utf-8")
            raise _YtDlpDownloadError(
                "HTTP Error 401 Cookie: session-secret-value https://cdn.invalid/signed-token"
            )

    downloader = FreshSessionFirstYtDlpDownloader(
        _CookieContext,
        maximum_bytes=1024,
        facade_factory=FailingFacade,
    )
    with pytest.raises(CollectorRuntimeError) as error:
        downloader.download(_candidate(), output)
    assert error.value.code is RuntimeReasonCode.DIRECT_DOWNLOAD_AUTH_REQUIRED
    assert not output.exists()
    diagnostics = downloader.attempt_diagnostics
    assert diagnostics == [
        {
            "session_cookie_present": True,
            "csrf_cookie_present": True,
            "accepted_cookie_count": 2,
            "stage": "metadata_extraction",
            "reason_code": "DIRECT_DOWNLOAD_AUTH_REQUIRED",
            "output_file_count": 0,
            "cleaned_partial_artifacts": True,
        }
    ]
    transcript = SafeEventTranscript()
    transcript.download_diagnostics = diagnostics
    summary = CollectorSummary(None, "failed", 3, 0, 0, 1, 0, "DIRECT_DOWNLOAD_AUTH_REQUIRED")
    payload = safe_summary_json(summary, transcript, None)
    assert json.loads(payload)["stop_reason_code"] == "DIRECT_DOWNLOAD_AUTH_REQUIRED"
    for secret in ("session-secret-value", "csrf-secret-value", "cdn.invalid", "Authorization"):
        assert secret not in payload
        assert secret not in repr(downloader)


def test_size_limit_cleans_temporary_and_cookie_jar(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"

    class OversizeFacade:
        def download(self, _candidate, _jar, path: Path, _maximum: int) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * 8)

    jar = SessionCookieProvider().get(_CookieContext())
    downloader = SessionFirstYtDlpDownloader(jar, maximum_bytes=4, facade=OversizeFacade())
    with pytest.raises(CollectorRuntimeError) as error:
        downloader.download(_candidate(), output)
    assert error.value.code is RuntimeReasonCode.DIRECT_DOWNLOAD_SIZE_LIMIT
    assert not output.exists()
    assert list(jar.to_ytdlp_cookiejar()) == []
