import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  clearMediaCache: vi.fn(),
  deleteCachedVideo: vi.fn(),
  clearOfflineVideos: vi.fn(),
  deleteOfflineVideo: vi.fn(),
  reconcileOfflineLibrary: vi.fn(),
}));

vi.mock("../../lib/offline/media-cache", () => ({
  clearMediaCache: mocks.clearMediaCache,
  deleteCachedVideo: mocks.deleteCachedVideo,
}));
vi.mock("../../lib/offline/repository", () => ({
  clearOfflineVideos: mocks.clearOfflineVideos,
  deleteOfflineVideo: mocks.deleteOfflineVideo,
}));
vi.mock("../../lib/offline/reconciliation", () => ({
  reconcileOfflineLibrary: mocks.reconcileOfflineLibrary,
}));

import { clearOfflineLibrary, deleteOfflineLibraryVideo } from "../../lib/offline/library-management";
import { VIDEO_ID_ONE } from "./test-helpers";

describe("offline library management recovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reconciles after metadata deletion fails following cache deletion", async () => {
    mocks.deleteCachedVideo.mockResolvedValue(true);
    mocks.deleteOfflineVideo.mockRejectedValue(new DOMException("blocked", "SecurityError"));
    mocks.reconcileOfflineLibrary.mockResolvedValue({});

    await expect(deleteOfflineLibraryVideo(VIDEO_ID_ONE)).rejects.toMatchObject({ code: "browser_storage_unavailable" });

    expect(mocks.deleteCachedVideo).toHaveBeenCalledWith(VIDEO_ID_ONE);
    expect(mocks.deleteOfflineVideo).toHaveBeenCalledWith(VIDEO_ID_ONE);
    expect(mocks.reconcileOfflineLibrary).toHaveBeenCalledOnce();
  });

  it("reconciles after metadata clear fails without touching any shell cache API", async () => {
    mocks.clearMediaCache.mockResolvedValue(true);
    mocks.clearOfflineVideos.mockRejectedValue(new DOMException("blocked", "SecurityError"));
    mocks.reconcileOfflineLibrary.mockResolvedValue({});

    await expect(clearOfflineLibrary()).rejects.toMatchObject({ code: "browser_storage_unavailable" });

    expect(mocks.clearMediaCache).toHaveBeenCalledOnce();
    expect(mocks.clearOfflineVideos).toHaveBeenCalledOnce();
    expect(mocks.reconcileOfflineLibrary).toHaveBeenCalledOnce();
  });
});
