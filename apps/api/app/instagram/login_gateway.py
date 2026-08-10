"""Standalone HTTPS-only gateway for a one-time mobile remote-login link.

This module is intentionally not imported by ``app.main``.  It is started only
by the isolated Stage 4 Compose project, so normal FastAPI startup has no
remote-browser dependency or attack surface.
"""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import hashlib
import hmac
from html import escape
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from websockets.asyncio.client import connect as connect_websocket

from app.db.session import create_session_factory
from app.instagram.contracts import LoginSessionStatus
from app.instagram.login_sessions import LoginSessionError, LoginSessionService


class LoginGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    database_url: str = Field(validation_alias="DATABASE_URL")
    gateway_origin: AnyHttpUrl = Field(validation_alias="LOGIN_GATEWAY_ORIGIN")
    session_secret: str = Field(min_length=32, validation_alias="LOGIN_GATEWAY_SESSION_SECRET")
    browser_control_secret: str = Field(
        min_length=32, validation_alias="LOGIN_BROWSER_CONTROL_SECRET"
    )
    browser_control_url: AnyHttpUrl = Field(
        default="http://login-browser:8081", validation_alias="LOGIN_BROWSER_CONTROL_URL"
    )
    browser_vnc_url: AnyHttpUrl = Field(
        default="http://login-browser:6080", validation_alias="LOGIN_BROWSER_VNC_URL"
    )

    @field_validator("gateway_origin")
    @classmethod
    def gateway_must_use_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("LOGIN_GATEWAY_ORIGIN must use HTTPS")
        return value

    @property
    def origin(self) -> str:
        return str(self.gateway_origin).rstrip("/")

    @property
    def host(self) -> str:
        return self.origin.removeprefix("https://").removeprefix("http://")


class BrowserController:
    """Safe internal control plane: it never returns CDP, cookie, or VNC data."""

    def __init__(self, settings: LoginGatewaySettings) -> None:
        self._settings = settings

    async def readiness(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(
                    f"{str(self._settings.browser_control_url).rstrip('/')}/readiness",
                    headers={"X-Login-Browser-Control": self._settings.browser_control_secret},
                )
                response.raise_for_status()
                state = response.json().get("state")
                return (
                    state
                    if state in {"preparing", "login", "challenge", "verifying", "connected"}
                    else "preparing"
                )
        except (httpx.HTTPError, ValueError):
            return "preparing"

    async def close(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{str(self._settings.browser_control_url).rstrip('/')}/shutdown",
                    headers={"X-Login-Browser-Control": self._settings.browser_control_secret},
                )
        except httpx.HTTPError:
            # The durable state is already completed; a supervisor may clean
            # up the browser process. Never surface infrastructure detail.
            return

    async def open_login(self) -> bool:
        return await self._navigate("open-login")

    async def verify_profile(self) -> bool:
        return await self._navigate("verify-profile")

    async def _navigate(self, action: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{str(self._settings.browser_control_url).rstrip('/')}/{action}",
                    headers={"X-Login-Browser-Control": self._settings.browser_control_secret},
                )
                return response.status_code == 202
        except httpx.HTTPError:
            return False


def create_login_gateway(
    settings: LoginGatewaySettings | None = None,
    browser: BrowserController | None = None,
) -> FastAPI:
    settings = settings or LoginGatewaySettings()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.session_factory = create_session_factory(settings)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    app.state.browser = browser or BrowserController(settings)

    @app.get("/connect/{session_id}", response_class=HTMLResponse)
    async def connect(session_id: UUID, request: Request) -> HTMLResponse:
        _require_host(request, settings)
        if app.state.login_sessions.status(session_id) is LoginSessionStatus.PENDING:
            return _connection_start_page(session_id)
        return _unavailable_page("Reconnect is required.")

    @app.post("/connect/{session_id}/activate")
    async def activate(session_id: UUID, request: Request) -> Response:
        _require_host(request, settings)
        _require_origin(request, settings)
        try:
            body = await request.json()
            launch_token = body.get("launch_token") if isinstance(body, dict) else None
            if not isinstance(launch_token, str) or not launch_token:
                raise LoginSessionError("Login link is unavailable.")
            app.state.login_sessions.activate(session_id, launch_token)
        except LoginSessionError:
            raise HTTPException(status_code=409) from None
        except ValueError:
            raise HTTPException(status_code=400) from None
        response = Response(status_code=204, headers=_security_headers())
        response.set_cookie(
            "login_gateway_session",
            _sign_session(session_id, settings),
            httponly=True,
            secure=True,
            samesite="strict",
            path=f"/remote/{session_id}",
            max_age=15 * 60,
        )
        return response

    @app.get("/remote/{session_id}", response_class=HTMLResponse)
    async def remote(session_id: UUID, request: Request) -> HTMLResponse:
        _require_host(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE:
            return _unavailable_page("Reconnect is required.")
        if app.state.login_sessions.is_profile_check(session_id):
            return _profile_verification_page(session_id)
        return _full_bleed_remote_viewer_page(session_id)

    @app.get("/remote/{session_id}/interactive", response_class=HTMLResponse)
    async def interactive_login(session_id: UUID, request: Request) -> HTMLResponse:
        _require_host(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE:
            return _unavailable_page("Reconnect is required.")
        return _full_bleed_remote_viewer_page(session_id)

    @app.get("/remote/{session_id}/layout-preview", response_class=HTMLResponse)
    async def layout_preview(session_id: UUID, request: Request) -> HTMLResponse:
        """Signed, non-Instagram visual check before changing the transport shell."""
        _require_host(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE:
            return _unavailable_page("Reconnect is required.")
        return _layout_preview_page(session_id)

    @app.post("/remote/{session_id}/open-login")
    async def open_login(session_id: UUID, request: Request) -> Response:
        _require_host(request, settings)
        _require_origin(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE:
            raise HTTPException(status_code=409)
        if not await app.state.browser.open_login():
            raise HTTPException(status_code=503)
        return Response(status_code=202, headers=_security_headers())

    @app.post("/remote/{session_id}/verify-profile")
    async def verify_profile(session_id: UUID, request: Request) -> Response:
        _require_host(request, settings)
        _require_origin(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if (
            app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE
            or not app.state.login_sessions.is_profile_check(session_id)
        ):
            raise HTTPException(status_code=409)
        if not await app.state.browser.verify_profile():
            raise HTTPException(status_code=503)
        return Response(status_code=202, headers=_security_headers())

    @app.get("/remote/{session_id}/state")
    async def state(session_id: UUID, request: Request) -> Response:
        _require_host(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        durable_status = app.state.login_sessions.status(session_id)
        if durable_status is None:
            raise HTTPException(status_code=404)
        if durable_status is LoginSessionStatus.ACTIVE:
            browser_state = await app.state.browser.readiness()
            if browser_state == "verifying":
                await app.state.browser.verify_profile()
            elif browser_state == "connected":
                durable_status = app.state.login_sessions.complete(session_id)
                await app.state.browser.close()
        return Response(
            content=_state_json(
                durable_status,
                browser_state if durable_status is LoginSessionStatus.ACTIVE else None,
            ),
            media_type="application/json",
            headers=_security_headers(),
        )

    @app.get("/remote/{session_id}/vnc/{asset_path:path}")
    async def vnc_asset(session_id: UUID, asset_path: str, request: Request) -> Response:
        _require_host(request, settings)
        _require_session(request.cookies.get("login_gateway_session"), session_id, settings)
        if app.state.login_sessions.status(
            session_id
        ) is not LoginSessionStatus.ACTIVE or not _safe_asset(asset_path):
            raise HTTPException(status_code=404)
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.get(f"{str(settings.browser_vnc_url).rstrip('/')}/{asset_path}")
        if upstream.status_code != 200:
            raise HTTPException(status_code=404)
        headers = _security_headers(frame_ancestors="'self'")
        headers["Content-Type"] = upstream.headers.get("content-type", "application/octet-stream")
        return Response(upstream.content, headers=headers)

    @app.websocket("/remote/{session_id}/websockify")
    async def websockify(session_id: UUID, websocket: WebSocket) -> None:
        if not _websocket_allowed(websocket, session_id, settings):
            await websocket.close(code=4403)
            return
        if app.state.login_sessions.status(session_id) is not LoginSessionStatus.ACTIVE:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        upstream_url = (
            str(settings.browser_vnc_url).replace("http://", "ws://").replace("https://", "wss://")
            + "/websockify"
        )
        try:
            async with connect_websocket(upstream_url, origin=settings.origin) as upstream:
                await _relay(websocket, upstream)
        except (OSError, WebSocketDisconnect):
            await websocket.close(code=1011)

    return app


async def _relay(client: WebSocket, upstream) -> None:
    async def receive_client() -> None:
        while True:
            message = await client.receive()
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                await upstream.send(data)
            elif message.get("text") is not None:
                await upstream.send(message["text"])

    async def receive_upstream() -> None:
        async for data in upstream:
            if isinstance(data, bytes):
                await client.send_bytes(data)
            else:
                await client.send_text(data)

    tasks = [asyncio.create_task(receive_client()), asyncio.create_task(receive_upstream())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()


def _require_host(request: Request, settings: LoginGatewaySettings) -> None:
    if request.headers.get("host", "").lower() != settings.host.lower():
        raise HTTPException(status_code=400)


def _require_session(value: str | None, session_id: UUID, settings: LoginGatewaySettings) -> None:
    if not _valid_cookie(value, session_id, settings):
        raise HTTPException(status_code=403)


def _require_origin(request: Request, settings: LoginGatewaySettings) -> None:
    if request.headers.get("origin", "").rstrip("/") != settings.origin:
        raise HTTPException(status_code=403)


def _websocket_allowed(
    websocket: WebSocket, session_id: UUID, settings: LoginGatewaySettings
) -> bool:
    return (
        websocket.headers.get("host", "").lower() == settings.host.lower()
        and websocket.headers.get("origin", "").rstrip("/") == settings.origin
        and _valid_cookie(websocket.cookies.get("login_gateway_session"), session_id, settings)
    )


def _sign_session(session_id: UUID, settings: LoginGatewaySettings) -> str:
    message = str(session_id).encode("ascii")
    signature = hmac.new(
        settings.session_secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    return f"{session_id}.{signature}"


def _valid_cookie(value: str | None, session_id: UUID, settings: LoginGatewaySettings) -> bool:
    return value is not None and hmac.compare_digest(value, _sign_session(session_id, settings))


def _safe_asset(path: str) -> bool:
    return bool(path) and ".." not in path and "\\" not in path and not path.startswith("/")


def _security_headers(frame_ancestors: str = "'none'") -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY" if frame_ancestors == "'none'" else "SAMEORIGIN",
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {frame_ancestors}; object-src 'none'; "
            "connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'"
        ),
    }


def _layout_preview_page(session_id: UUID) -> HTMLResponse:
    """Static, credential-free reference screen for phone viewport acceptance."""
    sid = escape(str(session_id))
    html = f"""<!doctype html>
<html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>Проверка экрана</title>
<style>
html,body,main{{width:100%;height:100%;margin:0;overflow:hidden;background:#162033;color:#162033;font:16px system-ui}}
main{{position:relative}}#canvas{{position:absolute;inset:0;box-sizing:border-box;background:#fff}}
#canvas::before,#canvas::after{{content:'';position:absolute;top:0;bottom:0;width:1px;background:#334155}}#canvas::before{{left:0}}#canvas::after{{right:0}}
section{{box-sizing:border-box;min-height:100%;padding:calc(86px + env(safe-area-inset-top)) 24px calc(96px + env(safe-area-inset-bottom));display:grid;place-content:center;text-align:center}}
.card{{max-width:19rem}}h1{{margin:0 0 12px;font-size:1.35rem}}p{{margin:0;color:#334155;line-height:1.45}}
header,footer{{box-sizing:border-box;position:absolute;z-index:2;left:0;right:0;background:#162033;color:#fff}}header{{top:0;padding:calc(10px + env(safe-area-inset-top)) 16px 10px;font-weight:700}}footer{{bottom:0;padding:10px 16px calc(10px + env(safe-area-inset-bottom))}}a{{display:inline-flex;min-height:44px;align-items:center;border-radius:10px;padding:0 14px;background:#334155;color:#fff;font-weight:700;text-decoration:none}}
</style>
<main data-layout-preview><div id="canvas"><section><div class="card"><h1>Проверка границ экрана</h1><p>Белая область должна точно доходить до левого и правого края без чёрных полос и обрезания.</p></div></section></div><header>Проверка мобильного экрана</header><footer><a href="/remote/{sid}">Вернуться к браузеру</a></footer></main></html>"""
    return HTMLResponse(html, headers=_security_headers())


def _profile_verification_page(session_id: UUID) -> HTMLResponse:
    """NoVNC-free result screen for an already connected persistent profile."""
    sid = escape(str(session_id))
    html = f"""<!doctype html>
<html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Проверка Instagram</title>
<style>
html,body{{width:100%;height:100%;margin:0;background:#162033;color:#fff;font:17px system-ui}}
main{{box-sizing:border-box;min-height:100%;padding:calc(32px + env(safe-area-inset-top)) 24px calc(32px + env(safe-area-inset-bottom));display:grid;place-items:center;text-align:center}}
section{{max-width:22rem}}h1{{margin:0 0 12px;font-size:1.45rem}}p{{margin:0;color:#d7e0ec;line-height:1.5}}button{{display:none;align-items:center;justify-content:center;margin-top:22px;min-height:46px;border:0;border-radius:10px;padding:0 16px;background:#334155;color:#fff;font:inherit;font-weight:700}}
</style>
<main><section><h1 id="title">Проверяем подключение…</h1><p id="detail">Это займёт несколько секунд.</p><button id="reauth">Войти в Instagram</button></section></main>
<script>
const title=document.querySelector('#title'),detail=document.querySelector('#detail'),reauth=document.querySelector('#reauth');
const labels={{preparing:['Проверяем подключение…','Это займёт несколько секунд.'],connected:['Instagram подключён','Профиль подтверждён. Эту страницу можно закрыть.'],completed:['Instagram подключён','Профиль подтверждён. Эту страницу можно закрыть.'],expired:['Ссылка истекла','Создайте новую защищённую ссылку.'],cancelled:['Сессия отменена','Создайте новую защищённую ссылку.'],login:['Требуется повторный вход','Instagram запросил авторизацию.'],challenge:['Требуется повторный вход','Завершите проверку в реальной странице Instagram.']}};
async function verify(){{const r=await fetch('/remote/{sid}/verify-profile',{{method:'POST',credentials:'same-origin'}});if(!r.ok){{title.textContent='Требуется повторный вход';detail.textContent='Откройте реальную страницу Instagram.';reauth.style.display='inline-flex'}}}}
async function poll(){{const r=await fetch('/remote/{sid}/state',{{cache:'no-store'}});if(!r.ok)return;const s=await r.json(),text=labels[s.state]||labels.login;title.textContent=text[0];detail.textContent=text[1];if(['login','challenge'].includes(s.state))reauth.style.display='inline-flex';if(['connected','completed','expired','cancelled'].includes(s.state))reauth.remove()}}
reauth.addEventListener('click',()=>location.assign('/remote/{sid}/interactive'));verify();poll();setInterval(poll,2500);
</script></html>"""
    return HTMLResponse(html, headers=_security_headers())


def _full_bleed_remote_viewer_page(session_id: UUID) -> HTMLResponse:
    """Full-bleed, width-first mobile frame around maintained same-origin noVNC."""
    sid = escape(str(session_id))
    query = urlencode({"autoconnect": "true", "resize": "scale", "path": f"remote/{sid}/websockify"})
    html = f"""<!doctype html>
<html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>Подключение Instagram</title>
<style>
html,body,main{{width:100%;height:100%;margin:0;overflow:hidden;background:#162033;color:#fff;font:16px system-ui}}
main{{position:relative}}
#viewer{{position:absolute;inset:0;display:block;width:100%;height:100%;border:0;background:#000}}
#checking{{position:fixed;z-index:1;inset:0;display:grid;place-items:center;padding:24px;background:#162033;text-align:center}}#checking[hidden]{{display:none}}#checking h1{{margin:0 0 12px;font-size:1.45rem}}#checking p{{margin:0;color:#d7e0ec;line-height:1.5}}
header,footer{{box-sizing:border-box;position:fixed;z-index:2;left:0;right:0;background:#162033}}
header{{top:0;min-height:54px;padding:calc(10px + env(safe-area-inset-top)) 16px 10px}}
footer{{bottom:0;display:flex;gap:8px;padding:10px 16px calc(10px + env(safe-area-inset-bottom))}}
#state{{font-weight:700}}
button{{min-height:44px;border:0;border-radius:10px;padding:10px 13px;background:#ea5701;color:#fff;font:inherit;font-weight:700}}
button.secondary{{background:#334155}}button:disabled{{opacity:.55}}
</style>
<main><iframe id="viewer" title="Удалённый Chromium" src="/remote/{sid}/vnc/vnc.html?{query}"></iframe><section id="checking" hidden><div><h1>Проверяем подключение…</h1><p>Instagram подтверждает авторизацию.</p></div></section>
<header><div id="state">Подготовка браузера…</div></header>
<footer><button id="open">Открыть вход Instagram</button><button id="keyboard" class="secondary">Клавиатура</button></footer></main>
<script>
const viewer=document.querySelector('#viewer'),state=document.querySelector('#state'),open=document.querySelector('#open'),keyboard=document.querySelector('#keyboard'),checking=document.querySelector('#checking'),checkingTitle=checking.querySelector('h1'),checkingDetail=checking.querySelector('p');
const REMOTE_WIDTH=430,REMOTE_HEIGHT=800;
function installNoVncLayout(){{
  const doc=viewer.contentDocument;if(!doc)return;
  const style=doc.createElement('style');
  style.textContent=`html,body{{margin:0!important;overflow:hidden!important;background:#000!important}}#noVNC_control_bar_anchor{{display:none!important}}#noVNC_keyboardinput{{font-size:16px!important}}#noVNC_container{{width:100%!important;height:max(100%,calc(100vw * ${{REMOTE_HEIGHT}} / ${{REMOTE_WIDTH}}))!important;margin:0!important;background:#000!important;border-radius:0!important;overflow:hidden!important}}`;
  doc.head.append(style);
  let viewport=doc.querySelector('meta[name=viewport]');if(!viewport){{viewport=doc.createElement('meta');viewport.name='viewport';doc.head.append(viewport)}}viewport.content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no';
  const resizeRemote=()=>{{
    const container=doc.querySelector('#noVNC_container');if(!container)return;
    const height=Math.max(viewer.clientHeight,Math.ceil(viewer.clientWidth*REMOTE_HEIGHT/REMOTE_WIDTH));
    container.style.height=`${{height}}px`;
    doc.defaultView?.dispatchEvent(new Event('resize'));
  }};
  resizeRemote();window.addEventListener('resize',resizeRemote);new ResizeObserver(resizeRemote).observe(viewer);
}}
viewer.addEventListener('load',installNoVncLayout);
keyboard.addEventListener('click',()=>{{viewer.contentDocument?.querySelector('#noVNC_keyboard_button')?.click()}});
open.addEventListener('click',async()=>{{open.disabled=true;const r=await fetch('/remote/{sid}/open-login',{{method:'POST',credentials:'same-origin'}});state.textContent=r.ok?'Войдите в Instagram.':'Требуется повторное подключение.'}});
const labels={{preparing:'Подготовка браузера…',login:'Войдите в Instagram.',challenge:'Завершите 2FA или CAPTCHA.',verifying:'Проверяем подключение…',connected:'Instagram подключён.',expired:'Ссылка истекла.',cancelled:'Сессия отменена.',completed:'Instagram подключён.'}};
function showChecking(title='Проверяем подключение…',detail='Instagram подтверждает авторизацию.'){{checkingTitle.textContent=title;checkingDetail.textContent=detail;checking.hidden=false;viewer.style.visibility='hidden';open.style.display='none';keyboard.style.display='none'}}function showRemote(){{checking.hidden=true;viewer.style.visibility='visible';open.style.display='';keyboard.style.display=''}}
async function poll(){{const r=await fetch('/remote/{sid}/state',{{cache:'no-store'}});if(!r.ok)return;const s=await r.json();state.textContent=labels[s.state]||'Требуется повторное подключение.';if(s.state==='verifying')showChecking();else if(['login','challenge'].includes(s.state))showRemote();if(['connected','completed'].includes(s.state)){{showChecking('Instagram подключён','Профиль подтверждён. Эту страницу можно закрыть.');viewer.remove();open.remove();keyboard.remove()}}else if(['expired','cancelled'].includes(s.state)){{showChecking(labels[s.state],'Создайте новую защищённую ссылку.');viewer.remove();open.remove();keyboard.remove()}}}}
poll();setInterval(poll,5000);
</script></html>"""
    return HTMLResponse(html, headers=_security_headers())


def _responsive_remote_viewer_page(session_id: UUID) -> HTMLResponse:
    """Phone-first shell using the maintained noVNC UI inside a same-origin iframe."""
    sid = escape(str(session_id))
    query = urlencode({"autoconnect": "true", "resize": "scale", "path": f"remote/{sid}/websockify"})
    html = f"""<!doctype html><html lang=\"ru\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><title>Подключение Instagram</title><style>html,body,main{{height:100%;margin:0;background:#162033;color:#fff;font:16px system-ui}}main{{position:relative}}#viewer{{display:block;border:0;width:100%;height:100%;background:#000}}header,footer{{position:absolute;z-index:2;left:12px;right:12px;background:rgba(22,32,51,.92);border-radius:12px;box-shadow:0 4px 18px rgba(0,0,0,.25)}}header{{top:calc(10px + env(safe-area-inset-top));padding:10px 12px}}footer{{bottom:calc(10px + env(safe-area-inset-bottom));padding:8px;display:flex;gap:8px}}#state{{font-weight:700}}button{{border:0;border-radius:10px;padding:10px 13px;background:#ea5701;color:#fff;font:inherit;font-weight:700}}button.secondary{{background:#334155}}button:disabled{{opacity:.55}}</style><main><iframe id=\"viewer\" title=\"Удалённый Chromium\" src=\"/remote/{sid}/vnc/vnc.html?{query}\"></iframe><header><div id=\"state\">Подготовка браузера…</div></header><footer><button id=\"open\">Открыть Instagram</button><button id=\"keyboard\" class=\"secondary\">Клавиатура</button></footer></main><script>const viewer=document.querySelector('#viewer'),state=document.querySelector('#state'),open=document.querySelector('#open'),keyboard=document.querySelector('#keyboard');viewer.addEventListener('load',()=>{{const doc=viewer.contentDocument;if(!doc)return;const style=doc.createElement('style');style.textContent='#noVNC_control_bar_anchor{{display:none!important}}html,body,#noVNC_container,#noVNC_screen{{width:100%!important;height:100%!important;margin:0!important;background:#000!important;border-radius:0!important}}';doc.head.append(style)}});keyboard.addEventListener('click',()=>{{viewer.contentDocument?.querySelector('#noVNC_keyboard_button')?.click()}});open.addEventListener('click',async()=>{{open.disabled=true;const r=await fetch('/remote/{sid}/open-instagram',{{method:'POST',credentials:'same-origin'}});state.textContent=r.ok?'Войдите в Instagram.':'Требуется повторное подключение.'}});const labels={{preparing:'Подготовка браузера…',login:'Войдите в Instagram.',challenge:'Завершите 2FA или CAPTCHA.',connected:'Instagram подключён.',expired:'Ссылка истекла.',cancelled:'Сессия отменена.',completed:'Instagram подключён.'}};async function poll(){{const r=await fetch('/remote/{sid}/state',{{cache:'no-store'}});if(!r.ok)return;const s=await r.json();state.textContent=labels[s.state]||'Требуется повторное подключение.';if(['connected','completed','expired','cancelled'].includes(s.state)){{viewer.remove();open.remove();keyboard.remove()}}}}poll();setInterval(poll,5000);</script></html>"""
    return HTMLResponse(html, headers=_security_headers())


def _remote_viewer_page(session_id: UUID) -> HTMLResponse:
    """A phone-first shell around noVNC core, never an Instagram credential form."""
    sid = escape(str(session_id))
    html = f"""<!doctype html><html lang=\"ru\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><title>Instagram connection</title><style>html,body{{height:100%;margin:0;background:#111827;color:#f8fafc;font:16px system-ui}}main{{height:100%;display:grid;grid-template-rows:auto 1fr auto;max-width:34rem;margin:auto}}header,footer{{padding:calc(12px + env(safe-area-inset-top)) 16px 12px;background:#182235}}footer{{padding:12px 16px calc(12px + env(safe-area-inset-bottom));display:flex;gap:10px}}#state{{font-weight:650}}#screen{{min-height:0;background:#000;touch-action:none}}button{{border:0;border-radius:12px;padding:11px 14px;font:inherit;font-weight:650;color:#fff;background:#e1306c}}button.secondary{{background:#334155}}button:disabled{{opacity:.55}}textarea{{position:absolute;left:-40px;width:1px;height:1px;opacity:0}}</style><main><header><div id=\"state\">Подготовка браузера…</div></header><div id=\"screen\" aria-label=\"Удалённый Chromium\"></div><footer><button id=\"open\">Открыть Instagram</button><button id=\"keyboard\" class=\"secondary\">Клавиатура</button></footer></main><textarea id=\"keyboardinput\" autocapitalize=\"off\" autocomplete=\"off\" spellcheck=\"false\"></textarea><script type=\"module\">import RFB from '/remote/{sid}/vnc/core/rfb.js';import Keyboard from '/remote/{sid}/vnc/core/input/keyboard.js';import KeyTable from '/remote/{sid}/vnc/core/input/keysym.js';import keysyms from '/remote/{sid}/vnc/core/input/keysymdef.js';const screen=document.querySelector('#screen'),state=document.querySelector('#state'),open=document.querySelector('#open'),input=document.querySelector('#keyboardinput');const rfb=new RFB(screen,`wss://${{location.host}}/remote/{sid}/websockify`);rfb.scaleViewport=true;rfb.resizeSession=true;const keyboard=new Keyboard(input);keyboard.onkeyevent=(keysym,code,down)=>rfb.sendKey(keysym,code,down);keyboard.grab();let previous=' ';function reset(){{input.value=' ';previous=' '}}reset();input.addEventListener('input',event=>{{const value=event.target.value;let inputs=value.length-previous.length,backspaces=inputs<0?-inputs:0;for(let i=0;i<Math.min(previous.length,value.length);i++){{if(value.charAt(i)!==previous.charAt(i)){{inputs=value.length-i;backspaces=previous.length-i;break}}}}for(let i=0;i<backspaces;i++)rfb.sendKey(KeyTable.XK_BackSpace,'Backspace');for(let i=value.length-inputs;i<value.length;i++)rfb.sendKey(keysyms.lookup(value.charCodeAt(i)));if(value.length>64||value.length<1){{reset();if(value.length<1)setTimeout(()=>input.focus(),0)}}else previous=value}});document.querySelector('#keyboard').addEventListener('click',()=>input.focus());open.addEventListener('click',async()=>{{open.disabled=true;const r=await fetch('/remote/{sid}/open-instagram',{{method:'POST',credentials:'same-origin'}});if(!r.ok)state.textContent='Требуется повторное подключение.';else state.textContent='Войдите в Instagram.'}});const labels={{preparing:'Подготовка браузера…',login:'Войдите в Instagram.',challenge:'Завершите 2FA или CAPTCHA.',connected:'Instagram подключён.',expired:'Ссылка истекла.',cancelled:'Сессия отменена.',completed:'Instagram подключён.'}};async function poll(){{const r=await fetch('/remote/{sid}/state',{{cache:'no-store'}});if(!r.ok)return;const s=await r.json();state.textContent=labels[s.state]||'Требуется повторное подключение.';if(['connected','completed','expired','cancelled'].includes(s.state)){{screen.replaceChildren();open.remove();document.querySelector('#keyboard').remove()}}}}poll();setInterval(poll,5000);</script></html>"""
    return HTMLResponse(html, headers=_security_headers())


def _connection_start_page(session_id: UUID) -> HTMLResponse:
    """Read a fragment-only token and require a deliberate user activation."""
    sid = escape(str(session_id))
    html = f"""<!doctype html><html lang=\"ru\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><title>Instagram connection</title><style>html,body{{height:100%;margin:0;background:#111;color:#fff;font:17px system-ui;display:grid;place-items:center}}main{{max-width:26rem;padding:2rem;text-align:center}}button{{font:inherit;padding:.8rem 1.1rem;border:0;border-radius:.6rem;background:#4d6fff;color:white}}p{{line-height:1.45}}</style><main><p id=\"state\">Tap to open the protected remote browser.</p><button id=\"open\">Open browser</button></main><script>const token=location.hash.slice(1)||new URLSearchParams(location.search).get('launch_token')||'';history.replaceState(null,'',location.pathname);const state=document.querySelector('#state'),button=document.querySelector('#open');button.addEventListener('click',async()=>{{if(!token){{state.textContent='Reconnect is required.';button.remove();return}}button.disabled=true;state.textContent='Preparing browser…';try{{const r=await fetch('/connect/{sid}/activate',{{method:'POST',headers:{{'Content-Type':'application/json'}},credentials:'same-origin',body:JSON.stringify({{launch_token:token}})}});if(!r.ok)throw new Error();location.replace('/remote/{sid}')}}catch(_error){{state.textContent='Reconnect is required.';button.remove()}}}});</script></html>"""
    return HTMLResponse(html.replace("vnc_lite.html", "vnc.html"), headers=_security_headers())


def _login_page(session_id: UUID) -> HTMLResponse:
    sid = escape(str(session_id))
    html = f"""<!doctype html><html lang=\"ru\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><title>Подключение Instagram</title><style>html,body{{height:100%;margin:0;background:#111;color:#fff;font:16px system-ui}}main{{height:100%;display:grid;grid-template-rows:auto 1fr}}#state{{padding:12px env(safe-area-inset-right) 12px env(safe-area-inset-left);background:#1e1e1e}}iframe{{border:0;width:100%;height:100%}}</style><main><div id=\"state\">Подготовка браузера…</div><iframe title=\"Удалённый Chromium\" allow=\"clipboard-read; clipboard-write\" src=\"/remote/{sid}/vnc/vnc_lite.html?{urlencode({"autoconnect": "true", "resize": "remote", "path": f"remote/{sid}/websockify"})}\"></iframe></main><script>const text={{preparing:'Подготовка браузера…',login:'Войдите в Instagram.',challenge:'Завершите 2FA или CAPTCHA.',connected:'Instagram подключён.',expired:'Ссылка истекла.',cancelled:'Сессия отменена.',completed:'Instagram подключён.'}};async function p(){{let r=await fetch('/remote/{sid}/state',{{cache:'no-store'}});if(!r.ok)return;let s=await r.json();document.querySelector('#state').textContent=text[s.state]||'Требуется повторное подключение.';if(['connected','completed','expired','cancelled'].includes(s.state))document.querySelector('iframe').remove();}}p();setInterval(p,5000);</script></html>"""
    return HTMLResponse(html.replace("vnc_lite.html", "vnc.html"), headers=_security_headers())


def _unavailable_page(message: str) -> HTMLResponse:
    return HTMLResponse(
        f'<!doctype html><meta name="viewport" content="width=device-width"><p>{escape(message)}</p>',
        headers=_security_headers(),
    )


def _state_json(status: LoginSessionStatus, browser_state: str | None) -> str:
    if status is LoginSessionStatus.ACTIVE:
        return '{"state":"' + (browser_state or "preparing") + '"}'
    return '{"state":"' + status.value + '"}'
