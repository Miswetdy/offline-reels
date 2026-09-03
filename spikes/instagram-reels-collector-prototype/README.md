# Instagram Reels local collector prototype

This is an isolated, local-only spike for collecting ten Reels into MP4 files.
It deliberately has no database, MinIO, API, Docker Compose, or import from
the production application.

## Why this differs from the current Collector

Instagram mobile Reels can retain `/reels/` (or the first Reel URL) while the
active video changes. This prototype therefore treats the visible, central
`<video>` media source as the transition identity. A transition is accepted
only after a different source is stable in two consecutive samples. Canonical
URL/shortcode discovery is not part of this local-file prototype.

Navigation uses a bounded cascade: CDP scroll gesture, CDP wheel, keyboard,
and the nearest real scroll container. Every action is followed by a bounded
wait for the new media fingerprint; no action is assumed to have worked.

## Setup

Use a private virtual environment outside version control and install the
matching Chromium once:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

`ffmpeg` and `ffprobe` must also be available on `PATH`; they validate and
normalize every saved file.

Provide credentials only for the process, never in a file:

```powershell
$env:INSTAGRAM_USERNAME = '<your Instagram username>'
$env:INSTAGRAM_PASSWORD = '<your Instagram password>'
python collect_reels.py --count 10
```

The persistent Chromium profile is `runtime/profile` and downloaded files are
written atomically to `output/`. Both are ignored by Git. Re-run without
credentials after a successful login to reuse that local profile.

If Instagram presents checkpoint, CAPTCHA, 2FA, or email confirmation, the
program exits with `AUTH_INTERACTION_REQUIRED`; complete that interaction in a
normal browser and then rerun. It does not attempt to bypass account security.

## Commands

```powershell
python -m pytest -q
python collect_reels.py --count 10 --headless false
```

If the pinned Playwright browser is unavailable but Chrome for Testing is
already provisioned on a server, pass its exact binary with
`--browser-executable <path-to-chrome>`. Do not point it at a profile owned by
another running browser.

`--headless false` is useful for an initial manual inspection. Logs contain
only sequence counts, durations, byte counts, and safe reason codes; they do
not contain credentials, cookies, URLs, shortcodes, or media fingerprints.
