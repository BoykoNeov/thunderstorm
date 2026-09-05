import { describe, expect, it } from "vitest";
import { AUTO_DEFAULTS, AutoScaler } from "../src/autoscale";

// feed n identical frames spaced dt ms apart; return the last non-null change
function feed(a: AutoScaler, measured: number, target: number, n: number, t0: number, dt = 16): number | null {
  let last: number | null = null;
  for (let i = 0; i < n; i++) {
    const r = a.update(measured, target, t0 + i * dt);
    if (r !== null) last = r;
  }
  return last;
}

describe("AutoScaler (gpu mode)", () => {
  it("holds full scale when the frame is cheap", () => {
    const a = new AutoScaler("gpu");
    expect(feed(a, 3, 16.67, 60, 0)).toBeNull();
    expect(a.scale).toBe(1);
  });

  it("scales down by sqrt(goal/measured) when overloaded (cost ∝ pixels)", () => {
    const a = new AutoScaler("gpu");
    // goal = 0.8·16.67 = 13.3 ms; measured 40 ms → sqrt(13.3/40) = 0.577 → 0.6
    // (exactly one decision: a constant 40 ms fed past the rate limit would
    // keep retreating, since this fake cost does not fall with the scale)
    const s = feed(a, 40, 16.67, 20, 0);
    expect(s).toBeCloseTo(0.6, 6);
  });

  it("never goes below min or above max", () => {
    const a = new AutoScaler("gpu");
    expect(feed(a, 400, 16.67, 60, 0)).toBe(AUTO_DEFAULTS.min);
    const b = new AutoScaler("gpu", AUTO_DEFAULTS, 0.5);
    feed(b, 0.5, 16.67, 400, 0);
    expect(b.scale).toBe(AUTO_DEFAULTS.max);
  });

  it("scales up gradually (≤ two steps per decision)", () => {
    const a = new AutoScaler("gpu", AUTO_DEFAULTS, 0.5);
    const s = feed(a, 1, 16.67, 25, 0);
    expect(s).toBeCloseTo(0.6, 6);
  });

  it("rate-limits decisions by frames AND time", () => {
    const a = new AutoScaler("gpu");
    // 19 frames: below minFrames → no decision even though overloaded
    expect(feed(a, 40, 16.67, 19, 0)).toBeNull();
    // 20th frame decides
    expect(a.update(40, 16.67, 20 * 16)).not.toBeNull();
    // the next 20 frames come within minInterval ms → no second change
    expect(feed(a, 40, 16.67, 20, 20 * 16 + 1, 10)).toBeNull();
  });

  it("holds inside the deadband", () => {
    const a = new AutoScaler("gpu", AUTO_DEFAULTS, 0.8);
    // goal 13.3; 12 ms is inside (9.3, 13.3] → hold
    expect(feed(a, 12, 16.67, 60, 0)).toBeNull();
    expect(a.scale).toBe(0.8);
  });

  it("ignores non-positive measurements", () => {
    const a = new AutoScaler("gpu");
    expect(feed(a, 0, 16.67, 60, 0)).toBeNull();
    expect(feed(a, NaN, 16.67, 60, 0)).toBeNull();
  });
});

describe("AutoScaler (raf mode)", () => {
  it("retreats when frame spacing exceeds 1.3× the target", () => {
    const a = new AutoScaler("raf");
    const s = feed(a, 33, 16.67, 40, 0, 33); // vsync-missed 30 fps
    expect(s).not.toBeNull();
    expect(s!).toBeLessThan(1);
  });

  it("cannot read headroom from a capped spacing, so it only PROBES up after a quiet interval", () => {
    const a = new AutoScaler("raf", AUTO_DEFAULTS, 0.7);
    // 3 s of exactly-capped frames: no probe yet (5 s interval)
    expect(feed(a, 16.7, 16.67, 180, 0, 16.7)).toBeNull();
    // past 5 s: one step up
    const s = feed(a, 16.7, 16.67, 200, 3000, 16.7);
    expect(s).toBeCloseTo(0.75, 6);
  });

  it("backs the probe interval off when a probe is followed by a retreat", () => {
    const a = new AutoScaler("raf", AUTO_DEFAULTS, 0.7);
    // quiet 6 s → probe to 0.75
    expect(feed(a, 16.7, 16.67, 360, 0, 16.7)).toBeCloseTo(0.75, 6);
    const tProbe = 360 * 16.7;
    // immediately too slow → retreat, and the interval doubles to 10 s
    const r = feed(a, 40, 16.67, 30, tProbe + 600, 40);
    expect(r).not.toBeNull();
    expect(r!).toBeLessThan(0.75);
    // quiet for 7 s: NOT enough any more (interval is now 10 s)
    const tRetreat = tProbe + 600 + 30 * 40;
    expect(feed(a, 16.7, 16.67, 420, tRetreat + 600, 16.7)).toBeNull();
  });
});
