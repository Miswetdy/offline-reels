"""Minimal in-memory CookieJar extraction from a live browser context."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.cookiejar import Cookie, CookieJar
from typing import Protocol

from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode

COOKIE_NAMES = frozenset({"sessionid", "csrftoken"})


class BrowserCookieContext(Protocol):
    def cookies(self) -> list[dict[str, object]]: ...


@dataclass(frozen=True, repr=False)
class SessionCookie:
    name: str
    value: str = field(repr=False)
    domain: str
    path: str
    secure: bool
    expires_at: float | None


class SessionCookieJar:
    def __init__(self, cookies: tuple[SessionCookie, ...]) -> None:
        self._cookies = cookies

    def __repr__(self) -> str:
        return "SessionCookieJar(redacted)"

    def to_http_cookiejar(self) -> CookieJar:
        result = CookieJar()
        for item in self._cookies:
            result.set_cookie(
                Cookie(
                    version=0,
                    name=item.name,
                    value=item.value,
                    port=None,
                    port_specified=False,
                    domain=item.domain,
                    domain_specified=True,
                    domain_initial_dot=item.domain.startswith("."),
                    path=item.path,
                    path_specified=True,
                    secure=item.secure,
                    expires=item.expires_at,
                    discard=item.expires_at is None,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
            )
        return result

    def clear(self) -> None:
        self._cookies = ()


class SessionCookieProvider:
    def get(self, context: BrowserCookieContext) -> SessionCookieJar:
        now = datetime.now(UTC).timestamp()
        accepted: list[SessionCookie] = []
        for raw in context.cookies():
            name = raw.get("name")
            value = raw.get("value")
            domain = raw.get("domain")
            path = raw.get("path")
            secure = raw.get("secure")
            expires = raw.get("expires")
            if (
                name not in COOKIE_NAMES
                or not isinstance(value, str)
                or not isinstance(domain, str)
                or not isinstance(path, str)
                or not secure
                or not _instagram_domain(domain)
            ):
                continue
            expires_at = (
                float(expires)
                if isinstance(expires, int | float) and expires > 0
                else None
            )
            if expires_at is not None and expires_at <= now:
                continue
            accepted.append(
                SessionCookie(name, value, domain, path or "/", bool(secure), expires_at)
            )
        if not any(cookie.name == "sessionid" for cookie in accepted):
            raise CollectorRuntimeError(RuntimeReasonCode.AUTH_REQUIRED)
        return SessionCookieJar(tuple(accepted))


def _instagram_domain(domain: str) -> bool:
    normalized = domain.lstrip(".").lower()
    return normalized == "instagram.com" or normalized.endswith(".instagram.com")
