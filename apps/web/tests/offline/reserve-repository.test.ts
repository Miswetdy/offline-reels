import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LOCAL_RESERVE_STORE, openOfflineDatabase } from "../../lib/offline/db";
import { getLocalReserve, updateLocalReserve } from "../../lib/offline/reserve-repository";
import { resetOfflineDatabase } from "./test-helpers";

beforeEach(async () => { await resetOfflineDatabase(); });
afterEach(async () => { await resetOfflineDatabase(); });

describe("production reserve gate", () => {
  it("ignores a persisted autoRefillEnabled=true and keeps manual settings usable", async () => {
    const initial = await getLocalReserve();
    const database = await openOfflineDatabase();
    await database.put(LOCAL_RESERVE_STORE, { ...initial, autoRefillEnabled: true, pendingCycle: "auto" });
    database.close();

    expect(await getLocalReserve()).toMatchObject({ autoRefillEnabled: false, pendingCycle: "none" });
    expect(await updateLocalReserve({ desiredCount: 10, lowWatermark: 4, autoRefillEnabled: true }))
      .toMatchObject({ desiredCount: 10, lowWatermark: 4, autoRefillEnabled: false, pendingCycle: "none" });
  });
});
