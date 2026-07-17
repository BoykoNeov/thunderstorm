import { describe, expect, it } from "vitest";
import { buildNoise3D, CELLS_G, CELLS_R, NOISE_SIZE, valueNoise3 } from "../src/noise3d";

describe("valueNoise3", () => {
  it("is deterministic and seed-sensitive", () => {
    expect(valueNoise3(1.3, 2.7, 0.4, CELLS_R, 1)).toBe(valueNoise3(1.3, 2.7, 0.4, CELLS_R, 1));
    expect(valueNoise3(1.3, 2.7, 0.4, CELLS_R, 1)).not.toBe(valueNoise3(1.3, 2.7, 0.4, CELLS_R, 2));
  });

  it("stays in [0,1)", () => {
    for (let i = 0; i < 500; i++) {
      const v = valueNoise3(i * 0.173, i * 0.311, i * 0.457, CELLS_G, 42);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("is periodic with the declared cell count (tileability under REPEAT)", () => {
    for (let i = 0; i < 50; i++) {
      const x = i * 0.37;
      const y = i * 0.53;
      const z = i * 0.71;
      expect(valueNoise3(x + CELLS_R, y, z, CELLS_R, 9)).toBeCloseTo(
        valueNoise3(x, y, z, CELLS_R, 9),
        10,
      );
      expect(valueNoise3(x, y + CELLS_R, z + CELLS_R, CELLS_R, 9)).toBeCloseTo(
        valueNoise3(x, y, z, CELLS_R, 9),
        10,
      );
    }
  });

  it("is continuous (no lattice-boundary jumps)", () => {
    const eps = 1e-4;
    for (let i = 1; i < CELLS_R; i++) {
      const a = valueNoise3(i - eps, 1.5, 2.5, CELLS_R, 5);
      const b = valueNoise3(i + eps, 1.5, 2.5, CELLS_R, 5);
      expect(Math.abs(a - b)).toBeLessThan(0.01);
    }
  });
});

describe("buildNoise3D", () => {
  const data = buildNoise3D(1);

  it("has RG8 layout at the declared size", () => {
    expect(data.length).toBe(NOISE_SIZE ** 3 * 2);
  });

  it("both channels have healthy spread, centered mid-range", () => {
    for (const ch of [0, 1]) {
      let min = 255;
      let max = 0;
      let sum = 0;
      const count = NOISE_SIZE ** 3;
      for (let i = 0; i < count; i++) {
        const v = data[i * 2 + ch];
        min = Math.min(min, v);
        max = Math.max(max, v);
        sum += v;
      }
      expect(max - min).toBeGreaterThan(120);
      expect(sum / count).toBeGreaterThan(100);
      expect(sum / count).toBeLessThan(155);
    }
  });

  it("G varies faster than R (it is the finer octave)", () => {
    // mean |difference| between x-adjacent texels on a mid slice
    const n = NOISE_SIZE;
    const grad = [0, 0];
    let count = 0;
    const k = n >> 1;
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n - 1; i++) {
        const o = ((k * n + j) * n + i) * 2;
        grad[0] += Math.abs(data[o] - data[o + 2]);
        grad[1] += Math.abs(data[o + 1] - data[o + 3]);
        count++;
      }
    }
    expect(grad[1] / count).toBeGreaterThan((grad[0] / count) * 2);
  });

  it("wraps seamlessly: edge-to-edge texel step is no bigger than interior steps", () => {
    // compare |f(last texel) - f(first texel)| along x against the mean
    // interior adjacent-texel step — a non-tiling bake would show a cliff
    const n = NOISE_SIZE;
    let wrapDiff = 0;
    let interiorDiff = 0;
    let count = 0;
    for (let k = 0; k < n; k += 7) {
      for (let j = 0; j < n; j += 7) {
        const row = (k * n + j) * n;
        wrapDiff += Math.abs(data[(row + n - 1) * 2] - data[row * 2]);
        for (let i = 0; i < n - 1; i++) interiorDiff += Math.abs(data[(row + i) * 2] - data[(row + i + 1) * 2]);
        count++;
      }
    }
    const meanInterior = interiorDiff / (count * (n - 1));
    const meanWrap = wrapDiff / count;
    expect(meanWrap).toBeLessThan(meanInterior * 3 + 2);
  });
});
