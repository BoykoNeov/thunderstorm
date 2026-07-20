import { describe, expect, it } from "vitest";
import { niceScaleBar } from "../src/scalebar";

describe("niceScaleBar", () => {
  it("picks the largest 1-2-5 distance that fits the allowance", () => {
    // 0.1 km/px over 150 px = 15 km of headroom → 10 km is the biggest rung
    const b = niceScaleBar(0.1, 150);
    expect(b.km).toBe(10);
    expect(b.px).toBeCloseTo(100, 10);
    expect(b.label).toBe("10 km");
  });

  it("never overruns the allowance", () => {
    for (const kmPerPx of [0.002, 0.017, 0.05, 0.4, 3.3, 41]) {
      const b = niceScaleBar(kmPerPx, 150);
      expect(b.px).toBeLessThanOrEqual(150);
      expect(b.px).toBeGreaterThan(0);
    }
  });

  it("only ever returns a 1, 2 or 5 mantissa", () => {
    for (const kmPerPx of [0.001, 0.003, 0.009, 0.02, 0.07, 0.15, 0.9, 6, 22]) {
      const { km } = niceScaleBar(kmPerPx, 150);
      const m = km / 10 ** Math.floor(Math.log10(km));
      expect([1, 2, 5]).toContain(Math.round(m));
    }
  });

  it("uses at least half the allowance, so the rule never reads as a stub", () => {
    // the 1-2-5 ladder's worst gap is 5→10, so the bar always fills ≥ 1/2
    for (const kmPerPx of [0.004, 0.011, 0.09, 0.6, 7]) {
      expect(niceScaleBar(kmPerPx, 150).px).toBeGreaterThanOrEqual(75);
    }
  });

  it("switches to metres below a kilometre", () => {
    expect(niceScaleBar(0.004, 150).label).toBe("500 m");
    expect(niceScaleBar(0.0004, 150).label).toBe("50 m");
  });

  it("degrades to an empty bar rather than NaN geometry", () => {
    for (const bad of [0, -1, NaN, Infinity]) {
      const b = niceScaleBar(bad, 150);
      expect(b).toEqual({ km: 0, px: 0, label: "" });
    }
    expect(niceScaleBar(0.1, 0).px).toBe(0);
  });
});
