/** Stage 8 is compile-time fixture-only; production has no runtime override. */
export const AUTO_REFILL_ENABLED = process.env.OFFLINE_REELS_BUILD_AUTO_REFILL === "true";
