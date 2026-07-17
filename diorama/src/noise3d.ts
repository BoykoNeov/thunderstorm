// Tileable 3D value noise, baked once into a small RG8 3D texture (REPEAT,
// trilinear). Two octaves in two channels sampled with one fetch: R is coarse
// (CELLS_R lattice cells per tile), G is fine (CELLS_G). The volume shader
// uses it for (a) edge "detail erosion" of the cloud — sub-voxel structure the
// 250 m grid cannot carry, breaking up the trilinear voxel facets — and (b)
// the rain veil's vertically-stretched falling-sheet modulation. Presentation
// only, never physics: noise modulates how the data LOOKS, never what it says.
//
// This module is the pure CPU side (deterministic, unit-tested); the GLSL just
// samples the texture.

export const NOISE_SIZE = 64;
export const CELLS_R = 4; // coarse octave: wavelength = tile / 4
export const CELLS_G = 16; // fine octave: wavelength = tile / 16

/** Same integer-lattice hash family as island.ts / precip.ts. */
function hash3(x: number, y: number, z: number, seed: number): number {
  let h = (x * 374761393 + y * 668265263 + z * 1440662683 + seed * 1442695041) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

const fade = (t: number) => t * t * (3 - 2 * t);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/**
 * Periodic value noise at continuous lattice coords (units = lattice cells),
 * period `cells` along every axis. Returns [0, 1). Periodicity is what makes
 * the baked texture tile seamlessly under REPEAT sampling.
 */
export function valueNoise3(
  x: number,
  y: number,
  z: number,
  cells: number,
  seed: number,
): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const zi = Math.floor(z);
  const fx = fade(x - xi);
  const fy = fade(y - yi);
  const fz = fade(z - zi);
  const w = (i: number) => ((i % cells) + cells) % cells;
  const c = (dx: number, dy: number, dz: number) =>
    hash3(w(xi + dx), w(yi + dy), w(zi + dz), seed);
  return lerp(
    lerp(lerp(c(0, 0, 0), c(1, 0, 0), fx), lerp(c(0, 1, 0), c(1, 1, 0), fx), fy),
    lerp(lerp(c(0, 0, 1), c(1, 0, 1), fx), lerp(c(0, 1, 1), c(1, 1, 1), fx), fy),
    fz,
  );
}

/**
 * Bake the RG8 texture data: NOISE_SIZE³ texels × 2 bytes (R coarse, G fine),
 * evaluated at texel centers so GL's trilinear interpolation reconstructs the
 * periodic lattice function seamlessly across the wrap.
 */
export function buildNoise3D(seed: number): Uint8Array {
  const n = NOISE_SIZE;
  const data = new Uint8Array(n * n * n * 2);
  for (let k = 0; k < n; k++) {
    for (let j = 0; j < n; j++) {
      for (let i = 0; i < n; i++) {
        const u = (i + 0.5) / n;
        const v = (j + 0.5) / n;
        const w = (k + 0.5) / n;
        const o = ((k * n + j) * n + i) * 2;
        data[o] = Math.min(
          255,
          Math.round(valueNoise3(u * CELLS_R, v * CELLS_R, w * CELLS_R, CELLS_R, seed) * 255),
        );
        data[o + 1] = Math.min(
          255,
          Math.round(
            valueNoise3(u * CELLS_G, v * CELLS_G, w * CELLS_G, CELLS_G, seed + 7777) * 255,
          ),
        );
      }
    }
  }
  return data;
}
