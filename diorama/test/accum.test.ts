import { describe, expect, it } from "vitest";
import { ACC_CAP, jitterSeq, nextCount, sameView, type ViewKey } from "../src/accum";

const key = (over: Partial<ViewKey> = {}): ViewKey => ({
  az: 1, el: 2, dist: 3, fovY: 4, targetZ: 5, fa: 6, fb: 7, mix: 0.5, ...over,
});

describe("nextCount", () => {
  it("resets to 1 when the view changed, regardless of the previous count", () => {
    expect(nextCount(false, 40)).toBe(1);
    expect(nextCount(false, 0)).toBe(1);
  });

  it("counts up while the view holds", () => {
    expect(nextCount(true, 1)).toBe(2);
    expect(nextCount(true, 10)).toBe(11);
  });

  it("saturates at the cap", () => {
    expect(nextCount(true, ACC_CAP)).toBe(ACC_CAP);
    expect(nextCount(true, ACC_CAP + 5)).toBe(ACC_CAP);
  });
});

describe("jitterSeq", () => {
  it("starts at 0 (pass 0 reproduces the un-jittered image)", () => {
    expect(jitterSeq(0)).toBe(0);
  });

  it("is the golden-ratio sequence", () => {
    expect(jitterSeq(1)).toBeCloseTo(0.618, 3);
  });

  it("stays in [0,1) for a long run", () => {
    for (let n = 0; n <= 200; n++) {
      const j = jitterSeq(n);
      expect(j).toBeGreaterThanOrEqual(0);
      expect(j).toBeLessThan(1);
    }
  });
});

describe("sameView", () => {
  it("is false against a null history (first frame always restarts)", () => {
    expect(sameView(null, key())).toBe(false);
  });

  it("is true for identical keys", () => {
    expect(sameView(key(), key())).toBe(true);
  });

  it("is false when any single field differs", () => {
    const fields: (keyof ViewKey)[] = ["az", "el", "dist", "fovY", "targetZ", "fa", "fb", "mix"];
    for (const f of fields) {
      expect(sameView(key(), key({ [f]: 999 }))).toBe(false);
    }
  });
});
