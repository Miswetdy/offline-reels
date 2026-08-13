import { expect, test, type Page } from "@playwright/test";

const fixtureOrigin = process.env.STAGE8_E2E_ORIGIN;
const fixturePairingSecret = process.env.STAGE8_E2E_PAIRING_SECRET;

function fixtureEnvironment(): { origin: string; pairingSecret: string } {
  if (!fixtureOrigin || !fixturePairingSecret) throw new Error("Stage 8 fixture environment is required.");
  return { origin: fixtureOrigin, pairingSecret: fixturePairingSecret };
}

async function localState(page: Page) {
  return page.evaluate(async () => {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("offline-reels");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const records = await new Promise<Array<{ id: string; status: string }>>((resolve, reject) => {
      const request = database.transaction("offlineVideos", "readonly").objectStore("offlineVideos").getAll();
      request.onsuccess = () => resolve(request.result as Array<{ id: string; status: string }>);
      request.onerror = () => reject(request.error);
    });
    database.close();
    const cache = await caches.open("offline-reels-media-v1");
    const cacheKeys = await cache.keys();
    return { records, cacheKeys: cacheKeys.map((item) => item.url) };
  });
}

async function clearLibrary(page: Page) {
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Очистить библиотеку" }).click();
  await expect.poll(async () => (await localState(page)).records.length).toBe(0);
}

async function waitForCompleted(page: Page, count: number) {
  await expect.poll(async () => {
    const local = await localState(page);
    return local.records.filter((record) => record.status === "completed").length;
  }, { timeout: 90_000 }).toBe(count);
}

test("Stage 8 mobile local reserve lifecycle", async ({ page, context }) => {
  const { origin, pairingSecret } = fixtureEnvironment();
  const responseHeaders = new Map<string, string | undefined>();
  let collectionPosts = 0;
  page.on("response", (response) => {
    const url = response.url();
    if (url.includes("/api/instagram/collection-runs") && response.request().method() === "POST") collectionPosts += 1;
    if (url.includes("/api/management/") || url.includes("/api/reserve/") || url.includes("/api/instagram/")) {
      responseHeaders.set(url, response.headers()["cache-control"]);
    }
  });

  await page.goto(origin, { waitUntil: "networkidle" });
  await page.locator("#pairing-code").fill(pairingSecret);
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("heading", { name: "Instagram" })).toBeVisible();
  await page.getByRole("button", { name: "Подключить Instagram" }).click();
  await page.waitForURL(`${origin}/`, { timeout: 30_000 });
  await expect(page.getByText("Instagram подключён")).toBeVisible({ timeout: 30_000 });

  await page.locator("#reserve-count").selectOption("10");
  await page.getByLabel("Автоматически пополнять").check();
  await waitForCompleted(page, 10);
  await expect(page.getByText("Запас готов")).toBeVisible();
  expect(collectionPosts).toBe(1);
  const initial = await localState(page);
  expect(new Set(initial.records.map((record) => record.id)).size).toBe(10);
  expect(initial.cacheKeys).toHaveLength(10);

  const postsBeforeReload = collectionPosts;
  await page.reload({ waitUntil: "networkidle" });
  await waitForCompleted(page, 10);
  expect(collectionPosts).toBe(postsBeforeReload);
  const visible = await page.locator("body").innerText();
  expect(visible).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/i);
  expect(visible).not.toMatch(/object[_ -]?key|reason[_ -]?code|shortcode|sha(?:256)?/i);
  expect([...responseHeaders.keys()].some((url) => url.includes("/api/management/"))).toBe(true);
  expect([...responseHeaders.keys()].some((url) => url.includes("/api/reserve/"))).toBe(true);
  expect([...responseHeaders.values()].filter((value) => value !== undefined)).not.toContainEqual(expect.not.stringContaining("no-store"));

  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/serwist/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
  });
  await page.reload({ waitUntil: "networkidle" });
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
  await context.setOffline(true);
  await page.goto(`${origin}/offline`, { waitUntil: "domcontentloaded", timeout: 15_000 });
  await expect(page.locator("video").first()).toBeVisible({ timeout: 30_000 });
  await context.setOffline(false);

  await page.goto(origin, { waitUntil: "networkidle" });
  await clearLibrary(page);
  await page.getByLabel("Автоматически пополнять").uncheck();
  await page.addInitScript(() => {
    const storage = navigator.storage;
    const realEstimate = storage.estimate.bind(storage);
    Object.defineProperty(storage, "estimate", { configurable: true, value: async () => {
      const forced = (window as Window & { __stage8Quota?: { usage: number; quota: number } }).__stage8Quota;
      return forced ?? realEstimate();
    } });
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.evaluate(() => { (window as Window & { __stage8Quota?: { usage: number; quota: number } }).__stage8Quota = { usage: 95, quota: 100 }; });
  await page.getByLabel("Автоматически пополнять").check();
  await expect(page.getByText("Недостаточно места")).toBeVisible();
  expect(collectionPosts).toBe(postsBeforeReload);

  await page.evaluate(() => {
    (window as Window & { __stage8Quota?: { usage: number; quota: number } }).__stage8Quota = { usage: 0, quota: 100_000_000 };
    window.dispatchEvent(new Event("online"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await waitForCompleted(page, 10);
  await expect(page.getByText("Запас готов")).toBeVisible();

  await clearLibrary(page);
  await page.getByLabel("Автоматически пополнять").uncheck();
  await page.route(/\/api\/videos\/[^/]+\/stream$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 450));
    await route.continue();
  });
  await page.getByLabel("Автоматически пополнять").check();
  await waitForCompleted(page, 1);
  await page.getByRole("button", { name: "Безопасно отменить" }).click();
  await expect(page.getByText("Автопополнение приостановлено")).toBeVisible();
  const cancelled = await localState(page);
  expect(cancelled.records.filter((record) => record.status === "completed")).toHaveLength(1);
  expect(cancelled.cacheKeys).toHaveLength(1);
  await page.unroute(/\/api\/videos\/[^/]+\/stream$/);

  await page.getByRole("button", { name: "Возобновить" }).click();
  await waitForCompleted(page, 10);
  const postsBeforeSatisfied = collectionPosts;
  await page.reload({ waitUntil: "networkidle" });
  await waitForCompleted(page, 10);
  expect(collectionPosts).toBe(postsBeforeSatisfied);
});
