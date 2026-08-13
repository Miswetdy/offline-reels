"use client";

import { useEffect, useState } from "react";
import { getLocalReserveController, type ReserveSnapshot } from "../lib/offline/reserve-controller";

export function useLocalReserve() {
  const [snapshot, setSnapshot] = useState<ReserveSnapshot | null>(null);
  useEffect(() => {
    const controller = getLocalReserveController();
    const update = () => setSnapshot(controller.getSnapshot());
    const unsubscribe = controller.subscribe(update);
    const trigger = () => void controller.request("auto");
    const onVisibility = () => { if (document.visibilityState === "visible") trigger(); };
    update(); window.addEventListener("online", trigger); window.addEventListener("pageshow", trigger);
    document.addEventListener("visibilitychange", onVisibility); void controller.request("auto");
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
