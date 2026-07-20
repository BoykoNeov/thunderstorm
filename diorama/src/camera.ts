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

// Pan bounds for the look-at point (km). The staging slab is 110×110 km and the
// storm box reaches ±52 km at the 3× scale cap, so ±60 lets you walk the target
// to any corner of either without letting a stray drag lose the diorama
// entirely. The z floor is the ground plane; 40 km clears the anvil at 3×.
const TARGET_XY = 60;
const TARGET_Z_MAX = 40;

export function clampOrbit(s: OrbitState): OrbitState {
  return {
    ...s,
    elevation: Math.min(EL_MAX, Math.max(EL_MIN, s.elevation)),
    distance: Math.min(500, Math.max(5, s.distance)),
  };
}

/** Keeps a panned look-at point inside the diorama (see TARGET_XY / _Z_MAX). */
export function clampTarget(t: Vec3): Vec3 {
  return {
    x: Math.min(TARGET_XY, Math.max(-TARGET_XY, t.x)),
    y: Math.min(TARGET_XY, Math.max(-TARGET_XY, t.y)),
    z: Math.min(TARGET_Z_MAX, Math.max(0, t.z)),
  };
}

/**
 * Scene-kilometres spanned by ONE pixel at the look-at point's depth.
 *
 * Exact only on the plane through the target perpendicular to the view — this
 * is a perspective camera, so nearer things read bigger and farther things
 * smaller. That is why the scale bar this feeds is labelled "at storm centre"
 * rather than presented as a scale for the whole image.
 *
 * `viewportHeightPx` must be CSS pixels (canvas.clientHeight), not the
 * device-pixel backing-store height — the bar is DOM and is laid out in CSS px.
 */
export function kmPerPixel(s: OrbitState, viewportHeightPx: number): number {
  return (2 * Math.tan(s.fovY / 2) * s.distance) / viewportHeightPx;
}

// Ground pan is foreshortened by sin(elevation): near the horizon one screen
// pixel spans a great deal of ground, and at el→0 the exact factor diverges.
// Clamping the divisor keeps a low camera from teleporting the target. 0.15 sits
// just under the default 11° view (sin = 0.19), so the default is exact.
const GROUND_MIN_SIN = 0.15;

/**
 * Right-drag pan: slide the look-at point ACROSS THE GROUND (z held).
 *
 * "Grab the world" convention — the scene follows the cursor, so the camera
 * translates opposite to the drag. Horizontal motion runs along `right`, which
 * is world-horizontal by construction (right.z === 0 for a z-up orbit), and
 * vertical motion runs along the ground-projected view direction, so dragging
 * down pulls the far countryside toward the viewer. Pixels convert at the
 * target's depth, which keeps the scene under the cursor at any zoom (the
 * reason pan feels wrong when it is hard-coded to a fixed km/px).
 *
 * Orbit is untouched: pan changes only `target`, so azimuth/elevation/distance
 * survive it.
 */
export function panGround(
  s: OrbitState,
  dxPx: number,
  dyPx: number,
  viewportHeightPx: number,
): OrbitState {
  const k = kmPerPixel(s, viewportHeightPx);
  const b = basis(s);
  const f = Math.hypot(b.forward.x, b.forward.y); // forward, flattened onto the ground
  const fx = f > 1e-9 ? b.forward.x / f : 0;
  const fy = f > 1e-9 ? b.forward.y / f : 0;
  const fwd = (dyPx * k) / Math.max(Math.sin(s.elevation), GROUND_MIN_SIN);
  return {
    ...s,
    target: clampTarget({
      x: s.target.x - b.right.x * dxPx * k + fx * fwd,
      y: s.target.y - b.right.y * dxPx * k + fy * fwd,
      z: s.target.z,
    }),
  };
}

/**
 * Middle-drag: raise/lower the look-at point — the elevator for following a
 * tall storm from cloud base to anvil. Same grab-the-world sense as panGround
 * (drag down ⇒ the scene slides down ⇒ you rise), so the two feel like one
 * gesture on different axes rather than opposites.
 */
export function panAltitude(s: OrbitState, dyPx: number, viewportHeightPx: number): OrbitState {
  const k = kmPerPixel(s, viewportHeightPx);
  return { ...s, target: clampTarget({ ...s.target, z: s.target.z + dyPx * k }) };
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
