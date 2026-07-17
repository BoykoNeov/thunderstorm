import { describe, expect, it } from "vitest";
import {
  buildStaging,
  FLOATS_PER_VERTEX,
  GROUND_HALF,
  heightAt,
  placeTowns,
  placeTrees,
  WALL_DEPTH,
} from "../src/land";

const SEED = 1337;

describe("land heightfield", () => {
  it("is deterministic for a seed and differs across seeds", () => {
    expect(heightAt(3.2, -1.7, SEED)).toBe(heightAt(3.2, -1.7, SEED));
    const a = Array.from({ length: 32 }, (_, i) => heightAt(i * 2.9 - 40, i * 1.7 - 25, SEED));
    const b = Array.from({ length: 32 }, (_, i) => heightAt(i * 2.9 - 40, i * 1.7 - 25, SEED + 1));
    expect(a).not.toEqual(b);
  });

  it("is continuous countryside: mostly dry land, with lakes below the water sheet", () => {
    let above = 0;
    let total = 0;
    let lo = Infinity;
    const span = GROUND_HALF - 2;
    for (let j = 0; j < 100; j++) {
      for (let i = 0; i < 100; i++) {
        const h = heightAt(-span + (2 * span * i) / 99, -span + (2 * span * j) / 99, SEED);
        total++;
        if (h > 0) above++;
        lo = Math.min(lo, h);
      }
    }
    expect(above / total).toBeGreaterThan(0.55); // land, not an island in a sea
    expect(lo).toBeLessThan(-0.05); // at least one real lake
  });

  it("keeps the rim dry — no water leaking off the slab edge", () => {
    for (let t = 0; t <= 60; t++) {
      const u = -GROUND_HALF + (2 * GROUND_HALF * t) / 60;
      for (const [x, y] of [
        [u, -GROUND_HALF],
        [u, GROUND_HALF],
        [-GROUND_HALF, u],
        [GROUND_HALF, u],
      ]) {
        expect(heightAt(x, y, SEED)).toBeGreaterThan(0.02);
      }
    }
  });

  it("is bounded (toy mountains, shallow lakes)", () => {
    let lo = Infinity;
    let hi = -Infinity;
    for (let j = 0; j < 90; j++) {
      for (let i = 0; i < 90; i++) {
        const h = heightAt(-54 + i * 1.2, -54 + j * 1.2, SEED);
        lo = Math.min(lo, h);
        hi = Math.max(hi, h);
      }
    }
    expect(lo).toBeGreaterThanOrEqual(-0.5);
    // toy summit cap; massifs sit 20+ km off the storm axis, clear of the cloud base
    expect(hi).toBeLessThan(3.1);
  });
});

describe("decorations", () => {
  it("trees: deterministic, plentiful, on dry land inside the slab", () => {
    const trees = placeTrees(SEED);
    expect(placeTrees(SEED)).toEqual(trees);
    expect(trees.length).toBeGreaterThan(400);
    for (const t of trees) {
      expect(Math.max(Math.abs(t.x), Math.abs(t.y))).toBeLessThan(GROUND_HALF - 1);
      expect(t.z).toBeGreaterThan(0); // never planted in a lake
      expect(t.size).toBeGreaterThan(0.2);
      expect(t.size).toBeLessThan(0.7);
    }
  });

  it("towns: deterministic, several, spaced apart, houses clustered on dry land", () => {
    const towns = placeTowns(SEED);
    expect(placeTowns(SEED)).toEqual(towns);
    expect(towns.length).toBeGreaterThanOrEqual(3);
    for (let a = 0; a < towns.length; a++) {
      expect(towns[a].houses.length).toBeGreaterThanOrEqual(6);
      for (const h of towns[a].houses) {
        expect(Math.hypot(h.x - towns[a].x, h.y - towns[a].y)).toBeLessThan(3);
        expect(h.z).toBeGreaterThan(0);
      }
      for (let b = a + 1; b < towns.length; b++) {
        const d = Math.hypot(towns[a].x - towns[b].x, towns[a].y - towns[b].y);
        expect(d).toBeGreaterThanOrEqual(14 - 1e-9);
      }
    }
  });
});

describe("staging mesh", () => {
  const mesh = buildStaging(SEED);

  it("is deterministic", () => {
    const again = buildStaging(SEED);
    expect(again.vertexCount).toBe(mesh.vertexCount);
    expect(again.data.length).toBe(mesh.data.length);
    // plain loop: toEqual's deep diff is O(minutes) on a ~6M-element array
    let mismatch = -1;
    for (let i = 0; i < mesh.data.length; i++) {
      if (again.data[i] !== mesh.data[i]) {
        mismatch = i;
        break;
      }
    }
    expect(mismatch).toBe(-1);
  });

  it("has sane structure: triangle soup, interleaved stride, no NaNs", () => {
    expect(mesh.vertexCount % 3).toBe(0);
    expect(mesh.vertexCount).toBeGreaterThan(100000); // full slab actually meshed
    expect(mesh.data.length).toBe(mesh.vertexCount * FLOATS_PER_VERTEX);
    expect(mesh.data.every((v) => Number.isFinite(v))).toBe(true);
  });

  it("has unit face normals and colors in [0,1]", () => {
    // accumulate + assert once: per-sample expect() calls are slow enough to
    // blow the test timeout on a loaded machine
    let badNormals = 0;
    let badColors = 0;
    for (let v = 0; v < mesh.vertexCount; v += 97) {
      const o = v * FLOATS_PER_VERTEX;
      const nl = Math.hypot(mesh.data[o + 3], mesh.data[o + 4], mesh.data[o + 5]);
      if (Math.abs(nl - 1) > 1e-4) badNormals++;
      for (let c = 6; c < 9; c++) {
        if (mesh.data[o + c] < 0 || mesh.data[o + c] > 1) badColors++;
      }
    }
    expect(badNormals).toBe(0);
    expect(badColors).toBe(0);
  });

  it("stays inside the slab footprint and depth", () => {
    let mMax = 0;
    let zMin = 0;
    let zMax = 0;
    for (let v = 0; v < mesh.vertexCount; v++) {
      const o = v * FLOATS_PER_VERTEX;
      mMax = Math.max(mMax, Math.abs(mesh.data[o]), Math.abs(mesh.data[o + 1]));
      zMin = Math.min(zMin, mesh.data[o + 2]);
      zMax = Math.max(zMax, mesh.data[o + 2]);
    }
    expect(mMax).toBeLessThanOrEqual(GROUND_HALF + 1e-4);
    expect(zMin).toBeGreaterThanOrEqual(-WALL_DEPTH - 1e-4);
    expect(zMax).toBeLessThan(3.5); // terrain + tallest tree stays toy scale
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
    expect(waterFlat).toBe(true); // water sheet at z=0, normal +z
  });

  it("wall normals point outward (no inside-out base)", () => {
    // wall vertices are the land verts on the slab's side planes below z=0
    let checked = 0;
    let worst = 1;
    for (let v = 0; v < mesh.vertexCount; v++) {
      const o = v * FLOATS_PER_VERTEX;
      if (mesh.data[o + 9] > 0.5 || mesh.data[o + 2] >= -1e-6) continue;
      const x = mesh.data[o];
      const y = mesh.data[o + 1];
      if (Math.max(Math.abs(x), Math.abs(y)) < GROUND_HALF - 0.01) continue;
      checked++;
      // outward = the axis direction of whichever side plane(s) the vert is on
      let outDot = -1;
      if (Math.abs(x) > GROUND_HALF - 0.01) {
        outDot = Math.max(outDot, mesh.data[o + 3] * Math.sign(x));
      }
      if (Math.abs(y) > GROUND_HALF - 0.01) {
        outDot = Math.max(outDot, mesh.data[o + 4] * Math.sign(y));
      }
      worst = Math.min(worst, outDot);
    }
    expect(checked).toBeGreaterThan(0);
    expect(worst).toBeGreaterThan(0.9);
  });
});
