import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { NetworkStatusIndicator } from "../components/network-status-indicator";

describe("NetworkStatusIndicator SSR", () => {
  it("renders without browser APIs", () => {
    expect(() => renderToString(<NetworkStatusIndicator offlineMessage="Офлайн" onlineMessage="Онлайн" />)).not.toThrow();
  });
});
