// Minimal 4×4 matrix math for the staging mesh (G-buffer) pass. Column-major
// Float32Array, the layout uniformMatrix4fv expects. The volume pass generates
// rays directly from the camera basis; this projection MUST stay consistent
// with that ray generation — test/mat.test.ts projects points both ways and
// asserts they agree, including the depth-buffer → ray-distance round trip the
// composite shader relies on.

import type { CameraBasis } from "./camera";
import { dot } from "./camera";
import type { Vec3 } from "./scene";

export type Mat4 = Float32Array;

export function perspective(fovY: number, aspect: number, near: number, far: number): Mat4 {
  const f = 1 / Math.tan(fovY / 2);
  const m = new Float32Array(16);
  m[0] = f / aspect;
  m[5] = f;
  m[10] = (far + near) / (near - far);
  m[11] = -1;
  m[14] = (2 * far * near) / (near - far);
  return m;
}

/** View matrix from the orbit camera basis (world → eye, −z forward). */
export function view(cam: CameraBasis): Mat4 {
  const { pos, right, up, forward } = cam;
  const back = { x: -forward.x, y: -forward.y, z: -forward.z };
  const m = new Float32Array(16);
  m[0] = right.x; m[4] = right.y; m[8] = right.z; m[12] = -dot(right, pos);
  m[1] = up.x; m[5] = up.y; m[9] = up.z; m[13] = -dot(up, pos);
  m[2] = back.x; m[6] = back.y; m[10] = back.z; m[14] = -dot(back, pos);
  m[15] = 1;
  return m;
}

export function multiply(a: Mat4, b: Mat4): Mat4 {
  const m = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      m[c * 4 + r] = s;
    }
  }
  return m;
}

/** Transform a point; returns clip-space xyz after perspective divide, plus w. */
export function project(m: Mat4, p: Vec3): { x: number; y: number; z: number; w: number } {
  const x = m[0] * p.x + m[4] * p.y + m[8] * p.z + m[12];
  const y = m[1] * p.x + m[5] * p.y + m[9] * p.z + m[13];
  const z = m[2] * p.x + m[6] * p.y + m[10] * p.z + m[14];
  const w = m[3] * p.x + m[7] * p.y + m[11] * p.z + m[15];
  return { x: x / w, y: y / w, z: z / w, w };
}

/**
 * Depth-buffer value (0..1) → eye-space distance along the camera forward
 * axis. CPU mirror of the GLSL in the composite pass (ray distance is then
 * ze / dot(rd, fwd)).
 */
export function linearizeDepth(d: number, near: number, far: number): number {
  const ndc = 2 * d - 1;
  return (2 * near * far) / (far + near - ndc * (far - near));
}
