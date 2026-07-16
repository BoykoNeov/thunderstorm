// Orbit camera, z-up, right-handed. Pure math kept separate from DOM event
// wiring (main.ts) so it is unit-testable — Black Hole Lab discipline.

import type { Vec3 } from "./scene";

export interface OrbitState {
  target: Vec3;
  /** radians around +z; 0 looks along −x toward the target from +x side */
  azimuth: number;
  /** radians above the horizon, clamped shy of the pole */
  elevation: number;
  /** km */
  distance: number;
  /** vertical field of view, radians (small = long lens = diorama look) */
  fovY: number;
}

export interface CameraBasis {
  pos: Vec3;
  right: Vec3;
  up: Vec3;
  forward: Vec3;
}

const EL_MIN = 0.02;
const EL_MAX = Math.PI / 2 - 0.02;

export function clampOrbit(s: OrbitState): OrbitState {
  return {
    ...s,
    elevation: Math.min(EL_MAX, Math.max(EL_MIN, s.elevation)),
    distance: Math.min(500, Math.max(5, s.distance)),
  };
}

/** Camera position + orthonormal basis (forward toward the target). */
export function basis(s: OrbitState): CameraBasis {
  const ce = Math.cos(s.elevation);
  const off = {
    x: ce * Math.cos(s.azimuth),
    y: ce * Math.sin(s.azimuth),
    z: Math.sin(s.elevation),
  };
  const pos = {
    x: s.target.x + off.x * s.distance,
    y: s.target.y + off.y * s.distance,
    z: s.target.z + off.z * s.distance,
  };
  const forward = norm({ x: -off.x, y: -off.y, z: -off.z });
  // z-up world: right = forward × up_world, then true up = right × forward.
  const right = norm(cross(forward, { x: 0, y: 0, z: 1 }));
  const up = cross(right, forward);
  return { pos, right, up, forward };
}

export function cross(a: Vec3, b: Vec3): Vec3 {
  return { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
}

export function dot(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

export function norm(a: Vec3): Vec3 {
  const l = Math.hypot(a.x, a.y, a.z);
  return { x: a.x / l, y: a.y / l, z: a.z / l };
}

/** Unit vector from azimuth/elevation (used for the sun). */
export function direction(azimuth: number, elevation: number): Vec3 {
  const ce = Math.cos(elevation);
  return { x: ce * Math.cos(azimuth), y: ce * Math.sin(azimuth), z: Math.sin(elevation) };
}
