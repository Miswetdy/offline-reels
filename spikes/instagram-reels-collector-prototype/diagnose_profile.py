"""Safe local diagnostic for a manually authenticated Instagram profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

REELS_URL = "https://www.instagram.com/reels/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path, required=True)
    parser.add_argument("--headless", choices=("true", "false"), default="false")
    args = parser.parse_args()
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(args.profile),
                executable_path=str(args.browser_executable),
                headless=args.headless == "true",
                viewport={"width": 430, "height": 800},
                is_mobile=True,
                has_touch=True,
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
                ),
            )
            try:
                context.set_default_navigation_timeout(30_000)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(REELS_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(8_000)
                payload = page.evaluate(
                    """() => {
                      const videos = [...document.querySelectorAll('video')];
                      return {
                      hasSession: document.cookie.includes('sessionid='),
                      videoCount: videos.length,
                      visibleVideoCount: videos.filter((v) => {
                        const r = v.getBoundingClientRect(); return r.width > 0 && r.height > 0;
                      }).length,
                      currentSourceCount: videos.filter((v) => v.currentSrc.startsWith('https://')).length,
                      declaredSourceCount: videos.filter((v) => v.src.startsWith('https://') || v.querySelector('source[src]')).length,
                      readyVideoCount: videos.filter((v) => v.readyState >= 2).length,
                      loginForm: Boolean(document.querySelector('input[name="username"], input[name="password"]')),
                      checkpointPath: /checkpoint|challenge|two_factor/.test(location.pathname),
                      reelsPath: /^\\/reels?\\//.test(location.pathname),
                    }}"""
                )
                cookies = context.cookies([REELS_URL])
                payload["sessionCookiePresent"] = any(
                    cookie.get("name") == "sessionid" for cookie in cookies
                )
                print(json.dumps(payload, sort_keys=True))
            finally:
                context.close()
    except Error:
        print(json.dumps({"reason_code": "BROWSER_UNAVAILABLE"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
