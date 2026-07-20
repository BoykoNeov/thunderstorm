import { describe, expect, it } from "vitest";
import {
  basis,
  clampOrbit,
  clampTarget,
  cross,
  direction,
  dot,
  kmPerPixel,
  norm,
  panTarget,
  type OrbitState,
} from "../src/camera";
import { volumeBox } from "../src/scene";
import type { WebManifest } from "../src/volume";

const S: OrbitState = {
  target: { x: 0, y: 0, z: 5 },
  azimuth: 0.7,
  elevation: 0.5,
  distance: 100,
  fovY: 0.4,
};

describe("orbit camera basis", () => {
  it("is orthonormal", () => {
    const b = basis(S);
    for (const v of [b.right, b.up, b.forward]) {
      expect(Math.hypot(v.x, v.y, v.z)).toBeCloseTo(1, 10);
    }
    expect(dot(b.right, b.up)).toBeCloseTo(0, 10);
    expect(dot(b.right, b.forward)).toBeCloseTo(0, 10);
    expect(dot(b.up, b.forward)).toBeCloseTo(0, 10);
  });

  it("is right-handed (right × up = forward … × -1 for a look-at basis)", () => {
    const b = basis(S);
    const c = cross(b.right, b.up);
    // right/up span the image plane; forward looks down -though the cross:
    expect(c.x).toBeCloseTo(-b.forward.x, 10);
    expect(c.y).toBeCloseTo(-b.forward.y, 10);
    expect(c.z).toBeCloseTo(-b.forward.z, 10);
  });

  it("looks at the target from the set distance", () => {
    const b = basis(S);
    const to = norm({
      x: S.target.x - b.pos.x,
      y: S.target.y - b.pos.y,
      z: S.target.z - b.pos.z,
    });
    expect(to.x).toBeCloseTo(b.forward.x, 10);
    expect(to.y).toBeCloseTo(b.forward.y, 10);
    expect(to.z).toBeCloseTo(b.forward.z, 10);
    const d = Math.hypot(b.pos.x - S.target.x, b.pos.y - S.target.y, b.pos.z - S.target.z);
    expect(d).toBeCloseTo(S.distance, 10);
  });

  it("clamps elevation away from the pole and distance to sane range", () => {
    const c = clampOrbit({ ...S, elevation: 3, distance: 1e6 });
    expect(c.elevation).toBeLessThan(Math.PI / 2);
    expect(c.distance).toBeLessThanOrEqual(500);
  });

  it("direction() matches the orbit offset convention", () => {
    const d = direction(0.7, 0.5);
    const b = basis({ ...S, target: { x: 0, y: 0, z: 0 } });
    expect(b.pos.x / S.distance).toBeCloseTo(d.x, 10);
    expect(b.pos.y / S.distance).toBeCloseTo(d.y, 10);
    expect(b.pos.z / S.distance).toBeCloseTo(d.z, 10);
  });
});

describe("pan (slice 5c: right-drag moves the look-at point)", () => {
  const H = 1000; // viewport height, CSS px

  it("kmPerPixel spans the frustum height over the viewport", () => {
    // the full viewport height covers 2·tan(fov/2)·distance km at the target
    expect(kmPerPixel(S, H) * H).toBeCloseTo(2 * Math.tan(S.fovY / 2) * S.distance, 10);
  });

  it("changes only the target — orbit angles and zoom survive a pan", () => {
    const p = panTarget(S, 120, -45, H);
    expect(p.azimuth).toBe(S.azimuth);
    expect(p.elevation).toBe(S.elevation);
    expect(p.distance).toBe(S.distance);
    expect(p.fovY).toBe(S.fovY);
  });

  it("stays in the image plane (the target never dollies toward the camera)", () => {
    const b = basis(S);
    const p = panTarget(S, 80, 33, H);
    const d = { x: p.target.x - S.target.x, y: p.target.y - S.target.y, z: p.target.z - S.target.z };
    expect(dot(d, b.forward)).toBeCloseTo(0, 10);
  });

  it("moves the scene WITH the cursor, by the distance under it", () => {
    const b = basis(S);
    const dx = 60;
    const p = panTarget(S, dx, 0, H);
    const d = { x: p.target.x - S.target.x, y: p.target.y - S.target.y, z: p.target.z - S.target.z };
    // dragging right walks the target along −right, so the world slides right
    expect(dot(d, b.right)).toBeCloseTo(-dx * kmPerPixel(S, H), 10);
    expect(Math.hypot(d.x, d.y, d.z)).toBeCloseTo(dx * kmPerPixel(S, H), 10);
  });

  it("drags down to rise (grab-the-world), on the simple axis-aligned view", () => {
    const flat: OrbitState = { ...S, azimuth: 0, elevation: 0 };
    expect(panTarget(flat, 0, 50, H).target.z).toBeGreaterThan(flat.target.z);
    expect(panTarget(flat, 0, -50, H).target.z).toBeLessThan(flat.target.z);
  });

  it("pans further per pixel when zoomed out — the scene still tracks the cursor", () => {
    const near = panTarget({ ...S, distance: 20 }, 100, 0, H).target;
    const far = panTarget({ ...S, distance: 200 }, 100, 0, H).target;
    expect(Math.hypot(far.x, far.y)).toBeGreaterThan(Math.hypot(near.x, near.y));
  });

  it("clamps the target into the diorama (ground floor, no flying off the slab)", () => {
    expect(clampTarget({ x: 900, y: -900, z: -5 })).toEqual({ x: 60, y: -60, z: 0 });
    expect(clampTarget({ x: 0, y: 0, z: 999 }).z).toBe(40);
    // a huge drag saturates rather than losing the storm
    const p = panTarget(S, 1e6, 0, H);
    expect(Math.abs(p.target.x)).toBeLessThanOrEqual(60);
    expect(Math.abs(p.target.y)).toBeLessThanOrEqual(60);
    expect(p.target.z).toBeGreaterThanOrEqual(0);
  });
});

describe("volumeBox placement (the ONE m→km conversion site)", () => {
  const man = {
    grid: { nx: 208, ny: 208, nz: 72, voxel_m: 250, origin_m: [-25875, -25875, 125] },
  } as unknown as WebManifest;

  it("reproduces the real package's box: 52×52×18 km centred on the origin", () => {
    const b = volumeBox(man);
    expect(b.min.x).toBeCloseTo(-26, 10);
    expect(b.max.x).toBeCloseTo(26, 10);
    expect(b.min.y).toBeCloseTo(-26, 10);
    expect(b.max.y).toBeCloseTo(26, 10);
    expect(b.min.z).toBeCloseTo(0, 10);
    expect(b.max.z).toBeCloseTo(18, 10);
  });

  it("scale magnifies uniformly: xy about the centre, z about the ground (render-time only)", () => {
    const b = volumeBox(man, 2);
    expect(b.min.z).toBeCloseTo(0, 10);
    expect(b.max.z).toBeCloseTo(36, 10);
    expect(b.min.x).toBeCloseTo(-52, 10); // xy doubles about the centre —
    expect(b.max.x).toBeCloseTo(52, 10); //  proportions stay true
    expect(b.min.y).toBeCloseTo(-52, 10);
    expect(b.max.y).toBeCloseTo(52, 10);
  });
});
