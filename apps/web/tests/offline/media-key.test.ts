import { describe, expect, it } from "vitest";

import { OfflineStorageError } from "../../lib/offline/errors";
import { getOfflineMediaPath, normalizeVideoId } from "../../lib/offline/media-key";
import { VIDEO_ID_ONE } from "./test-helpers";

describe("offline media keys", () => {
  it("builds a deterministic same-origin path and normalizes UUID case", () => {
    expect(getOfflineMediaPath(VIDEO_ID_ONE.toUpperCase())).toBe(`/offline-media/${VIDEO_ID_ONE}`);
    expect(normalizeVideoId(VIDEO_ID_ONE.toUpperCase())).toBe(VIDEO_ID_ONE);
  });

  it.each(["", "not-a-uuid", `${VIDEO_ID_ONE}/more`, `${VIDEO_ID_ONE}?cursor=x`, "../video", "/offline-media/x"]) (
    "rejects unsafe video id %s",
    (unsafeId) => {
      expect(() => getOfflineMediaPath(unsafeId)).toThrow(OfflineStorageError);
      try {
        getOfflineMediaPath(unsafeId);
      } catch (error) {
        expect(error).toMatchObject({ code: "invalid_video_id" });
      }
    },
  );
});
