/**
 * The fixture clock is compiled out of ordinary production builds. It is not
 * controlled by URL or storage and must never alter the fixed one-hour delay.
 */
export const isStage9FixtureBuild = process.env.OFFLINE_REELS_BUILD_STAGE9_FIXTURE === "true";

export function lifecycleNow(): string {
  if (isStage9FixtureBuild && typeof window !== "undefined") {
    const value = (window as Window & { __offlineReelsStage9FixtureNow?: string }).__offlineReelsStage9FixtureNow;
    if (typeof value === "string" && Number.isFinite(Date.parse(value))) return value;
  }
  return new Date().toISOString();
}

/**
 * Fixture-only manual acceptance control. This is compile-time excluded from
 * production, has no URL/storage/API input, and advances only the fixture
 * clock so a physical iPhone need not wait one real hour.
 */
export function advanceStage9FixtureClockOneHour(): boolean {
  if (!isStage9FixtureBuild || typeof window === "undefined") return false;
  const next = new Date(Date.parse(lifecycleNow()) + 3_600_000).toISOString();
  (window as Window & { __offlineReelsStage9FixtureNow?: string }).__offlineReelsStage9FixtureNow = next;
  return true;
}
