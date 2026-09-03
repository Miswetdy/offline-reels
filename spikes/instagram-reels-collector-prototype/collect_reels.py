"""Authenticated local-only Instagram Reels collector prototype.

No URL, cookie, DOM text, credential, shortcode, or media fingerprint is ever
logged. The active media source is retained only in memory long enough to
download the video and confirm a transition.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from normalizer import NormalizationError, normalize_to_mp4

REELS_URL = "https://www.instagram.com/reels/"
LOGIN_URL = "https://www.instagram.com/accounts/login/"
VIEWPORT = {"width": 430, "height": 800}
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)
MAX_MEDIA_BYTES = 350 * 1024 * 1024

ACTIVE_VIDEO_PROBE = """() => {
  const width = innerWidth, height = innerHeight;
  const centreX = width / 2, centreY = height / 2;
  const candidates = [...document.querySelectorAll('video')].map((video) => {
    const r = video.getBoundingClientRect();
    const visibleWidth = Math.max(0, Math.min(r.right, width) - Math.max(r.left, 0));
    const visibleHeight = Math.max(0, Math.min(r.bottom, height) - Math.max(r.top, 0));
    const area = visibleWidth * visibleHeight;
    const centreDistance = Math.hypot((r.left + r.right) / 2 - centreX, (r.top + r.bottom) / 2 - centreY);
    return { video, area, centreDistance, visibleWidth, visibleHeight };
  }).filter((item) => item.area > 0);
  candidates.sort((a, b) => b.area - a.area || a.centreDistance - b.centreDistance);
  if (!candidates.length) return null;
  const selected = candidates[0];
  // Headless Chromium may defer network loading until playback is requested.
  // Muting preserves autoplay policy and is unrelated to the downloaded file.
  selected.video.muted = true;
  selected.video.play().catch(() => {});
  const declared = selected.video.getAttribute('src') || selected.video.querySelector('source[src]')?.src || '';
  return {
    source: selected.video.currentSrc || declared,
    identity: (() => {
      const ids = window.__offlineReelsPrototypeVideoIds || (window.__offlineReelsPrototypeVideoIds = new WeakMap());
      const next = window.__offlineReelsPrototypeVideoIdNext || 1;
      if (!ids.has(selected.video)) {
        ids.set(selected.video, next);
        window.__offlineReelsPrototypeVideoIdNext = next + 1;
      }
      return `${ids.get(selected.video)}:${selected.video.duration || 0}:${selected.video.videoWidth}x${selected.video.videoHeight}`;
    })(),
    duration: Number.isFinite(selected.video.duration) ? selected.video.duration : null,
    ready: selected.video.readyState,
    visibleArea: selected.area,
    viewportArea: width * height,
    width: selected.video.videoWidth,
    height: selected.video.videoHeight,
  };
}"""

SCROLL_CONTAINER_PROBE = """() => {
  const videos = [...document.querySelectorAll('video')];
  if (!videos.length) return false;
  let chosen = videos.sort((a, b) => {
    const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
    return Math.abs((ar.top + ar.bottom) / 2 - innerHeight / 2) - Math.abs((br.top + br.bottom) / 2 - innerHeight / 2);
  })[0];
  for (let node = chosen.parentElement; node && node !== document.documentElement; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
      node.scrollBy({top: Math.round(innerHeight * 0.92), behavior: 'instant'});
      return true;
    }
  }
  window.scrollBy({top: Math.round(innerHeight * 0.92), behavior: 'instant'});
  return true;
}"""


class CollectorError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActiveVideo:
    identity: str
    fingerprint: str
    duration: float | None


class ReelCatalog:
    """Canonical Reel codes extracted only from authenticated feed JSON."""

    def __init__(self, page: Any) -> None:
        self._codes: list[str] = []
        self._used: set[str] = set()
        page.on("response", self._observe)

    def _observe(self, response: Any) -> None:
        try:
            if "json" not in response.headers.get("content-type", "").lower():
                return
            stack = [response.json()]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    code = value.get("code")
                    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_-]{5,64}", code):
                        if code not in self._codes:
                            self._codes.append(code)
                    stack.extend(value.values())
                elif isinstance(value, list):
                    stack.extend(value)
        except Exception:
            return

    def wait_for_unused(self, page: Any, *, timeout_seconds: float) -> str:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for code in self._codes:
                if code not in self._used:
                    self._used.add(code)
                    return code
            page.wait_for_timeout(250)
        raise CollectorError("REEL_ID_NOT_FOUND")


def _safe_code(error: BaseException) -> str:
    return str(error) if str(error).isupper() and len(str(error)) < 80 else "UNEXPECTED_ERROR"


def _active_video(page: Any) -> ActiveVideo | None:
    payload = page.evaluate(ACTIVE_VIDEO_PROBE)
    if not isinstance(payload, dict) or not isinstance(payload.get("identity"), str):
        return None
    if not isinstance(payload.get("ready"), int) or payload["ready"] < 2:
        return None
    identity = payload["identity"]
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    duration = payload.get("duration")
    return ActiveVideo(identity, fingerprint, duration if isinstance(duration, int | float) else None)


def _wait_for_active(page: Any, *, timeout_seconds: float) -> ActiveVideo:
    deadline = time.monotonic() + timeout_seconds
    stable: ActiveVideo | None = None
    while time.monotonic() < deadline:
        candidate = _active_video(page)
        if candidate is not None and candidate.fingerprint == getattr(stable, "fingerprint", None):
            return candidate
        stable = candidate
        page.wait_for_timeout(250)
    raise CollectorError("ACTIVE_VIDEO_NOT_FOUND")


def _wait_for_transition(page: Any, previous: ActiveVideo, *, timeout_seconds: float) -> ActiveVideo | None:
    deadline = time.monotonic() + timeout_seconds
    stable: ActiveVideo | None = None
    while time.monotonic() < deadline:
        candidate = _active_video(page)
        if candidate is not None and candidate.fingerprint != previous.fingerprint:
            if candidate.fingerprint == getattr(stable, "fingerprint", None):
                return candidate
            stable = candidate
        else:
            stable = None
        page.wait_for_timeout(250)
    return None


def _advance(page: Any, _context: Any, previous: ActiveVideo) -> ActiveVideo | None:
    """Try bounded, interruptible browser inputs and confirm every result.

    CDP ``synthesizeScrollGesture`` is deliberately excluded: Chrome may leave
    that command pending indefinitely, which defeats a Collector deadline.
    """
    # This is the primary action. It moves the actual scroll owner selected
    # from the active video rather than depending on a global page URL.
    page.evaluate(SCROLL_CONTAINER_PROBE)
    transitioned = _wait_for_transition(page, previous, timeout_seconds=5)
    if transitioned:
        return transitioned
    for key in ("ArrowDown", "PageDown"):
        page.keyboard.press(key)
        transitioned = _wait_for_transition(page, previous, timeout_seconds=4)
        if transitioned:
            return transitioned
    page.mouse.move(VIEWPORT["width"] / 2, VIEWPORT["height"] / 2)
    page.mouse.wheel(0, int(VIEWPORT["height"] * 0.9))
    return _wait_for_transition(page, previous, timeout_seconds=5)


def _check_auth_state(page: Any, *, allow_login_form: bool = False) -> None:
    path = page.url.lower()
    if any(token in path for token in ("challenge", "checkpoint", "two_factor")):
        raise CollectorError("AUTH_INTERACTION_REQUIRED")
    if not allow_login_form and page.locator('input[name="username"], input[name="password"]').count() > 0:
        raise CollectorError("AUTH_REQUIRED")


def _has_authenticated_session(page: Any) -> bool:
    """Read only the presence of the session cookie; never retain its value."""

    return any(cookie.get("name") == "sessionid" for cookie in page.context.cookies([REELS_URL]))


def _wait_for_session(page: Any, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        _check_auth_state(page, allow_login_form=True)
        if _has_authenticated_session(page):
            return True
        page.wait_for_timeout(500)
    return False


def _login_if_needed(page: Any, username: str | None, password: str | None) -> None:
    # Reels can be viewed while logged out, so credentials explicitly request
    # an account login instead of treating a public Reels response as proof of
    # authentication.
    if username and password:
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        _check_auth_state(page, allow_login_form=True)
        username_field = page.locator('input[name="username"]')
        try:
            username_field.wait_for(state="visible", timeout=15_000)
        except Exception:
            # An existing session can redirect straight away; otherwise this
            # is an unusable login presentation, never evidence of login.
            if not _has_authenticated_session(page):
                raise CollectorError("AUTH_LOGIN_FAILED") from None
        else:
            username_field.fill(username)
            page.locator('input[name="password"]').fill(password)
            page.locator('button[type="submit"]').first.click()
        if not _wait_for_session(page, timeout_seconds=20):
            if page.locator('input[name="username"], input[name="password"]').count() > 0:
                raise CollectorError("AUTH_LOGIN_REJECTED")
            raise CollectorError("AUTH_INTERACTION_REQUIRED")
    page.goto(REELS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    _check_auth_state(page)
    username_field = page.locator('input[name="username"]')
    if username_field.count() == 0:
        return
    raise CollectorError("AUTH_REQUIRED")


def _download(context: Any, code: str, temporary: Path) -> int:
    """Run one bounded yt-dlp attempt with an attempt-local cookie file."""

    cookies: list[tuple[str, str, str, str, int]] = []
    for raw in context.cookies():
        name, value, domain, path = (raw.get(key) for key in ("name", "value", "domain", "path"))
        if not all(isinstance(item, str) and item for item in (name, value, domain, path)):
            continue
        if name not in {"sessionid", "csrftoken"} or not domain.lstrip(".").endswith("instagram.com"):
            continue
        expires = raw.get("expires")
        expires_at = int(expires) if isinstance(expires, int | float) and expires > 0 else 0
        cookies.append((domain, path, name, value, expires_at))
    if not any(name == "sessionid" for _, _, name, _, _ in cookies):
        raise CollectorError("AUTH_REQUIRED")
    attempt = Path(tempfile.mkdtemp(prefix=".reel-download-", dir=temporary.parent))
    try:
        cookie_file = attempt / "cookies.txt"
        cookie_file.write_text(
            "# Netscape HTTP Cookie File\n"
            + "".join(
                f"{domain}\t{'TRUE' if domain.startswith('.') else 'FALSE'}\t{path}\tTRUE\t{expires}\t{name}\t{value}\n"
                for domain, path, name, value, expires in cookies
            ),
            encoding="utf-8",
        )
        command = [
            sys.executable, "-m", "yt_dlp", "--quiet", "--no-warnings", "--no-progress",
            "--no-playlist", "--format", "best[ext=mp4]/best", "--socket-timeout", "30",
            "--retries", "2", "--cookies", str(cookie_file), "--output", str(attempt / "reel.%(ext)s"),
            f"https://www.instagram.com/reel/{code}/",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            raise CollectorError("MEDIA_DOWNLOAD_FAILED")
        files = [path for path in attempt.iterdir() if path.is_file() and path.name != "cookies.txt"]
        if len(files) != 1 or files[0].stat().st_size == 0 or files[0].stat().st_size > MAX_MEDIA_BYTES:
            raise CollectorError("MEDIA_DOWNLOAD_FAILED")
        os.replace(files[0], temporary)
        return temporary.stat().st_size
    except CollectorError:
        raise
    except subprocess.TimeoutExpired as error:
        raise CollectorError("MEDIA_DOWNLOAD_TIMEOUT") from error
    except Exception as error:
        raise CollectorError("MEDIA_DOWNLOAD_FAILED") from error
    finally:
        shutil.rmtree(attempt, ignore_errors=True)


def collect(
    *,
    count: int,
    profile: Path,
    output: Path,
    headless: bool,
    username: str | None,
    password: str | None,
    browser_executable: Path | None,
) -> int:
    from playwright.sync_api import Error, sync_playwright

    profile.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise CollectorError("OUTPUT_DIRECTORY_NOT_EMPTY")
    completed = 0
    with sync_playwright() as playwright:
        phase = "BROWSER"
        options: dict[str, object] = {
            "headless": headless,
            "viewport": VIEWPORT,
            "is_mobile": True,
            "has_touch": True,
            "user_agent": MOBILE_UA,
        }
        if browser_executable is not None:
            if not browser_executable.is_file():
                raise CollectorError("BROWSER_UNAVAILABLE")
            options["executable_path"] = str(browser_executable)
        try:
            context = playwright.chromium.launch_persistent_context(str(profile), **options)
        except Error as error:
            raise CollectorError("BROWSER_UNAVAILABLE") from error
        try:
            context.set_default_timeout(15_000)
            context.set_default_navigation_timeout(30_000)
            page = context.pages[0] if context.pages else context.new_page()
            catalog = ReelCatalog(page)
            phase = "LOGIN"
            _login_if_needed(page, username, password)
            phase = "ACTIVE_VIDEO"
            current = _wait_for_active(page, timeout_seconds=30)
            while completed < count:
                temporary = output / f".reel-{completed + 1:02d}.download"
                destination = output / f"reel-{completed + 1:02d}.mp4"
                normalized = False
                try:
                    code = catalog.wait_for_unused(page, timeout_seconds=30)
                    phase = "DOWNLOAD"
                    bytes_written = _download(context, code, temporary)
                    phase = "NORMALIZATION"
                    normalize_to_mp4(temporary, destination)
                    normalized = True
                finally:
                    if normalized:
                        temporary.unlink(missing_ok=True)
                    elif temporary.is_file():
                        os.replace(temporary, output / f".failed-reel-{completed + 1:02d}.mp4")
                completed += 1
                duration = round(current.duration, 1) if current.duration is not None else None
                print({"event": "saved", "completed": completed, "bytes": bytes_written, "duration_seconds": duration}, flush=True)
                if completed == count:
                    break
                phase = "TRANSITION"
                next_video = _advance(page, context, current)
                if next_video is None:
                    raise CollectorError("TRANSITION_FAILED")
                current = next_video
                print({"event": "transition_confirmed", "completed": completed}, flush=True)
        except CollectorError:
            raise
        except Exception as error:
            raise CollectorError(f"{phase}_FAILED") from error
        finally:
            context.close()
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--profile", type=Path, default=Path("runtime/profile"))
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--headless", choices=("true", "false"), default="true")
    parser.add_argument(
        "--browser-executable",
        type=Path,
        default=Path(os.environ["PLAYWRIGHT_BROWSER_EXECUTABLE"])
        if "PLAYWRIGHT_BROWSER_EXECUTABLE" in os.environ
        else None,
    )
    args = parser.parse_args(argv)
    if not 1 <= args.count <= 10:
        parser.error("--count must be between 1 and 10")
    try:
        completed = collect(
            count=args.count, profile=args.profile, output=args.output,
            headless=args.headless == "true", username=os.environ.get("INSTAGRAM_USERNAME"),
            password=os.environ.get("INSTAGRAM_PASSWORD"), browser_executable=args.browser_executable,
        )
    except (CollectorError, NormalizationError) as error:
        print({"event": "failed", "completed": 0, "reason_code": _safe_code(error)}, file=sys.stderr)
        return 2
    except Exception as error:
        # Playwright, network and external-process exceptions can contain
        # unsafe request data. Never render their message.
        print(
            {
                "event": "failed",
                "completed": 0,
                "reason_code": "UNEXPECTED_ERROR",
                "exception_type": type(error).__name__,
            },
            file=sys.stderr,
        )
        return 2
    print({"event": "complete", "completed": completed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
