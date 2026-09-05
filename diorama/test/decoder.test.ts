import { describe, expect, it } from "vitest";
import { decoderPoolSize } from "../src/decoder";

describe("decoderPoolSize", () => {
  it("uses half the logical cores, capped at 4", () => {
    expect(decoderPoolSize(16)).toBe(4);
    expect(decoderPoolSize(8)).toBe(4);
    expect(decoderPoolSize(6)).toBe(3);
    expect(decoderPoolSize(4)).toBe(2);
  });
  it("never drops below one worker", () => {
    expect(decoderPoolSize(1)).toBe(1);
    expect(decoderPoolSize(0)).toBe(1);
    expect(decoderPoolSize(undefined)).toBe(1);
  });
  it("honours a custom cap", () => {
    expect(decoderPoolSize(32, 8)).toBe(8);
  });
});
