"""Mobile-viewport acceptance for the disposable Stage 7 fixture only."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright
from sqlalchemy import select

from app.api.management import hash_secret
from app.core.settings import get_settings
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    ManagementPairingChallenge,
)
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus

TECHNICAL_UI = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|"
    r"shortcode|codec|object[_ -]?key|reason[_ -]?code|\b\d+\s*(?:bytes|байт)",
    re.IGNORECASE,
)
TECHNICAL_UI_EXTRA = re.compile(r"\bHTTP\s*\d{3}\b|stack trace", re.IGNORECASE)
RAW_TECHNICAL_SENTINELS = ("AUTH_REQUIRED", "FIXTURE_INTERNAL_REASON")


def wait_for_dashboard(page) -> None:
    """Wait for the reverse proxy and web server without relying on Compose start order."""
    deadline = time.monotonic() + 45
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            page.goto("https://localhost/", wait_until="domcontentloaded", timeout=5_000)
            page.get_by_label("Одноразовый код").wait_for(timeout=5_000)
            return
        except Exception as error:  # Playwright gives the useful final readiness error.
            last_error = error
            time.sleep(1)
    raise AssertionError("Stage 7 dashboard did not become ready") from last_error


def wait_for_condition(condition, description: str, timeout_seconds: float = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {description}")


def assert_fixed_dashboard_return(page) -> None:
    location = urlparse(page.url)
    assert (location.scheme, location.netloc, location.path) == ("https", "localhost", "/")
    assert location.query == ""
    assert location.fragment == ""


def assert_no_technical_ui(page) -> None:
    body = page.locator("body").inner_text()
    assert TECHNICAL_UI.search(body) is None
    assert TECHNICAL_UI_EXTRA.search(body) is None
    assert not any(value in body for value in RAW_TECHNICAL_SENTINELS)


def latest_fixture_run_status() -> str | None:
    with create_session_factory(get_settings())() as db:
        statement = select(InstagramCollectionRun).order_by(
            InstagramCollectionRun.created_at.desc()
        )
        run = db.scalar(statement)
        return run.status if run is not None else None


def require_fixture_reauthentication() -> None:
    """Model a server-observed auth loss without any external integration."""
    with create_session_factory(get_settings()).begin() as db:
        account = db.scalar(select(InstagramAccount).limit(1))
        if account is None:
            raise AssertionError("Fixture account is missing")
        account.status = AccountStatus.REAUTH_REQUIRED.value
        account.reauth_required_at = datetime.now(UTC)
        # This deliberately must not appear in any user-facing UI string.
        account.reason_code = "AUTH_REQUIRED"


def seed_expired_pairing_code() -> str:
    """Create a fixture-only expired operator code without exposing it in the UI."""
    secret = "expired-fixture-pairing-code"
    with create_session_factory(get_settings()).begin() as db:
        account = db.scalar(select(InstagramAccount).limit(1))
        if account is None:
            raise AssertionError("Fixture account is missing")
        db.add(
            ManagementPairingChallenge(
                account_id=account.id,
                secret_hash=hash_secret(secret),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    return secret


def main() -> int:
    pairing_code = os.environ["STAGE7_FIXTURE_PAIRING_SECRET"]
    management_responses: list[tuple[str, str | None]] = []
    management_requests: list[str] = []

    def record_response(response) -> None:
        is_management = "/api/management/" in response.url or "/api/instagram/" in response.url
        if is_management and response.status < 400:
            management_responses.append((response.url, response.headers.get("cache-control")))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            # Service Worker registration independently validates TLS. The
            # disposable Caddy fixture uses its own internal CA, so Chromium
            # must accept that CA at process scope as well as page scope.
            args=["--host-resolver-rules=MAP localhost caddy", "--ignore-certificate-errors"],
        )
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.on("response", record_response)
        page.on(
            "request",
            lambda request: management_requests.append(request.url)
            if "/api/management/" in request.url or "/api/instagram/" in request.url
            else None,
        )
        wait_for_dashboard(page)
        unauthenticated_status, unauthenticated_cache_control = page.evaluate(
            """
            async () => {
                const response = await fetch('/api/management/session', { cache: 'no-store' });
                return [response.status, response.headers.get('cache-control')];
            }
            """
        )
        assert unauthenticated_status == 401
        assert unauthenticated_cache_control == "no-store"

        expired_pairing_code = seed_expired_pairing_code()
        pairing_input = page.get_by_label("Одноразовый код")
        pairing_input.fill(expired_pairing_code)
        page.get_by_role("button", name="Подтвердить").click()
        page.get_by_text("Код недействителен или срок его действия истёк.").wait_for()
        assert_no_technical_ui(page)

        pairing_exchange_pattern = "**/api/management/pairing/exchange"
        raw_pairing_error = {
            "error": {
                "code": "FIXTURE_INTERNAL_REASON",
                "message": (
                    "00000000-0000-4000-8000-000000000001 shortcode codec "
                    "object_key reason_code HTTP 429 stack trace 4096 bytes"
                ),
            }
        }

        def rate_limited_pairing(route) -> None:
            route.fulfill(
                status=429,
                content_type="application/json",
                body=json.dumps(raw_pairing_error),
            )

        page.route(pairing_exchange_pattern, rate_limited_pairing)
        pairing_input.fill("rate-limited-fixture-pairing-code")
        page.get_by_role("button", name="Подтвердить").click()
        page.get_by_text("Слишком много попыток. Попробуйте позже.").wait_for()
        assert_no_technical_ui(page)
        page.unroute(pairing_exchange_pattern, rate_limited_pairing)

        def temporary_pairing(route) -> None:
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps(raw_pairing_error),
            )

        page.route(pairing_exchange_pattern, temporary_pairing)
        pairing_input.fill("temporary-fixture-pairing-code")
        page.get_by_role("button", name="Подтвердить").click()
        page.get_by_text("Не удалось подключить устройство. Попробуйте позже.").wait_for()
        assert_no_technical_ui(page)
        page.unroute(pairing_exchange_pattern, temporary_pairing)

        page.get_by_label("Одноразовый код").fill(pairing_code)
        page.get_by_role("button", name="Подтвердить").click()
        page.get_by_text("Instagram не подключён").wait_for()
        assert page.get_by_label("Одноразовый код").count() == 0

        page.get_by_role("button", name="Подключить Instagram").click()
        page.get_by_text("Instagram подключён").wait_for()

        require_fixture_reauthentication()
        page.get_by_text("Требуется переподключение Instagram").wait_for(timeout=8_000)
        page.get_by_role("button", name="Переподключить Instagram").wait_for()
        assert_no_technical_ui(page)
        page.get_by_role("button", name="Переподключить Instagram").click()
        page.get_by_text("Instagram подключён").wait_for(timeout=10_000)

        # Cancel while the Collector owns the run.  The fixture delay leaves
        # the run cancellable long enough to exercise the real control-plane
        # cancellation endpoint and prevents a late worker response from
        # advancing the dashboard to normalization.
        page.get_by_role("button", name="Загрузить Reels").click()
        page.get_by_text("Получаем Reels").wait_for()
        wait_for_condition(
            lambda: latest_fixture_run_status() is not None, "the first collection run"
        )
        page.get_by_role("button", name="Отменить загрузку").click()
        page.get_by_role("button", name="Загрузить Reels").wait_for()
        assert_fixed_dashboard_return(page)
        assert page.get_by_text("Подготавливаем видео").count() == 0
        wait_for_condition(
            lambda: latest_fixture_run_status() == "cancelled",
            "fixture collector cancellation",
            timeout_seconds=8,
        )

        # Stall one actual local stream after catalog enqueue.  This leaves
        # the sequential production queue active so its existing cancelBatch
        # path, rather than a fixture substitute, is exercised.
        held_streams = []

        def hold_stream(route) -> None:
            held_streams.append(route)

        stream_pattern = "**/api/videos/*/stream"
        page.route(stream_pattern, hold_stream)
        page.evaluate(
            """
            globalThis.stage7StageHistory = [];
            new MutationObserver(() => {
                globalThis.stage7StageHistory.push(document.body.innerText);
            }).observe(document.body, { childList: true, characterData: true, subtree: true });
            """
        )
        page.get_by_role("button", name="Загрузить Reels").click()
        page.get_by_text("Получаем Reels").wait_for()
        page.get_by_text("Подготавливаем видео").wait_for()
        page.get_by_text("Загружаем на устройство").wait_for()
        wait_for_condition(lambda: len(held_streams) == 1, "the first local video stream")
        page.get_by_role("button", name="Отменить загрузку").click()
        held_streams[0].abort()
        page.unroute(stream_pattern, hold_stream)
        page.get_by_role("button", name="Загрузить Reels").wait_for()
        page.wait_for_timeout(1_000)
        assert_fixed_dashboard_return(page)
        assert len(held_streams) == 1

        # A subsequent operation uses a fresh idempotency key and must still
        # complete after either cancellation path. The fixture has eleven
        # seed videos plus two completed ten-video runs, so its real catalog
        # spans two standard 30-item cursor pages. The second response is
        # deliberately given one item from page one, exercising the frontend
        # deduplication boundary without changing the production video API.
        catalog_pages: list[tuple[str | None, int]] = []
        first_catalog_item: dict[str, object] | None = None
        duplicate_injected = False
        final_stream_ids: list[str] = []

        def paginate_with_duplicate(route) -> None:
            nonlocal first_catalog_item, duplicate_injected
            request = route.request
            parsed = urlparse(request.url)
            query = parse_qs(parsed.query)
            cursor = query.get("cursor", [None])[0]
            # route.fetch() bypasses Chromium's host-resolver mapping and
            # would resolve localhost inside this E2E container. The catalog
            # is public, so read the same production endpoint directly across
            # the isolated fixture Docker network instead.
            with urlopen(
                f"http://api:8000/videos?{parsed.query}",
                timeout=10,
            ) as response:
                payload = json.load(response)
            items = payload["items"]
            catalog_pages.append((cursor, len(items)))
            if cursor is None:
                assert items
                first_catalog_item = items[0]
            elif first_catalog_item is not None and not duplicate_injected:
                payload["items"] = [*items, first_catalog_item]
                duplicate_injected = True
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        def record_final_stream(request) -> None:
            parsed = urlparse(request.url)
            if parsed.path.startswith("/api/videos/") and parsed.path.endswith("/stream"):
                final_stream_ids.append(parsed.path.split("/")[-2])

        catalog_pattern = "**/api/videos?*"
        page.route(catalog_pattern, paginate_with_duplicate)
        page.on("request", record_final_stream)
        page.get_by_role("button", name="Загрузить Reels").click()
        page.get_by_text("Получаем Reels").wait_for()
        page.get_by_text("Подготавливаем видео").wait_for()
        page.wait_for_url("https://localhost/offline", timeout=30_000)
        page.locator("video").first.wait_for(state="attached")
        page.locator("video").first.evaluate(
            "video => new Promise((resolve, reject) => {"
            "if (video.readyState >= HTMLMediaElement.HAVE_METADATA) resolve();"
            "else { video.addEventListener('loadedmetadata', resolve, { once: true });"
            "video.addEventListener('error', () => reject(new Error('fixture media failed')), "
            "{ once: true }); }"
            "})"
        )
        assert "Не удалось воспроизвести видео." not in page.locator("body").inner_text()
        page.unroute(catalog_pattern, paginate_with_duplicate)
        assert len(catalog_pages) == 2
        assert catalog_pages[0] == (None, 30)
        assert catalog_pages[1][0]
        assert catalog_pages[1][1] == 1
        assert duplicate_injected
        assert len(final_stream_ids) == 31
        assert len(set(final_stream_ids)) == 31
        stage_history = page.evaluate("globalThis.stage7StageHistory")

        page.goto("https://localhost/", wait_until="domcontentloaded")
        page.get_by_text("Instagram подключён").wait_for(timeout=10_000)
        service_worker_ready = page.evaluate(
            """
            async () => {
                if (!navigator.serviceWorker) return false;
                const registration = await Promise.race([
                    navigator.serviceWorker.ready.then((value) => value),
                    new Promise((resolve) => setTimeout(() => resolve(null), 5000)),
                ]);
                return registration !== null;
            }
            """
        )
        assert service_worker_ready
        # A first-install page is intentionally not assumed to be controlled;
        # reload online once, then prove the installed shell controls it before
        # exercising the browser's real offline event on the dashboard.
        page.reload(wait_until="domcontentloaded")
        page.get_by_text("Instagram подключён").wait_for(timeout=10_000)
        assert page.evaluate("Boolean(navigator.serviceWorker?.controller)")
        requests_before_offline = len(management_requests)
        context.set_offline(True)
        page.get_by_text("Нет подключения").wait_for()
        assert page.get_by_role("button", name="Загрузить Reels").is_disabled()
        assert page.get_by_role("button", name="Очистить библиотеку").is_enabled()
        offline_body = page.locator("body").inner_text()
        assert "Не удалось загрузить каталог" not in offline_body
        assert "Повторить" not in offline_body
        page.wait_for_timeout(3_500)
        assert len(management_requests) == requests_before_offline
        context.set_offline(False)
        page.get_by_text("Онлайн").wait_for()
        page.get_by_text("Instagram подключён").wait_for(timeout=10_000)

        # Revoke only through the dashboard. A subsequent protected request
        # must be rejected and the PWA must return to its pairing onboarding.
        page.get_by_role("button", name="Отключить это устройство").click()
        page.get_by_label("Одноразовый код").wait_for()
        revoked_status = page.evaluate(
            """
            async () => (await fetch('/api/instagram/status', { cache: 'no-store' })).status
            """
        )
        assert revoked_status == 401

        all_observed_text = "\n".join(stage_history)
        assert "Загружаем на устройство" in all_observed_text

        assert_no_technical_ui(page)
        assert management_responses
        missing_no_store = [
            response_url
            for response_url, cache_control in management_responses
            if cache_control != "no-store"
        ]
        assert not missing_no_store, f"management responses missing no-store: {missing_no_store}"
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
