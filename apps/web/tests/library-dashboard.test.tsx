// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  management: vi.fn(),
  downloads: vi.fn(),
  estimate: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("../hooks/use-management-control", () => ({ useManagementControl: mocks.management }));
vi.mock("../hooks/use-offline-downloads", () => ({ useOfflineDownloads: mocks.downloads }));
vi.mock("../lib/offline/storage", () => ({ getStorageEstimate: mocks.estimate }));

import { LibraryDashboard } from "../components/library-dashboard";
import { ManagementApiError, type ManagementErrorCode } from "../lib/api/management";

const offlineSnapshot = {
  clearing: false,
  completedCount: 0,
  batchProgress: null,
};

const TECHNICAL_UI = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-|shortcode|codec|object[_ -]?key|reason[_ -]?code|\b\d+\s*(?:bytes|байт)|\bHTTP\s*\d{3}\b|stack trace/i;
const RAW_BACKEND_SENTINEL = "FIXTURE_INTERNAL_REASON";

function expectNoTechnicalUi(): void {
  expect(document.body.textContent).not.toMatch(TECHNICAL_UI);
  expect(document.body.textContent).not.toContain(RAW_BACKEND_SENTINEL);
}

function paired(overrides: Record<string, unknown> = {}) {
  return {
    isOnline: true,
    state: "paired",
    error: null,
    status: {
      connection_status: "connected",
      reconnect_required: false,
      active_login: null,
      active_collection: null,
      normalization: { pending: 0, running: 0, completed: 0, failed: 0, cleanup_pending: 0, ready_count: 0 },
      ready_count: 0,
      auto_collection: { enabled: false, target_reserve: 5, scheduler_active: false },
    },
    pair: vi.fn(), disconnectDevice: vi.fn(), connectInstagram: vi.fn(), cancelInstagramLogin: vi.fn(),
    startCollection: vi.fn(), cancelCollection: vi.fn(), normalizationStatus: vi.fn(), refresh: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  mocks.estimate.mockResolvedValue({ usage: 0, quota: 100, available: 100, isAvailable: true });
  mocks.downloads.mockReturnValue({ snapshot: offlineSnapshot, enqueueCatalogAndStart: vi.fn(), cancelBatch: vi.fn(), cancelAndClear: vi.fn() });
  mocks.management.mockReturnValue(paired());
  vi.stubGlobal("confirm", vi.fn(() => true));
});

afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });

describe("LibraryDashboard Stage 7", () => {
  it("shows operator-assisted pairing without persisting or exposing technical identifiers", () => {
    mocks.management.mockReturnValue(paired({ state: "unpaired", status: null }));
    render(<LibraryDashboard />);
    expect(screen.getByRole("heading", { name: "Подключить это устройство" })).toBeInTheDocument();
    expect(screen.getByLabelText("Одноразовый код")).toHaveAttribute("autocomplete", "off");
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });

  it("clears the entered pairing code after a successful exchange", async () => {
    const control = paired({ state: "unpaired", status: null, pair: vi.fn().mockResolvedValue(undefined) });
    mocks.management.mockReturnValue(control);
    render(<LibraryDashboard />);
    const input = screen.getByLabelText("Одноразовый код");
    fireEvent.change(input, { target: { value: "operator-only-code" } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() => expect(control.pair).toHaveBeenCalledWith("operator-only-code"));
    await waitFor(() => expect(input).toHaveValue(""));
  });

  it("renders the connected card, disabled scheduler notice, storage controls, and fixed navigation", async () => {
    render(<LibraryDashboard />);
    expect(screen.getByText("Instagram подключён")).toBeInTheDocument();
    expect(screen.getByText("Автопополнение будет доступно позже")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить Reels" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Очистить библиотеку" })).toBeEnabled();
    expect(screen.getByRole("link", { name: "Главная" })).toHaveAttribute("href", "/");
  });

  it("disables management actions while offline while retaining local library cleanup", () => {
    mocks.management.mockReturnValue(paired({ isOnline: false }));
    render(<LibraryDashboard />);
    expect(screen.getByText("Нет подключения")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить Reels" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Очистить библиотеку" })).toBeEnabled();
  });

  it("keeps the offline dashboard quiet after a stale management error", () => {
    mocks.management.mockReturnValue(paired({
      isOnline: false,
      state: "temporary_error",
      error: { code: "temporary" },
    }));
    render(<LibraryDashboard />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("does not show the initial management check while offline", () => {
    mocks.management.mockReturnValue(paired({ isOnline: false, state: "checking", status: null }));
    render(<LibraryDashboard />);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("offers reconnect rather than raw backend details", () => {
    mocks.management.mockReturnValue(paired({
      error: { code: "reauth_required", detail: `${RAW_BACKEND_SENTINEL} AUTH_REQUIRED` },
      status: { ...paired().status, connection_status: "reauth_required", reconnect_required: true },
    }));
    render(<LibraryDashboard />);
    expect(screen.getByText("Требуется переподключение Instagram")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Переподключить Instagram" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("reauth_required");
    expectNoTechnicalUi();
  });

  it("shows only cancellation while a protected login session is active", () => {
    mocks.management.mockReturnValue(paired({
      status: {
        ...paired().status,
        connection_status: "connecting",
        active_login: { id: "00000000-0000-4000-8000-000000000001", status: "active" },
      },
    }));
    render(<LibraryDashboard />);
    expect(screen.getByText("Подготавливаем безопасный вход…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отменить подключение" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Подключить Instagram" })).not.toBeInTheDocument();
    expectNoTechnicalUi();
  });

  it.each([
    ["invalid pairing", "pairing_invalid", "Код недействителен или срок его действия истёк."],
    ["expired pairing", "pairing_invalid", "Код недействителен или срок его действия истёк."],
    ["rate-limited pairing", "pairing_rate_limited", "Слишком много попыток. Попробуйте позже."],
    ["temporary pairing", "temporary", "Не удалось подключить устройство. Попробуйте позже."],
  ])("redacts backend details for %s", async (_name, code, message) => {
    const error = new ManagementApiError(code as ManagementErrorCode);
    Object.defineProperty(error, "detail", {
      value: `${RAW_BACKEND_SENTINEL} 00000000-0000-4000-8000-000000000001 shortcode codec object_key reason_code HTTP 503 stack trace`,
    });
    const control = paired({
      state: "unpaired",
      status: null,
      pair: vi.fn().mockRejectedValue(error),
    });
    mocks.management.mockReturnValue(control);
    render(<LibraryDashboard />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "operator-code" } });
    fireEvent.click(screen.getAllByRole("button")[0]);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expectNoTechnicalUi();
  });

  it("does not show a pairing alert for a stale non-pairing management error", () => {
    mocks.management.mockReturnValue(paired({
      state: "unpaired",
      status: null,
      error: { code: "temporary", detail: `${RAW_BACKEND_SENTINEL} stale revoke poll` },
    }));
    render(<LibraryDashboard />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expectNoTechnicalUi();
  });

  it("redacts safe connection, pipeline, and cleanup errors", async () => {
    const rawError = new Error(`${RAW_BACKEND_SENTINEL} 00000000-0000-4000-8000-000000000001 object_key HTTP 503`);
    mocks.management.mockReturnValue(paired({
      state: "temporary_error",
      error: { code: "temporary", detail: rawError.message },
      status: { ...paired().status, connection_status: "disconnected" },
    }));
    mocks.downloads.mockReturnValue({
      snapshot: offlineSnapshot,
      enqueueCatalogAndStart: vi.fn(),
      cancelBatch: vi.fn(),
      cancelAndClear: vi.fn().mockRejectedValue(rawError),
    });
    const view = render(<LibraryDashboard />);

    expect(screen.getByRole("alert")).toHaveTextContent("Временная безопасная ошибка. Попробуйте позже.");
    mocks.management.mockReturnValue(paired({
      status: { ...paired().status, connection_status: "disconnected" },
      connectInstagram: vi.fn().mockRejectedValue(rawError),
    }));
    view.rerender(<LibraryDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Подключить Instagram" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Временная безопасная ошибка. Попробуйте позже."));

    mocks.management.mockReturnValue(paired({ startCollection: vi.fn().mockRejectedValue(rawError) }));
    view.rerender(<LibraryDashboard />);
    fireEvent.click(screen.getByRole("button", { name: "Загрузить Reels" }));
    await waitFor(() => expect(screen.getByText("Не удалось завершить загрузку Reels. Попробуйте ещё раз.")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Очистить библиотеку" }));
    await waitFor(() => expect(screen.getByText("Не удалось полностью очистить библиотеку. Попробуйте ещё раз.")).toBeInTheDocument());
    expectNoTechnicalUi();
  });
});
