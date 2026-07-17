// Scene-space contract.
//
// World units are KILOMETRES on CM1's own axes: x east, y north, z up,
// right-handed. WebGL is right-handed too, so there is no handedness flip
// anywhere in this app. This module is the ONE place CM1 metres become scene
// units (charter: the coordinate/units conversion lives in exactly one module).
//
// The diorama LOOK (toy scale) is a presentation effect — camera, staging,
// depth-of-field — never a change to these coordinates. The storm's display
// scale (charter: render-time only, 1×–3×) is a UNIFORM magnification applied
// to the volume box here, at placement — proportions stay true — and is never
// baked into data.

import type { WebManifest } from "./volume";

export const M_TO_WORLD = 1 / 1000;

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface Box {
  min: Vec3;
  max: Vec3;
}

/**
 * World-space bounds of the volume texture, in km.
 *
 * The manifest's origin_m is the CENTRE of voxel (0,0,0) (OpenVDB convention,
 * carried over), so the box extends half a voxel beyond the first/last centres.
 * `scale` magnifies the storm uniformly (proportions stay true): horizontally
 * about the box centre, vertically about the ground plane (z = box floor), so
 * the storm base stays on the platter.
 */
export function volumeBox(man: WebManifest, scale = 1): Box {
  const g = man.grid;
  const [ox, oy, oz] = g.origin_m;
  const v = g.voxel_m;
  const x0 = (ox - v / 2) * M_TO_WORLD;
  const x1 = (ox + (g.nx - 0.5) * v) * M_TO_WORLD;
  const y0 = (oy - v / 2) * M_TO_WORLD;
  const y1 = (oy + (g.ny - 0.5) * v) * M_TO_WORLD;
  const z0 = (oz - v / 2) * M_TO_WORLD;
  const z1 = (oz + (g.nz - 0.5) * v) * M_TO_WORLD;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return {
    min: { x: cx + (x0 - cx) * scale, y: cy + (y0 - cy) * scale, z: z0 },
    max: { x: cx + (x1 - cx) * scale, y: cy + (y1 - cy) * scale, z: z0 + (z1 - z0) * scale },
  };
}
