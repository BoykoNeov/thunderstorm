import { describe, expect, it } from "vitest";
import { planRing, RING_BUDGET_BYTES, RING_MAX, RING_MIN, uploadSlabs } from "../src/budget";

const MB = 1024 * 1024;

describe("planRing", () => {
  it("keeps the Phase 1 package at the historical 24 slots / 10 read-ahead", () => {
    // 208×208×72×4 = 12.46 MB → 24 fit in 300 MB
    const p = planRing(208 * 208 * 72 * 4);
    expect(p.slots).toBe(RING_MAX);
    expect(p.readAhead).toBe(10);
    expect(p.bytes).toBeLessThanOrEqual(RING_BUDGET_BYTES);
  });

  it("shrinks the ring for the 540×540×54 supercell brick instead of pinning 1.5 GB", () => {
    const frame = 540 * 540 * 54 * 4; // ≈ 63 MB
    const p = planRing(frame);
    expect(p.slots).toBeLessThan(RING_MAX);
    expect(p.slots).toBeGreaterThanOrEqual(RING_MIN);
    // the floor wins here (4 fit in 300 MB): the floor exists for upload-sync
    // safety, so the budget is deliberately exceeded rather than the ring starved
    expect(p.slots).toBe(RING_MIN);
    expect(p.readAhead).toBe(2);
    expect(p.bytes).toBeLessThan(700 * MB); // ~630 MB — still far from 1.5 GB
  });

  it("read-ahead never exceeds what the ring can hold with slack", () => {
    for (const frame of [1 * MB, 10 * MB, 20 * MB, 40 * MB, 100 * MB]) {
      const p = planRing(frame);
      // protected window (read-ahead + wanted pair + last-bound pair) + 4 rotating
      expect(p.readAhead + 2 + 2 + 4).toBeLessThanOrEqual(p.slots);
      expect(p.readAhead).toBeGreaterThanOrEqual(2);
    }
  });

  it("honours a larger explicit budget", () => {
    const frame = 540 * 540 * 54 * 4;
    const p = planRing(frame, 2048 * MB);
    expect(p.slots).toBe(RING_MAX);
  });

  it("rejects a non-positive brick size", () => {
    expect(() => planRing(0)).toThrow();
  });
});

describe("uploadSlabs", () => {
  it("is a single full-range upload when the brick fits the chunk (today's path)", () => {
    // 208×208×4 B per slice × 72 slices = 12.5 MB < 16 MB
    expect(uploadSlabs(72, 208 * 208 * 4, 16 * MB)).toEqual([[0, 72]]);
  });

  it("splits a 63 MB brick into ~16 MB z-slabs that tile [0, nz) exactly", () => {
    const perSlice = 540 * 540 * 4; // 1.17 MB
    const slabs = uploadSlabs(54, perSlice, 16 * MB);
    expect(slabs.length).toBeGreaterThan(1);
    expect(slabs[0][0]).toBe(0);
    expect(slabs[slabs.length - 1][1]).toBe(54);
    for (let i = 1; i < slabs.length; i++) expect(slabs[i][0]).toBe(slabs[i - 1][1]);
    for (const [z0, z1] of slabs) expect((z1 - z0) * perSlice).toBeLessThanOrEqual(16 * MB);
  });

  it("never emits an empty slab, even when one slice exceeds the chunk", () => {
    const slabs = uploadSlabs(3, 20 * MB, 16 * MB);
    expect(slabs).toEqual([[0, 1], [1, 2], [2, 3]]);
  });

  it("returns nothing for nz = 0", () => {
    expect(uploadSlabs(0, 100, 100)).toEqual([]);
  });
});
