"""Aggregate-only network diagnostic for the local authenticated Reels profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--browser-executable", type=Path, required=True)
    args = parser.parse_args()
    counts = {"video": 0, "json": 0, "other": 0}
    video_types: dict[str, int] = {}
    ranged_video = 0
    video_bytes = {"unknown": 0, "under_1mb": 0, "over_1mb": 0, "over_5mb": 0}
    json_keys = {"code": 0, "shortcode": 0, "video_url": 0, "video_versions": 0}
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(args.profile), executable_path=str(args.browser_executable), headless=False,
            viewport={"width": 430, "height": 800}, is_mobile=True, has_touch=True,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()

            def observe(response) -> None:
                nonlocal ranged_video
                content_type = response.headers.get("content-type", "").lower()
                if content_type.startswith("video/") or "application/vnd.apple.mpegurl" in content_type:
                    counts["video"] += 1
                    kind = content_type.split(";", 1)[0]
                    video_types[kind] = video_types.get(kind, 0) + 1
                    if "content-range" in response.headers:
                        ranged_video += 1
                    raw_length = response.headers.get("content-length")
                    if raw_length is None or not raw_length.isdigit():
                        video_bytes["unknown"] += 1
                    else:
                        length = int(raw_length)
                        if length > 5 * 1024 * 1024:
                            video_bytes["over_5mb"] += 1
                        elif length > 1024 * 1024:
                            video_bytes["over_1mb"] += 1
                        else:
                            video_bytes["under_1mb"] += 1
                elif "json" in content_type:
                    counts["json"] += 1
                    try:
                        payload = response.json()
                        stack = [payload]
                        while stack:
                            value = stack.pop()
                            if isinstance(value, dict):
                                for key, child in value.items():
                                    if key in json_keys:
                                        json_keys[key] += 1
                                    stack.append(child)
                            elif isinstance(value, list):
                                stack.extend(value)
                    except Exception:
                        pass
                else:
                    counts["other"] += 1

            page.on("response", observe)
            page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(10_000)
            print(json.dumps({**counts, "jsonKeys": json_keys, "rangedVideo": ranged_video, "videoBytes": video_bytes, "videoTypes": video_types}, sort_keys=True))
        finally:
            context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
