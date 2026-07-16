// Scene-space contract.
//
// World units are KILOMETRES on CM1's own axes: x east, y north, z up,
// right-handed. WebGL is right-handed too, so there is no handedness flip
// anywhere in this app. This module is the ONE place CM1 metres become scene
// units (charter: the coordinate/units conversion lives in exactly one module).
//
// The diorama LOOK (toy scale) is a presentation effect — camera, staging,
// depth-of-field — never a change to these coordinates. Vertical exaggeration
// (charter: render-time only, 1×–3×) stretches the volume box here, at
// placement, and is never baked into data.

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
 * `zExaggeration` stretches z about the ground plane (z = box floor).
 */
export function volumeBox(man: WebManifest, zExaggeration = 1): Box {
  const g = man.grid;
  const [ox, oy, oz] = g.origin_m;
  const v = g.voxel_m;
  const min = {
    x: (ox - v / 2) * M_TO_WORLD,
    y: (oy - v / 2) * M_TO_WORLD,
    z: (oz - v / 2) * M_TO_WORLD,
  };
  const max = {
    x: (ox + (g.nx - 0.5) * v) * M_TO_WORLD,
    y: (oy + (g.ny - 0.5) * v) * M_TO_WORLD,
    z: min.z + ((oz + (g.nz - 0.5) * v) * M_TO_WORLD - min.z) * zExaggeration,
  };
  return { min, max };
}
