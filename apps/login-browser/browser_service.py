"""One non-root, headed Chromium login session with an internal safe controller."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import signal
import socket
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import UUID

CONTROL_SECRET = os.environ["LOGIN_BROWSER_CONTROL_SECRET"]
ACCOUNT_ID = UUID(os.environ["LOGIN_ACCOUNT_ID"])
PROFILE_ROOT = Path("/login-profiles").resolve()
PROFILE = (PROFILE_ROOT / str(ACCOUNT_ID)).resolve()
if PROFILE_ROOT not in PROFILE.parents:
    raise SystemExit("unsafe profile path")


class BrowserRuntime:
    def __init__(self) -> None:
        self.stopping = threading.Event()
        self.processes: list[subprocess.Popen[bytes]] = []

    def start(self) -> None:
        PROFILE.mkdir(parents=True, exist_ok=True)
        # Docker named volumes may be created with a permissive root directory.
        # The account directory itself is the sensitive browser state and must
        # remain readable only by this non-root service account.
        PROFILE.chmod(0o700)
        # Chromium can leave these process locks behind after a container
        # signal.  This service owns the sole account profile, so remove only
        # the exact transient locks before spawning its next Chromium process.
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                (PROFILE / name).unlink()
            except FileNotFoundError:
                pass
        try:
            self.processes.append(
                subprocess.Popen(
                    ["Xvfb", ":99", "-screen", "0", "430x800x24", "-nolisten", "tcp"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            _wait_until(lambda: Path("/tmp/.X11-unix/X99").exists())
            self.processes.append(
                subprocess.Popen(
                    ["openbox", "--display", ":99"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            )
            chromium = subprocess.Popen(
                [
                    "chromium", "--display=:99", f"--user-data-dir={PROFILE}",
                    "--no-first-run", "--no-default-browser-check",
                    # Keep Chromium's supported non-setuid sandbox selection
                    # without ever using --no-sandbox.
                    "--disable-setuid-sandbox",
                    "--window-size=430,800", "--window-position=0,0",
                    # Keep the physical VNC canvas compact while giving
                    # mobile-web layouts enough CSS width for their controls.
                    "--force-device-scale-factor=0.9",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-debugging-port=9222", "--kiosk", "about:blank",
                    "--user-agent=Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(chromium)
            x11vnc = subprocess.Popen(
                ["x11vnc", "-display", ":99", "-localhost", "-nopw", "-forever", "-shared"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes.append(x11vnc)
            # websockify is reachable only by login-gateway over the private
            # Compose network. x11vnc and CDP themselves remain loopback-only.
            self.processes.append(
                subprocess.Popen(
                    ["websockify", "--web", "/usr/share/novnc", "0.0.0.0:6080", "127.0.0.1:5900"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        if self.stopping.is_set():
            return
        self.stopping.set()
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(self.processes):
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
        for path in (Path("/tmp/.X99-lock"), Path("/tmp/.X11-unix/X99")):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def readiness(self) -> str:
        if self.stopping.is_set() or not any(process.poll() is None for process in self.processes):
            return "preparing"
        try:
            pages = json.loads(urlopen("http://127.0.0.1:9222/json/list", timeout=1).read())
            page = next(item for item in pages if item.get("type") == "page")
            document = _cdp_call(page["webSocketDebuggerUrl"], "Runtime.evaluate", {
                "expression": "JSON.stringify({href:location.href,login:!!document.querySelector('input[name=username],input[name=password],form[action*=login]'),checkpoint:/checkpoint|challenge|two_factor|login/i.test(location.pathname),reel:!!document.querySelector('video,article[role=main],[role=main] video'),reelsPath:/^\\/reels(?:\\/|$)/.test(location.pathname)})",
                "returnByValue": True,
            })
            value = document["result"]["result"]["value"]
            state = json.loads(value)
            hostname = (urlparse(state["href"]).hostname or "").lower()
            if hostname != "instagram.com" and not hostname.endswith(".instagram.com"):
                return "login"
            if state["login"] or state["checkpoint"]:
                return "challenge" if state["checkpoint"] else "login"
            cookies = _cdp_call(page["webSocketDebuggerUrl"], "Network.getAllCookies", {})
            names = {cookie["name"] for cookie in cookies["result"]["cookies"]}
            if {"sessionid", "csrftoken"}.issubset(names):
                if state["reel"] or state["reelsPath"]:
                    return "connected"
                # The credentials were accepted, but the controller has not
                # yet verified the personal Reels boundary. The phone must
                # see a neutral progress screen rather than Instagram home.
                return "verifying"
            return "login"
        except Exception:
            return "preparing"

    def open_login(self) -> None:
        """Navigate only to Instagram's real login boundary after user action."""
        self._navigate("https://www.instagram.com/accounts/login/")

    def verify_profile(self) -> None:
        """Check a retained profile on the fixed personal Reels boundary."""
        self._navigate("https://www.instagram.com/reels/")

    def _navigate(self, url: str) -> None:
        pages = json.loads(urlopen("http://127.0.0.1:9222/json/list", timeout=1).read())
        page = next(item for item in pages if item.get("type") == "page")
        _cdp_call(
            page["webSocketDebuggerUrl"],
            "Page.navigate",
            {"url": url},
        )


def _cdp_call(url: str, method: str, params: dict[str, object]) -> dict[str, object]:
    parsed = urlparse(url)
    connection = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=2)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        connection.sendall((f"GET {parsed.path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        if b" 101 " not in connection.recv(4096):
            raise RuntimeError("CDP unavailable")
        payload = json.dumps({"id": 1, "method": method, "params": params}).encode()
        mask = os.urandom(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        header = bytes([0x81, 0x80 | len(payload)]) if len(payload) < 126 else bytes([0x81, 0x80 | 126]) + struct.pack("!H", len(payload))
        connection.sendall(header + mask + masked)
        while True:
            first, second = _read(connection, 2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack("!H", _read(connection, 2))[0]
            elif size == 127:
                size = struct.unpack("!Q", _read(connection, 8))[0]
            body = _read(connection, size)
            response = json.loads(body)
            if response.get("id") == 1:
                return response
    finally:
        connection.close()


def _read(connection: socket.socket, count: int) -> bytes:
    data = b""
    while len(data) < count:
        part = connection.recv(count - len(data))
        if not part:
            raise RuntimeError("CDP closed")
        data += part
    return data


def _wait_until(condition) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise RuntimeError("browser runtime did not become ready")


RUNTIME = BrowserRuntime()


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _allowed(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Login-Browser-Control", ""), CONTROL_SECRET)

    def _send(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if not self._allowed() or self.path not in {"/health", "/readiness"}:
            self._send(404)
            return
        if self.path == "/health":
            self._send(200, b'{"status":"ok"}')
            return
        self._send(200, json.dumps({"state": RUNTIME.readiness()}).encode())

    def do_POST(self) -> None:  # noqa: N802
        if not self._allowed() or self.path not in {"/shutdown", "/open-login", "/verify-profile"}:
            self._send(404)
            return
        if self.path in {"/open-login", "/verify-profile"}:
            try:
                if self.path == "/open-login":
                    RUNTIME.open_login()
                else:
                    RUNTIME.verify_profile()
            except Exception:
                self._send(503)
                return
            self._send(202)
            return
        self._send(202)
        threading.Thread(target=_shutdown, args=(self.server,), daemon=True).start()


def _shutdown(server: ThreadingHTTPServer) -> None:
    RUNTIME.stop()
    # BaseServer.shutdown() must run from a thread other than serve_forever.
    # It lets the main thread leave normally and execute its cleanup finally.
    server.shutdown()


def _handle_signal(_signum: int, _frame: object) -> None:
    RUNTIME.stop()
    raise SystemExit


def main() -> None:
    RUNTIME.start()
    server = ThreadingHTTPServer(("0.0.0.0", 8081), ControlHandler)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    try:
        server.serve_forever()
    finally:
        RUNTIME.stop()


if __name__ == "__main__":
    main()
