import { describe, expect, it } from "vitest";
import { basis, clampOrbit, cross, direction, dot, norm, type OrbitState } from "../src/camera";
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

  it("z-exaggeration stretches about the ground only (charter: render-time only)", () => {
    const b = volumeBox(man, 2);
    expect(b.min.z).toBeCloseTo(0, 10);
    expect(b.max.z).toBeCloseTo(36, 10);
    expect(b.max.x).toBeCloseTo(26, 10); // horizontal untouched
  });
});
