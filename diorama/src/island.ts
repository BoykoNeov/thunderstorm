// Procedural diorama staging: a low-poly island on a circular water platter
// with a layered "resin base" side wall. Pure CPU, seeded, deterministic —
// built once at startup, unit-tested (Black Hole Lab discipline).
//
// This is DECORATIVE STAGING, not sim terrain (design doc §5.2): the Phase 1
// scenario is flat, and nothing here feeds back into anything physical. When
// Phase 3 terrain scenarios exist, this module is the slot where the real
// heightfield gets meshed instead.
//
// World units are km on CM1 axes (scene.ts contract). The platter is sized so
// the whole 52×52 km volume footprint stands on it (half-diagonal ≈ 36.8 km).
// Output is a flat-shaded triangle soup, interleaved 10 floats per vertex:
// position(3), face normal(3), face color(3), material(1: 0 land, 1 water).

export const PLATTER_RADIUS = 37; // km
export const WALL_DEPTH = 3.2; // km, toy base thickness
export const FLOATS_PER_VERTEX = 10;

export interface StagingMesh {
  data: Float32Array;
  vertexCount: number;
}

// -- seeded hash / noise ------------------------------------------------------

/** Integer lattice hash → [0,1); deterministic across runs and platforms. */
function hash2(ix: number, iy: number, seed: number): number {
  let h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

function smooth(t: number): number {
  return t * t * (3 - 2 * t);
}

/** Value noise on a unit lattice, bilinear with smoothstep fade. */
function vnoise(x: number, y: number, seed: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = smooth(x - ix);
  const fy = smooth(y - iy);
  const a = hash2(ix, iy, seed);
  const b = hash2(ix + 1, iy, seed);
  const c = hash2(ix, iy + 1, seed);
  const d = hash2(ix + 1, iy + 1, seed);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

/** 4-octave fBm in [0,1]-ish. */
function fbm(x: number, y: number, seed: number): number {
  let v = 0;
  let amp = 0.5;
  let f = 1;
  for (let o = 0; o < 4; o++) {
    v += amp * vnoise(x * f, y * f, seed + o * 101);
    amp *= 0.5;
    f *= 2.03;
  }
  return v / 0.9375;
}

// -- heightfield ----------------------------------------------------------------

// Island centre sits a little off the storm axis so the storm shadow sweeps
// across it instead of pinning it dead-centre.
const ISLE_CX = 4.5;
const ISLE_CY = -3.5;

/** Gentle stepped-plateau shaping — terraces without hard stair edges. */
function terrace(h: number, step: number): number {
  const k = h / step;
  const f = k - Math.floor(k);
  return (Math.floor(k) + smooth(Math.min(1, Math.max(0, (f - 0.2) / 0.6)))) * step;
}

/** Toy terrain height (km) at world (x, y). Deterministic for a given seed. */
export function heightAt(x: number, y: number, seed: number): number {
  const dx = x - ISLE_CX;
  const dy = y - ISLE_CY;
  const r = Math.hypot(dx, dy);
  // broad island shield + named features: a summit cone NE, a carved bay on
  // the south rim, and a small offshore islet NW
  const body = Math.exp(-(r * r) / (12 * 12)) * 0.95;
  const dPeak = Math.hypot(x - 9.0, y - 0.5);
  const peak = Math.exp(-(dPeak * dPeak) / (3.4 * 3.4)) * 0.95;
  const dBay = Math.hypot(x - 2.0, y + 9.5);
  const bay = Math.exp(-(dBay * dBay) / (4.5 * 4.5)) * 1.0;
  const dIslet = Math.hypot(x + 13.5, y - 7.5);
  const islet = Math.exp(-(dIslet * dIslet) / (2.4 * 2.4)) * 0.5;
  const n = fbm(x * 0.09, y * 0.09, seed);
  const reach = Math.max(0, 1 - r / 24); // noise texture fades out by ~24 km
  let h =
    body + peak + islet - bay + (n - 0.5) * 1.5 * reach - 0.12 -
    0.3 * smooth(Math.min(1, Math.max(0, (r - 20) / 6))); // shelf drops to deep sea
  if (h > 1.2) h = 1.2 + (h - 1.2) * 0.55; // soft-compress summits (toy scale)
  if (h > 0.12) h = 0.12 + terrace(h - 0.12, 0.3);
  return Math.max(h, -0.55); // shallow toy seabed; hidden by the water disk
}

// -- mesh assembly ----------------------------------------------------------------

class SoupBuilder {
  private parts: number[] = [];
  count = 0;

  /** One flat-shaded triangle; normal is per-face, flipped toward `refUp`. */
  tri(
    a: [number, number, number],
    b: [number, number, number],
    c: [number, number, number],
    color: [number, number, number],
    mat: number,
    refUp: [number, number, number],
  ): void {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    let nx = uy * vz - uz * vy;
    let ny = uz * vx - ux * vz;
    let nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz);
    if (l < 1e-9) return; // degenerate
    nx /= l; ny /= l; nz /= l;
    if (nx * refUp[0] + ny * refUp[1] + nz * refUp[2] < 0) {
      nx = -nx; ny = -ny; nz = -nz;
    }
    for (const p of [a, b, c]) {
      this.parts.push(p[0], p[1], p[2], nx, ny, nz, color[0], color[1], color[2], mat);
    }
    this.count += 3;
  }

  build(): StagingMesh {
    return { data: new Float32Array(this.parts), vertexCount: this.count };
  }
}

// palette (placeholder per design doc — tuned by eye with the owner)
const SAND: [number, number, number] = [0.86, 0.73, 0.45];
const GRASS_A: [number, number, number] = [0.33, 0.63, 0.28];
const GRASS_B: [number, number, number] = [0.17, 0.44, 0.23];
const ROCK: [number, number, number] = [0.5, 0.5, 0.46];
const SNOW: [number, number, number] = [0.93, 0.94, 0.95];
const WATER: [number, number, number] = [0.21, 0.58, 0.58];
const WALL_BANDS: [number, [number, number, number]][] = [
  // [band bottom z, color] — sediment layers of the toy base, top to bottom
  [-0.7, [0.87, 0.79, 0.6]],
  [-1.9, [0.63, 0.5, 0.39]],
  [-WALL_DEPTH, [0.46, 0.39, 0.34]],
];

function faceColor(
  havg: number,
  nz: number,
  jx: number,
  jy: number,
  seed: number,
): [number, number, number] {
  let c: [number, number, number];
  if (havg > 1.3) c = SNOW; // summit cap — makes the peak read as a mountain
  else if (nz < 0.72 || havg > 1.18) c = ROCK; // steep cliffs + a thin summit ring
  else if (havg < 0.04) c = SAND;
  else {
    const t = fbm(jx * 0.35, jy * 0.35, seed + 977);
    c = [
      GRASS_A[0] + (GRASS_B[0] - GRASS_A[0]) * t,
      GRASS_A[1] + (GRASS_B[1] - GRASS_A[1]) * t,
      GRASS_A[2] + (GRASS_B[2] - GRASS_A[2]) * t,
    ];
  }
  // small per-face value jitter sells the faceted low-poly look
  const j = (hash2(Math.round(jx * 37), Math.round(jy * 37), seed + 31) - 0.5) * 0.045;
  return [
    Math.min(1, Math.max(0, c[0] + j)),
    Math.min(1, Math.max(0, c[1] + j)),
    Math.min(1, Math.max(0, c[2] + j)),
  ];
}

/**
 * Build the full staging mesh: island heightfield + water platter disk +
 * layered side wall. Deterministic for a given seed.
 */
export function buildStaging(seed: number): StagingMesh {
  const soup = new SoupBuilder();

  // --- island heightfield, jittered grid, flat-shaded --------------------------
  const EXTENT = 27; // km half-size of the meshed square around the island
  const N = 200; // cells per side (~0.27 km cells — faceted but not chunky)
  const cell = (2 * EXTENT) / N;
  // lattice with consistent per-vertex jitter so neighbouring faces share verts
  const px = new Float32Array((N + 1) * (N + 1));
  const py = new Float32Array((N + 1) * (N + 1));
  const pz = new Float32Array((N + 1) * (N + 1));
  for (let j = 0; j <= N; j++) {
    for (let i = 0; i <= N; i++) {
      const id = j * (N + 1) + i;
      const jx = (hash2(i, j, seed + 7) - 0.5) * 0.45 * cell;
      const jy = (hash2(i, j, seed + 8) - 0.5) * 0.45 * cell;
      const x = ISLE_CX - EXTENT + i * cell + (i > 0 && i < N ? jx : 0);
      const y = ISLE_CY - EXTENT + j * cell + (j > 0 && j < N ? jy : 0);
      px[id] = x;
      py[id] = y;
      pz[id] = heightAt(x, y, seed);
    }
  }
  const SUBMERGED = -0.22; // faces entirely below this hide under the water disk
  for (let j = 0; j < N; j++) {
    for (let i = 0; i < N; i++) {
      const i00 = j * (N + 1) + i;
      const i10 = i00 + 1;
      const i01 = i00 + (N + 1);
      const i11 = i01 + 1;
      const quad = [i00, i10, i11, i01];
      if (quad.every((q) => pz[q] < SUBMERGED)) continue;
      // the meshed square's corners poke past the platter — drop open-sea
      // cells out there so every emitted vertex stays on the platter
      if (quad.some((q) => Math.hypot(px[q], py[q]) > PLATTER_RADIUS - 0.5)) continue;
      const P = (q: number): [number, number, number] => [px[q], py[q], pz[q]];
      // alternate the diagonal per cell parity — avoids a visible grid bias
      const tris =
        (i + j) % 2 === 0
          ? [[i00, i10, i11], [i00, i11, i01]]
          : [[i10, i11, i01], [i10, i01, i00]];
      for (const [a, b, c] of tris) {
        const havg = (pz[a] + pz[b] + pz[c]) / 3;
        const cx = (px[a] + px[b] + px[c]) / 3;
        const cy = (py[a] + py[b] + py[c]) / 3;
        // face normal z for the palette (recomputed inside tri() as well)
        const ux = px[b] - px[a], uy = py[b] - py[a], uz = pz[b] - pz[a];
        const vx = px[c] - px[a], vy = py[c] - py[a], vz = pz[c] - pz[a];
        let nz = ux * vy - uy * vx;
        const nl = Math.hypot(uy * vz - uz * vy, uz * vx - ux * vz, nz);
        nz = Math.abs(nz) / (nl || 1);
        soup.tri(P(a), P(b), P(c), faceColor(havg, nz, cx, cy, seed), 0, [0, 0, 1]);
      }
    }
  }

  // --- water platter disk (z = 0) ----------------------------------------------
  const SECT = 96;
  for (let s = 0; s < SECT; s++) {
    const a0 = (s / SECT) * 2 * Math.PI;
    const a1 = ((s + 1) / SECT) * 2 * Math.PI;
    const R = PLATTER_RADIUS;
    soup.tri(
      [0, 0, 0],
      [R * Math.cos(a0), R * Math.sin(a0), 0],
      [R * Math.cos(a1), R * Math.sin(a1), 0],
      WATER,
      1,
      [0, 0, 1],
    );
  }

  // --- side wall: sediment bands from the waterline down ------------------------
  for (let s = 0; s < SECT; s++) {
    const a0 = (s / SECT) * 2 * Math.PI;
    const a1 = ((s + 1) / SECT) * 2 * Math.PI;
    const R = PLATTER_RADIUS;
    const x0 = R * Math.cos(a0), y0 = R * Math.sin(a0);
    const x1 = R * Math.cos(a1), y1 = R * Math.sin(a1);
    const out: [number, number, number] = [
      Math.cos((a0 + a1) / 2),
      Math.sin((a0 + a1) / 2),
      0,
    ];
    let zTop = 0;
    for (const [zBot, col] of WALL_BANDS) {
      soup.tri([x0, y0, zTop], [x1, y1, zTop], [x1, y1, zBot], col, 0, out);
      soup.tri([x0, y0, zTop], [x1, y1, zBot], [x0, y0, zBot], col, 0, out);
      zTop = zBot;
    }
  }

  return soup.build();
}
