import { describe, expect, it } from "vitest";
import {
  buildStaging,
  FLOATS_PER_VERTEX,
  heightAt,
  PLATTER_RADIUS,
  WALL_DEPTH,
} from "../src/island";

const SEED = 1337;

describe("island heightfield", () => {
  it("is deterministic for a seed and differs across seeds", () => {
    expect(heightAt(3.2, -1.7, SEED)).toBe(heightAt(3.2, -1.7, SEED));
    const a = Array.from({ length: 32 }, (_, i) => heightAt(i * 1.3 - 8, i * 0.7 - 5, SEED));
    const b = Array.from({ length: 32 }, (_, i) => heightAt(i * 1.3 - 8, i * 0.7 - 5, SEED + 1));
    expect(a).not.toEqual(b);
  });

  it("rises above the sea at the island core and stays sea far away", () => {
    expect(heightAt(4.5, -3.5, SEED)).toBeGreaterThan(0.1);
    // beyond the noise reach the field is pure sea
    for (const [x, y] of [[30, 0], [0, 30], [-25, -25]]) {
      expect(heightAt(x, y, SEED)).toBeLessThan(0);
    }
  });

  it("is bounded (toy mountains, shallow toy seabed)", () => {
    let lo = Infinity;
    let hi = -Infinity;
    for (let j = 0; j < 80; j++) {
      for (let i = 0; i < 80; i++) {
        const h = heightAt(-20 + i * 0.5, -20 + j * 0.5, SEED);
        lo = Math.min(lo, h);
        hi = Math.max(hi, h);
      }
    }
    expect(lo).toBeGreaterThanOrEqual(-0.55);
    expect(hi).toBeLessThan(2.0); // staging must stay well under the ~1–2 km cloud base
  });
});

describe("staging mesh", () => {
  const mesh = buildStaging(SEED);

  it("is deterministic", () => {
    const again = buildStaging(SEED);
    expect(again.vertexCount).toBe(mesh.vertexCount);
    expect(again.data).toEqual(mesh.data);
  });

  it("has sane structure: triangle soup, interleaved stride, no NaNs", () => {
    expect(mesh.vertexCount % 3).toBe(0);
    expect(mesh.vertexCount).toBeGreaterThan(3000); // island actually meshed
    expect(mesh.data.length).toBe(mesh.vertexCount * FLOATS_PER_VERTEX);
    expect(mesh.data.every((v) => Number.isFinite(v))).toBe(true);
  });

  it("has unit face normals and colors in [0,1]", () => {
    for (let v = 0; v < mesh.vertexCount; v += 97) {
      const o = v * FLOATS_PER_VERTEX;
      const nl = Math.hypot(mesh.data[o + 3], mesh.data[o + 4], mesh.data[o + 5]);
      expect(nl).toBeCloseTo(1, 5);
      for (let c = 6; c < 9; c++) {
        expect(mesh.data[o + c]).toBeGreaterThanOrEqual(0);
        expect(mesh.data[o + c]).toBeLessThanOrEqual(1);
      }
    }
  });

  it("stays inside the platter footprint and depth", () => {
    let rMax = 0;
    let zMin = 0;
    for (let v = 0; v < mesh.vertexCount; v++) {
      const o = v * FLOATS_PER_VERTEX;
      rMax = Math.max(rMax, Math.hypot(mesh.data[o], mesh.data[o + 1]));
      zMin = Math.min(zMin, mesh.data[o + 2]);
    }
    expect(rMax).toBeLessThanOrEqual(PLATTER_RADIUS + 1e-4);
    expect(zMin).toBeGreaterThanOrEqual(-WALL_DEPTH - 1e-4);
  });

  it("contains both materials: land (0) and water (1), and water is flat at z=0", () => {
    let land = 0;
    let water = 0;
    let waterFlat = true;
    for (let v = 0; v < mesh.vertexCount; v++) {
      const o = v * FLOATS_PER_VERTEX;
      if (mesh.data[o + 9] > 0.5) {
        water++;
        if (mesh.data[o + 2] !== 0 || Math.abs(mesh.data[o + 5] - 1) > 1e-6) waterFlat = false;
      } else {
        land++;
      }
    }
    expect(land).toBeGreaterThan(0);
    expect(water).toBeGreaterThan(0);
    expect(waterFlat).toBe(true); // water disk at z=0, normal +z
  });

  it("wall normals point outward (no inside-out base)", () => {
    // wall vertices are the land verts at r ≈ PLATTER_RADIUS below z=0
    let checked = 0;
    let worst = 1;
    for (let v = 0; v < mesh.vertexCount; v++) {
      const o = v * FLOATS_PER_VERTEX;
      if (mesh.data[o + 9] < 0.5 && mesh.data[o + 2] < -1e-6) {
        const r = Math.hypot(mesh.data[o], mesh.data[o + 1]);
        if (r > PLATTER_RADIUS - 0.01) {
          checked++;
          const outDot =
            (mesh.data[o] / r) * mesh.data[o + 3] + (mesh.data[o + 1] / r) * mesh.data[o + 4];
          worst = Math.min(worst, outDot);
        }
      }
    }
    expect(checked).toBeGreaterThan(0);
    expect(worst).toBeGreaterThan(0.9);
  });
});
