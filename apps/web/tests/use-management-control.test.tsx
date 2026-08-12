// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getInstagramStatus: vi.fn(),
  hasManagementCsrf: vi.fn(),
  revokeManagementSession: vi.fn(),
}));

vi.mock("../hooks/use-network-status", () => ({ useNetworkStatus: () => true }));
vi.mock("../lib/api/management", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api/management")>();
  return {
    ...actual,
    getInstagramStatus: mocks.getInstagramStatus,
    hasManagementCsrf: mocks.hasManagementCsrf,
    revokeManagementSession: mocks.revokeManagementSession,
  };
});

import { ManagementApiError } from "../lib/api/management";
import { useManagementControl } from "../hooks/use-management-control";

function ControlProbe() {
  const control = useManagementControl();
  return (
    <>
      <output data-testid="state">{control.state}</output>
      <output data-testid="error">{control.error?.code ?? ""}</output>
      <button type="button" onClick={() => void control.disconnectDevice()}>disconnect</button>
    </>
  );
}

describe("useManagementControl revoke", () => {
  beforeEach(() => {
    mocks.hasManagementCsrf.mockReturnValue(true);
    mocks.getInstagramStatus.mockRejectedValue(new ManagementApiError("temporary"));
    mocks.revokeManagementSession.mockResolvedValue(undefined);
  });

  afterEach(() => vi.clearAllMocks());

  it("clears a stale polling failure after the device is revoked", async () => {
    render(<ControlProbe />);
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("temporary_error"));
    expect(screen.getByTestId("error")).toHaveTextContent("temporary");

    fireEvent.click(screen.getByRole("button", { name: "disconnect" }));

    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("unpaired"));
    expect(screen.getByTestId("error")).toHaveTextContent("");
  });
});
