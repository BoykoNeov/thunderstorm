import { describe, expect, it } from "vitest";
import {
  buildPrecipInstances,
  cycleFade,
  fallCycle,
  FLOATS_PER_INSTANCE,
  HAIL,
  RAIN,
} from "../src/precip";

const SEED = 1337;

describe("precip instance buffer", () => {
  it("is deterministic for a seed and differs across seeds", () => {
    const a = buildPrecipInstances(512, SEED);
    expect(buildPrecipInstances(512, SEED)).toEqual(a);
    expect(buildPrecipInstances(512, SEED + 1)).not.toEqual(a);
  });

  it("has the declared stride and every value in [0,1)", () => {
    const a = buildPrecipInstances(1000, SEED);
    expect(a.length).toBe(1000 * FLOATS_PER_INSTANCE);
    for (const v of a) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("spawnFrac < 1 confines spawn to a centred disk, uniform by area", () => {
    const frac = 0.35;
    const a = buildPrecipInstances(4096, SEED, frac);
    let inner = 0;
    for (let i = 0; i < 4096; i++) {
      const du = a[i * FLOATS_PER_INSTANCE] - 0.5;
      const dv = a[i * FLOATS_PER_INSTANCE + 1] - 0.5;
      const r = Math.hypot(du, dv);
      expect(r).toBeLessThanOrEqual(frac / 2 + 1e-6);
      if (r < frac / 4) inner++; // quarter of the area → ~quarter of the points
    }
    expect(inner / 4096).toBeGreaterThan(0.2);
    expect(inner / 4096).toBeLessThan(0.3);
  });

  it("spawns spread out, not clumped (footprint coverage)", () => {
    // 16 buckets per axis over (u, v); with 4096 instances every bucket
    // should see traffic — a broken hash would leave holes
    const a = buildPrecipInstances(4096, SEED);
    const hits = new Set<number>();
    for (let i = 0; i < 4096; i++) {
      const u = a[i * FLOATS_PER_INSTANCE];
      const v = a[i * FLOATS_PER_INSTANCE + 1];
      hits.add(Math.floor(u * 16) * 16 + Math.floor(v * 16));
    }
    expect(hits.size).toBe(256);
  });
});

describe("fall cycle", () => {
  const zTop = 2.4;
  const zBot = 0;
  const speed = 1.1;

  it("stays within [zBot, zTop] for arbitrary times and phases", () => {
    for (let i = 0; i < 200; i++) {
      const { z, f } = fallCycle(i * 7.31, (i * 0.137) % 1, speed, zTop, zBot);
      expect(z).toBeGreaterThanOrEqual(zBot);
      expect(z).toBeLessThanOrEqual(zTop);
      expect(f).toBeGreaterThanOrEqual(0);
      expect(f).toBeLessThan(1);
    }
  });

  it("descends at the given speed between wraps", () => {
    const t0 = 0.2;
    const dt = 0.05;
    const a = fallCycle(t0, 0.3, speed, zTop, zBot);
    const b = fallCycle(t0 + dt, 0.3, speed, zTop, zBot);
    expect(a.z - b.z).toBeCloseTo(speed * dt, 6);
  });

  it("wraps with period span/speed and lands back where it started", () => {
    const period = (zTop - zBot) / speed;
    const a = fallCycle(1.0, 0.7, speed, zTop, zBot);
    const b = fallCycle(1.0 + period, 0.7, speed, zTop, zBot);
    expect(b.z).toBeCloseTo(a.z, 6);
    expect(b.f).toBeCloseTo(a.f, 6);
  });

  it("is well-defined for negative time (phase subtraction stays in range)", () => {
    const { z, f } = fallCycle(-123.4, 0.05, speed, zTop, zBot);
    expect(z).toBeGreaterThanOrEqual(zBot);
    expect(z).toBeLessThanOrEqual(zTop);
    expect(f).toBeGreaterThanOrEqual(0);
    expect(f).toBeLessThan(1);
  });
});

describe("cycle fade", () => {
  it("is zero at both cycle ends and full in the middle", () => {
    expect(cycleFade(0)).toBe(0);
    expect(cycleFade(1)).toBe(0);
    expect(cycleFade(0.5)).toBe(1);
  });

  it("ramps monotonically at the ends", () => {
    expect(cycleFade(0.02)).toBeLessThan(cycleFade(0.06));
    expect(cycleFade(0.97)).toBeLessThan(cycleFade(0.9));
  });
});

describe("specs", () => {
  it("rain and hail gate on the channels the manifest ships", () => {
    expect(RAIN.gateChannel).toBe("rain");
    expect(HAIL.gateChannel).toBe("graupelhail");
  });

  it("hail falls faster than rain and is sparser (design §5.3)", () => {
    expect(HAIL.fallSpeed).toBeGreaterThan(RAIN.fallSpeed);
    expect(HAIL.count).toBeLessThan(RAIN.count);
  });
});
