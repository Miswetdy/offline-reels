import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const origin = process.env.STAGE9_E2E_ORIGIN;
const pairingSecret = process.env.STAGE9_E2E_PAIRING_SECRET;
const secondPairingSecret = process.env.STAGE9_E2E_SECOND_PAIRING_SECRET;

function fixture() {
  if (!origin || !pairingSecret || !secondPairingSecret) throw new Error("Stage 9 fixture environment is required.");
  return { origin, pairingSecret, secondPairingSecret };
}

async function localState(page: Page) {
  return page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("offline-reels");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const records = await new Promise<Array<{ id: string; status: string; viewedAt?: string; deletionState?: string }>>((resolve, reject) => {
      const request = db.transaction("offlineVideos", "readonly").objectStore("offlineVideos").getAll();
      request.onsuccess = () => resolve(request.result as Array<{ id: string; status: string; viewedAt?: string; deletionState?: string }>);
      request.onerror = () => reject(request.error);
    });
    db.close();
    const keys = await (await caches.open("offline-reels-media-v1")).keys();
    return { records, cacheKeys: keys.map((key) => key.url) };
  });
}

async function openFixtureHome(page: Page) {
  const { origin } = fixture();
  let lastError: unknown;
  // Caddy can accept the health request during its final upstream hand-off
  // and close exactly the next TLS connection. Bound a retry to this
  // disposable fixture startup race; it never masks later test failures.
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await page.goto(origin, { waitUntil: "domcontentloaded", timeout: 30_000 });
      await expect(page.locator("#pairing-code")).toBeVisible({ timeout: 10_000 });
      return;
    } catch (error) {
      lastError = error;
      if (attempt < 4) await page.waitForTimeout(750);
    }
  }
  throw lastError;
}

async function pairAndConnect(page: Page, secret: string) {
  const env = fixture();
  await openFixtureHome(page);
  await page.locator("#pairing-code").fill(secret);
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("heading", { name: "Instagram" })).toBeVisible({ timeout: 30_000 });
  // The synthetic gateway first returns /#, then the App Router normalizes
  // that fragment back to /. Both transitions must finish before manual
  // download begins.
  const toGatewayReturn = page.waitForEvent("framenavigated", (frame) => frame === page.mainFrame() && frame.url() === `${env.origin}/#`);
  const toApplication = page.waitForEvent("framenavigated", (frame) => frame === page.mainFrame() && frame.url() === `${env.origin}/`);
  await page.getByRole("button", { name: "Подключить Instagram" }).click();
  await toGatewayReturn;
  await toApplication;
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("button", { name: "Загрузить Reels" })).toBeVisible({ timeout: 30_000 });
}

async function waitCompleted(page: Page, expected: number) {
  await expect.poll(async () => (await localState(page)).records.filter((record) => record.status === "completed").length, { timeout: 90_000 }).toBe(expected);
}

async function activeVideo(page: Page) {
  const feed = page.locator("main[aria-label='Video feed']");
  await expect.poll(() => feed.getAttribute("data-committed-item-id")).not.toBeNull();
  const reelId = await feed.getAttribute("data-committed-item-id");
  if (reelId === null) throw new Error("Stage 9 fixture has no committed active Reel.");
  return { reelId, video: page.locator(`section[data-video-id="${reelId}"] video`) };
}

async function emitPlaybackSignals(page: Page) {
  const { video } = await activeVideo(page);
  await expect(video).toBeVisible();
  await video.evaluate((node) => {
    // The unit suite covers native media timing. This fixture sends the same
    // browser events without depending on Chromium's native decoder after a
    // fresh service-worker takeover; none may enter the viewed lifecycle.
    for (const type of ["play", "timeupdate", "pause", "ended"]) {
      node.dispatchEvent(new Event(type));
    }
  });
}

async function assertOfflineMediaRoute(page: Page, id: string) {
  const response = await page.evaluate(async (reelId) => {
    const media = await fetch(`/offline-media/${reelId}`, { cache: "no-store" });
    return {
      bytes: (await media.arrayBuffer()).byteLength,
      contentType: media.headers.get("content-type"),
      controlled: navigator.serviceWorker.controller !== null,
      status: media.status,
    };
  }, id);
  expect(response.controlled).toBe(true);
  expect(response.status).toBe(200);
  expect(response.contentType).toContain("video/mp4");
  expect(response.bytes).toBeGreaterThan(100);
}

async function pairSecondAccount(context: BrowserContext) {
  const page = await context.newPage();
  await pairAndConnect(page, fixture().secondPairingSecret);
  return page;
}

test("Stage 9 disposable mobile lifecycle fixture", async ({ page, context, browser }) => {
  const env = fixture();
  let confirmedViewSyncPosts = 0;
  let confirmedCollectionPosts = 0;
  page.on("response", (response) => {
    if (response.url().includes("/api/instagram/views/sync") && response.request().method() === "POST" && response.ok()) confirmedViewSyncPosts += 1;
    if (response.url().includes("/api/instagram/collection-runs") && response.request().method() === "POST" && response.ok()) confirmedCollectionPosts += 1;
  });
  await pairAndConnect(page, env.pairingSecret);
  // The fixture compiles a three-Reel manual target. Production exposes no
  // desired-reserve control and auto refill remains disabled.
  await page.getByRole("button", { name: "Загрузить Reels" }).click();
  await waitCompleted(page, 3);
  await expect(page.locator("#reserve-count")).toHaveCount(0);
  await expect(page.getByText("Автоматически пополнять")).toHaveCount(0);
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.register("/serwist/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    // Production keeps updates waiting for an explicit user decision. The
    // disposable E2E must activate the just-built worker before it verifies
    // its offline media route, otherwise Chromium can retain the shell's
    // earlier waiting worker after a fresh install.
    if (registration.waiting) {
      const controlling = new Promise<void>((resolve) => navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true }));
      registration.waiting.postMessage({ type: "SKIP_WAITING" });
      await controlling;
    }
  });
  await page.reload({ waitUntil: "networkidle" });
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  const initial = await localState(page);
  expect(initial.cacheKeys).toHaveLength(3);

  // Manual download deliberately leaves the user on the dashboard. Enter the
  // feed explicitly before asserting playback-only behavior.
  await page.goto(`${env.origin}/offline`, { waitUntil: "networkidle" });

  // Playback alone is deliberately irrelevant to the viewed lifecycle.
  // Progress, pause and completion signals must not create a row.
  await emitPlaybackSignals(page);
  expect((await localState(page)).records.some((record) => Boolean(record.viewedAt))).toBe(false);

  // Leaving the central card through a confirmed user swipe is the only
  // terminal viewed decision. Make the app offline first so it exercises the
  // durable outbox rather than immediately syncing that decision.
  await page.evaluate(() => {
    Object.defineProperty(Navigator.prototype, "onLine", { configurable: true, get: () => false });
  });
  const beforeSwipe = await activeVideo(page);
  const feed = page.locator("main[aria-label='Video feed']");
  const gesture = page.getByTestId(`reels-gesture-${beforeSwipe.reelId}`);
  const bounds = await gesture.boundingBox();
  if (!bounds) throw new Error("Stage 9 fixture gesture surface is unavailable.");
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height * 0.8);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height * 0.2, { steps: 4 });
  await page.mouse.up();
  await feed.evaluate((element) => element.scrollBy({ top: window.innerHeight, behavior: "instant" }));
  await expect.poll(() => feed.getAttribute("data-committed-item-id")).not.toBe(beforeSwipe.reelId);
  expect((await localState(page)).records.find((record) => record.id === beforeSwipe.reelId)?.viewedAt).toBeTruthy();
  const activeAfterSwipe = await activeVideo(page);

  // Verify that the Service Worker serves a locally cached MP4 with all
  // transport disabled. Playwright's full-offline switch tears down an
  // already in-flight native media request before the Service Worker gets a
  // chance to restart it, so the rest of the interaction blocks API transport
  // only. This exercises the same durable-outbox behavior without that
  // Chromium-only false media failure.
  await context.setOffline(true);
  await assertOfflineMediaRoute(page, activeAfterSwipe.reelId);
  await context.setOffline(false);
  // Keep native playback transport available after the real Service Worker
  // offline assertion. The Chromium harness cancels a native media request
  // when its global offline switch changes. The application itself still sees
  // no network, so its durable outbox path is exercised without a route mock.
  await page.evaluate(() => {
    Object.defineProperty(Navigator.prototype, "onLine", { configurable: true, get: () => false });
  });
  const viewed = (await localState(page)).records.find((record) => Boolean(record.viewedAt));
  expect(viewed).toBeTruthy();
  expect(confirmedViewSyncPosts).toBe(0);
  await page.addInitScript(() => {
    if (sessionStorage.getItem("stage9-fixture-force-offline") === "1") {
      Object.defineProperty(Navigator.prototype, "onLine", { configurable: true, get: () => false });
    }
  });
  await page.evaluate(() => sessionStorage.setItem("stage9-fixture-force-offline", "1"));
  // Reload while the PWA sees itself offline: the durable local record and
  // outbox must be reconstructed without any successful network sync.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(750);
  expect((await localState(page)).records.find((record) => record.id === viewed!.id)).toMatchObject({ viewedAt: viewed!.viewedAt, deletionState: "pending" });

  await page.evaluate(() => {
    sessionStorage.removeItem("stage9-fixture-force-offline");
    Object.defineProperty(Navigator.prototype, "onLine", { configurable: true, get: () => true });
    window.dispatchEvent(new Event("online"));
  });
  await expect.poll(() => confirmedViewSyncPosts, { timeout: 30_000 }).toBeGreaterThanOrEqual(1);
  await expect.poll(async () => (await page.request.get(`${env.origin}/api/instagram/views/status`)).json()).toMatchObject({ confirmed_count: 1 });
  expect((await localState(page)).cacheKeys.some((key) => key.endsWith(`/offline-media/${viewed!.id}`))).toBe(true);

  // Fixture-only compile-time clock: production builds cannot read this value.
  await page.addInitScript(() => {
    (window as Window & { __offlineReelsStage9FixtureNow?: string }).__offlineReelsStage9FixtureNow = "2030-01-01T01:00:00.000Z";
  });
  await page.evaluate(() => {
    (window as Window & { __offlineReelsStage9FixtureNow?: string }).__offlineReelsStage9FixtureNow = "2030-01-01T01:00:00.000Z";
  });
  // A closed iOS PWA cannot run timers. Wake the app under the fixture clock
  // to prove expiry recovery executes at the next launch/foreground.
  await page.reload({ waitUntil: "networkidle" });
  // A reload can initially restore the expired item as active. Its media is
  // intentionally protected while active; move to a different card without a
  // gesture, then expiry must delete immediately and must not create a second
  // viewed decision.
  const expiryFeed = page.locator("main[aria-label='Video feed']");
  if (await expiryFeed.getAttribute("data-committed-item-id") === viewed!.id) {
    await expiryFeed.evaluate((element) => element.scrollBy({ top: window.innerHeight, behavior: "instant" }));
    await expect.poll(() => expiryFeed.getAttribute("data-committed-item-id")).not.toBe(viewed!.id);
  }
  await expect.poll(async () => (await localState(page)).records.find((record) => record.id === viewed!.id)?.deletionState, { timeout: 90_000 }).toBe("deleted");
  const afterDelete = await localState(page);
  expect(afterDelete.cacheKeys.some((key) => key.endsWith(`/offline-media/${viewed!.id}`))).toBe(false);
  expect(afterDelete.records.find((record) => record.id === viewed!.id)).toMatchObject({ viewedAt: viewed!.viewedAt, deletionState: "deleted" });
  await expect.poll(async () => (await localState(page)).records.filter((record) => record.status === "completed").length).toBe(2);
  expect(confirmedCollectionPosts).toBe(1);
  await page.reload({ waitUntil: "networkidle" });
  expect((await localState(page)).records.find((record) => record.id === viewed!.id)?.deletionState).toBe("deleted");

  // The same canonical Reel remains eligible to the separate synthetic account.
  const secondContext = await browser.newContext({
    ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true,
  });
  const second = await pairSecondAccount(secondContext);
  const catalog = await second.request.get(`${env.origin}/api/instagram/catalog`);
  expect(catalog.ok()).toBe(true);
  expect((await catalog.json()).items.map((item: { id: string }) => item.id)).toContain(viewed!.id);
  await secondContext.close();
});
