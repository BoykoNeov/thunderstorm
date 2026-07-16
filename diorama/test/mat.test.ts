import { describe, expect, it } from "vitest";
import { basis, type OrbitState } from "../src/camera";
import { linearizeDepth, multiply, perspective, project, view } from "../src/mat";

const S: OrbitState = {
  target: { x: 3, y: -2, z: 4 },
  azimuth: 0.9,
  elevation: 0.6,
  distance: 80,
  fovY: 0.4,
};
const NEAR = 0.2;
const FAR = 700;
const ASPECT = 16 / 9;

describe("mesh-pass projection vs raymarch ray generation", () => {
  const cam = basis(S);
  const vp = multiply(perspective(S.fovY, ASPECT, NEAR, FAR), view(cam));

  it("projects the orbit target to the screen centre", () => {
    const c = project(vp, S.target);
    expect(c.x).toBeCloseTo(0, 6);
    expect(c.y).toBeCloseTo(0, 6);
  });

  it("agrees with the shader's ray generation for an off-centre point", () => {
    // Build a world point the way the composite shader builds rays:
    // rd = normalize(fwd + tan(fov/2) * (ndc.x*aspect*right + ndc.y*up))
    const ndcX = 0.37;
    const ndcY = -0.52;
    const ft = Math.tan(S.fovY / 2);
    const rd = {
      x: cam.forward.x + ft * (ndcX * ASPECT * cam.right.x + ndcY * cam.up.x),
      y: cam.forward.y + ft * (ndcX * ASPECT * cam.right.y + ndcY * cam.up.y),
      z: cam.forward.z + ft * (ndcX * ASPECT * cam.right.z + ndcY * cam.up.z),
    };
    const t = 55; // any distance along the (unnormalized) ray
    const p = { x: cam.pos.x + rd.x * t, y: cam.pos.y + rd.y * t, z: cam.pos.z + rd.z * t };
    const c = project(vp, p);
    // the matrix pass must land the point on the same pixel the ray came from
    expect(c.x).toBeCloseTo(ndcX, 6);
    expect(c.y).toBeCloseTo(ndcY, 6);
  });

  it("round-trips depth-buffer values back to ray distance (composite contract)", () => {
    // place a point at known distance along a normalized ray, project it,
    // convert clip z to the [0,1] depth-buffer value, then reconstruct
    const ndcX = -0.6;
    const ndcY = 0.25;
    const ft = Math.tan(S.fovY / 2);
    const raw = {
      x: cam.forward.x + ft * (ndcX * ASPECT * cam.right.x + ndcY * cam.up.x),
      y: cam.forward.y + ft * (ndcX * ASPECT * cam.right.y + ndcY * cam.up.y),
      z: cam.forward.z + ft * (ndcX * ASPECT * cam.right.z + ndcY * cam.up.z),
    };
    const l = Math.hypot(raw.x, raw.y, raw.z);
    const rd = { x: raw.x / l, y: raw.y / l, z: raw.z / l };
    const tTrue = 120;
    const p = {
      x: cam.pos.x + rd.x * tTrue,
      y: cam.pos.y + rd.y * tTrue,
      z: cam.pos.z + rd.z * tTrue,
    };
    const c = project(vp, p);
    const depthBuf = c.z * 0.5 + 0.5;
    const ze = linearizeDepth(depthBuf, NEAR, FAR);
    const cosF = rd.x * cam.forward.x + rd.y * cam.forward.y + rd.z * cam.forward.z;
    // matrices are Float32Array (GPU layout), so allow fp32 rounding: the
    // reconstruction must be good to ~2 m at 120 km — far below one voxel
    expect(Math.abs(ze / cosF - tTrue)).toBeLessThan(0.005);
  });

  it("linearizeDepth hits the planes exactly", () => {
    expect(linearizeDepth(0, NEAR, FAR)).toBeCloseTo(NEAR, 8);
    expect(linearizeDepth(1, NEAR, FAR)).toBeCloseTo(FAR, 3);
  });
});
