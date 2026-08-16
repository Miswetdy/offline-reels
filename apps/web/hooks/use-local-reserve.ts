"use client";

import { useEffect, useState } from "react";
import { getLocalReserveController, type ReserveSnapshot } from "../lib/offline/reserve-controller";
import { AUTO_REFILL_ENABLED } from "../lib/offline/feature-flags";

export function useLocalReserve() {
  const [snapshot, setSnapshot] = useState<ReserveSnapshot | null>(null);
  useEffect(() => {
    const controller = getLocalReserveController();
    const update = () => setSnapshot(controller.getSnapshot());
    const unsubscribe = controller.subscribe(update);
    const trigger = () => { if (AUTO_REFILL_ENABLED) void controller.request("auto"); };
    const onVisibility = () => { if (document.visibilityState === "visible") trigger(); };
    update(); window.addEventListener("online", trigger); window.addEventListener("pageshow", trigger);
    document.addEventListener("visibilitychange", onVisibility); trigger();
    return () => { unsubscribe(); window.removeEventListener("online", trigger); window.removeEventListener("pageshow", trigger); document.removeEventListener("visibilitychange", onVisibility); };
  }, []);
  return {
    snapshot,
    start: () => getLocalReserveController().request("manual"),
    pause: () => getLocalReserveController().pause(),
    cancel: () => getLocalReserveController().cancel(),
    updateSettings: (patch: Parameters<ReturnType<typeof getLocalReserveController>["updateSettings"]>[0]) => getLocalReserveController().updateSettings(patch),
  };
}
