// Procedural diorama staging: a big square slab of continuous countryside —
// rolling hills, a few small mountain massifs, carved lakes, seeded forests
// and toy towns — with a layered "resin base" side wall. Pure CPU, seeded,
// deterministic — built once at startup, unit-tested (Black Hole Lab
// discipline).
//
// This is DECORATIVE STAGING, not sim terrain (design doc §5.2): the Phase 1
// scenario is flat, and nothing here feeds back into anything physical. When
// Phase 3 terrain scenarios exist, this module is the slot where the real
// heightfield gets meshed instead.
//
// World units are km on CM1 axes (scene.ts contract). The slab is sized so
// the whole 52×52 km volume footprint (104×104 km at the default 2× display
// scale) stands on it. Output is a flat-shaded triangle soup, interleaved
// 10 floats per vertex: position(3), face normal(3), face color(3),
// material(1: 0 land, 1 water).

export const GROUND_HALF = 55; // km, half-size of the square ground slab
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

function s01(t: number): number {
  return t <= 0 ? 0 : t >= 1 ? 1 : smooth(t);
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
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

/** Gentle stepped-plateau shaping — terraces without hard stair edges. */
function terrace(h: number, step: number): number {
  const k = h / step;
  const f = k - Math.floor(k);
  return (Math.floor(k) + smooth(Math.min(1, Math.max(0, (f - 0.2) / 0.6)))) * step;
}

/**
 * Toy terrain height (km) at world (x, y). Deterministic for a given seed.
 * Continuous countryside: rolling hills everywhere, three seeded mountain
 * massifs with ridged detail, three seeded lake depressions (water sits at
 * z = 0), and a rim lift that keeps the slab edge dry.
 */
export function heightAt(x: number, y: number, seed: number): number {
  // rolling countryside base
  let h = 0.3 + (fbm(x * 0.045, y * 0.045, seed) - 0.5) * 0.7;

  // lakes: seeded depressions deep enough to dip below the z=0 water sheet
  for (let l = 0; l < 3; l++) {
    const lx = (hash2(l, 71, seed) - 0.5) * 2 * (GROUND_HALF - 16);
    const ly = (hash2(l, 72, seed) - 0.5) * 2 * (GROUND_HALF - 16);
    const lr = 4.5 + 3 * hash2(l, 73, seed);
    const d = Math.hypot(x - lx, y - ly);
    h -= Math.exp(-(d * d) / (lr * lr));
  }

  // dry rim: lift the outer band so water never leaks off the slab edge
  const rim = s01((Math.max(Math.abs(x), Math.abs(y)) - (GROUND_HALF - 7)) / 5);
  if (rim > 0) h += (Math.max(h, 0.18) - h) * rim;

  // terraced countryside — the toy-farmland read (mountains added after,
  // untouched by terracing, so their ridges stay rugged)
  if (h > 0.12) h = 0.12 + terrace(h - 0.12, 0.3);

  // small mountain massifs on a ring 20–38 km off the storm axis, so summits
  // stay clear of the cloud base over the storm; capped so overlaps can't
  // launch a summit past toy scale
  let massif = 0;
  for (let m = 0; m < 3; m++) {
    const am = hash2(m, 81, seed) * 2 * Math.PI;
    const rm = 20 + 18 * hash2(m, 82, seed);
    const mr = 7 + 5 * hash2(m, 83, seed);
    const d = Math.hypot(x - Math.cos(am) * rm, y - Math.sin(am) * rm);
    massif += Math.exp(-(d * d) / (mr * mr));
  }
  massif = Math.min(massif, 1.2);
  if (massif > 0.01) {
    // ridge-dominant (small pedestal): peaks and green valleys, not a dome
    const ridge = 1 - Math.abs(2 * fbm(x * 0.18, y * 0.18, seed + 733) - 1);
    h += massif * (0.35 + 2.35 * ridge * ridge);
  }

  if (h > 2.0) h = 2.0 + (h - 2.0) * 0.5; // soft-compress summits (toy scale)
  return Math.min(Math.max(h, -0.5), 3.0); // shallow lakes, hard toy summit cap
}

/** Local terrain slope (rise/run) — placement gate for trees and houses. */
function slopeAt(x: number, y: number, seed: number): number {
  const e = 0.3;
  const h0 = heightAt(x, y, seed);
  return (
    Math.hypot(heightAt(x + e, y, seed) - h0, heightAt(x, y + e, seed) - h0) / e
  );
}

/** Forest-cover noise in [0,1]-ish; forests live where this exceeds ~0.56. */
export function forestAt(x: number, y: number, seed: number): number {
  return fbm(x * 0.05 + 11.3, y * 0.05 + 5.7, seed + 555);
}

// -- decoration placement (exported for unit tests) -----------------------------

export interface TreeSpot {
  x: number;
  y: number;
  z: number; // base height, km (slightly sunk into the terrain)
  size: number; // cone height, km
}

export interface HouseSpot {
  x: number;
  y: number;
  z: number; // terrain height at the house, km
  yaw: number;
  w: number; // half-length along the ridge, km
  d: number; // half-width, km
  wallH: number;
  roofH: number;
  roof: number; // 0 = red tile, 1 = slate
}

export interface Town {
  x: number;
  y: number;
  houses: HouseSpot[];
}

/** Seeded forest scatter: cone-tree spots in forest zones on gentle dry land. */
export function placeTrees(seed: number): TreeSpot[] {
  const out: TreeSpot[] = [];
  for (let i = 0; i < 30000 && out.length < 3500; i++) {
    const x = (hash2(i, 1, seed + 601) - 0.5) * 2 * (GROUND_HALF - 1.5);
    const y = (hash2(i, 2, seed + 601) - 0.5) * 2 * (GROUND_HALF - 1.5);
    if (forestAt(x, y, seed) < 0.56) continue;
    const h = heightAt(x, y, seed);
    if (h < 0.06 || h > 0.9) continue; // treeline below the rock ramp
    if (slopeAt(x, y, seed) > 0.45) continue;
    out.push({ x, y, z: h - 0.03, size: 0.28 + 0.34 * hash2(i, 3, seed + 601) });
  }
  return out;
}

/** Seeded towns: spaced-out clusters of houses on flat low land. */
export function placeTowns(seed: number): Town[] {
  const towns: Town[] = [];
  for (let i = 0; i < 4000 && towns.length < 8; i++) {
    const x = (hash2(i, 5, seed + 907) - 0.5) * 2 * (GROUND_HALF - 5);
    const y = (hash2(i, 6, seed + 907) - 0.5) * 2 * (GROUND_HALF - 5);
    const h = heightAt(x, y, seed);
    if (h < 0.05 || h > 0.55) continue;
    if (slopeAt(x, y, seed) > 0.12) continue;
    if (forestAt(x, y, seed) > 0.62) continue; // not deep inside a forest
    if (towns.some((t) => Math.hypot(t.x - x, t.y - y) < 14)) continue;
    // loose village grid: houses share two perpendicular orientations
    const baseYaw = hash2(i, 7, seed + 907) * Math.PI;
    const n = 12 + Math.floor(hash2(i, 8, seed + 907) * 22);
    const houses: HouseSpot[] = [];
    for (let k = 0; k < n * 4 && houses.length < n; k++) {
      const id = i * 131 + k;
      const a = hash2(id, 9, seed + 907) * 2 * Math.PI;
      const r = Math.sqrt(hash2(id, 10, seed + 907)) * 2.4;
      const hx = x + Math.cos(a) * r;
      const hy = y + Math.sin(a) * r;
      const hh = heightAt(hx, hy, seed);
      if (hh < 0.03 || hh > 0.7) continue; // villages stay below the treeline
      if (slopeAt(hx, hy, seed) > 0.22) continue;
      houses.push({
        x: hx,
        y: hy,
        z: hh,
        yaw:
          baseYaw +
          (hash2(id, 11, seed + 907) < 0.5 ? 0 : Math.PI / 2) +
          (hash2(id, 12, seed + 907) - 0.5) * 0.12,
        w: 0.13 + 0.08 * hash2(id, 13, seed + 907),
        d: 0.09 + 0.05 * hash2(id, 14, seed + 907),
        wallH: 0.12 + 0.06 * hash2(id, 15, seed + 907),
        roofH: 0.09 + 0.05 * hash2(id, 16, seed + 907),
        roof: hash2(id, 17, seed + 907) < 0.65 ? 0 : 1,
      });
    }
    if (houses.length >= 6) towns.push({ x, y, houses });
  }
  return towns;
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

  quad(
    a: [number, number, number],
    b: [number, number, number],
    c: [number, number, number],
    d: [number, number, number],
    color: [number, number, number],
    mat: number,
    refUp: [number, number, number],
  ): void {
    this.tri(a, b, c, color, mat, refUp);
    this.tri(a, c, d, color, mat, refUp);
  }

  build(): StagingMesh {
    return { data: new Float32Array(this.parts), vertexCount: this.count };
  }
}

// palette (placeholder per design doc — tuned by eye with the owner)
const SAND: [number, number, number] = [0.86, 0.73, 0.45];
const GRASS_A: [number, number, number] = [0.33, 0.63, 0.28];
const GRASS_B: [number, number, number] = [0.17, 0.44, 0.23];
const FOREST_FLOOR: [number, number, number] = [0.1, 0.27, 0.13];
const ROCK: [number, number, number] = [0.5, 0.5, 0.46];
const SNOW: [number, number, number] = [0.93, 0.94, 0.95];
const WATER: [number, number, number] = [0.16, 0.42, 0.47];
const ROOF_TILE: [number, number, number] = [0.58, 0.23, 0.17];
const ROOF_SLATE: [number, number, number] = [0.36, 0.38, 0.44];
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
  const mix3 = (
    a: [number, number, number],
    b: [number, number, number],
    t: number,
  ): [number, number, number] => [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
  let c: [number, number, number];
  if (havg < 0.02) c = SAND; // lake shores (narrow band)
  else if (nz < 0.72) c = ROCK; // steep cliffs
  else {
    const t = fbm(jx * 0.35, jy * 0.35, seed + 977);
    c = mix3(GRASS_A, GRASS_B, t);
    // forest floor: ground under tree cover reads darker from above
    const f = s01((forestAt(jx, jy, seed) - 0.56) / 0.1);
    if (f > 0) c = mix3(c, FOREST_FLOOR, 0.6 * f);
    // mountains: grass → rock across the treeline, rock → snow at the caps.
    // The terraced plains top out ≈0.72, so the rock ramp only hits massifs —
    // the grey body is what makes them READ as mountains at diorama distance.
    c = mix3(c, ROCK, s01((havg - 0.85) / 0.25));
    c = mix3(c, SNOW, s01((havg - 1.9) / 0.25));
  }
  // small per-face value jitter sells the faceted low-poly look
  const j = (hash2(Math.round(jx * 37), Math.round(jy * 37), seed + 31) - 0.5) * 0.045;
  return [clamp01(c[0] + j), clamp01(c[1] + j), clamp01(c[2] + j)];
}

// -- decoration geometry ---------------------------------------------------------

/** Four-sided cone tree — 4 tris, random yaw, green varied per tree. */
function addTree(soup: SoupBuilder, t: TreeSpot, i: number, seed: number): void {
  const r = t.size * 0.45;
  const yaw = hash2(i, 41, seed + 601) * (Math.PI / 2);
  const g = 0.8 + 0.45 * hash2(i, 42, seed + 601);
  const col: [number, number, number] = [
    clamp01(0.09 * g),
    clamp01(0.3 * g),
    clamp01(0.11 * g),
  ];
  const apex: [number, number, number] = [t.x, t.y, t.z + t.size];
  const base: [number, number, number][] = [];
  for (let k = 0; k < 4; k++) {
    const a = yaw + (k * Math.PI) / 2;
    base.push([t.x + Math.cos(a) * r, t.y + Math.sin(a) * r, t.z]);
  }
  for (let k = 0; k < 4; k++) {
    const b0 = base[k];
    const b1 = base[(k + 1) % 4];
    // refUp: outward from the tree axis — only its sign matters
    soup.tri(b0, b1, apex, col, 0, [
      (b0[0] + b1[0]) / 2 - t.x,
      (b0[1] + b1[1]) / 2 - t.y,
      0,
    ]);
  }
}

/** Toy house: 4 walls, pitched roof, 2 gables — 14 tris, sunk into the slope. */
function addHouse(soup: SoupBuilder, hs: HouseSpot, seed: number): void {
  const c = Math.cos(hs.yaw);
  const s = Math.sin(hs.yaw);
  const P = (u: number, v: number, z: number): [number, number, number] => [
    hs.x + c * u - s * v,
    hs.y + s * u + c * v,
    z,
  ];
  const z0 = hs.z - 0.06; // walls sink so the house never floats on a slope
  const z1 = hs.z + hs.wallH;
  const z2 = z1 + hs.roofH;
  const jw = (hash2(Math.round(hs.x * 53), Math.round(hs.y * 53), seed + 71) - 0.5) * 0.08;
  const wall: [number, number, number] = [
    clamp01(0.88 + jw),
    clamp01(0.83 + jw),
    clamp01(0.71 + jw),
  ];
  const roof = hs.roof === 0 ? ROOF_TILE : ROOF_SLATE;
  const w = hs.w;
  const d = hs.d;
  soup.quad(P(-w, d, z0), P(w, d, z0), P(w, d, z1), P(-w, d, z1), wall, 0, [-s, c, 0]);
  soup.quad(P(w, -d, z0), P(-w, -d, z0), P(-w, -d, z1), P(w, -d, z1), wall, 0, [s, -c, 0]);
  soup.quad(P(w, d, z0), P(w, -d, z0), P(w, -d, z1), P(w, d, z1), wall, 0, [c, s, 0]);
  soup.quad(P(-w, -d, z0), P(-w, d, z0), P(-w, d, z1), P(-w, -d, z1), wall, 0, [-c, -s, 0]);
  // roof slopes meet at a ridge along the house's long axis
  soup.quad(P(-w, d, z1), P(w, d, z1), P(w, 0, z2), P(-w, 0, z2), roof, 0, [0, 0, 1]);
  soup.quad(P(w, -d, z1), P(-w, -d, z1), P(-w, 0, z2), P(w, 0, z2), roof, 0, [0, 0, 1]);
  soup.tri(P(w, d, z1), P(w, -d, z1), P(w, 0, z2), wall, 0, [c, s, 0]);
  soup.tri(P(-w, -d, z1), P(-w, d, z1), P(-w, 0, z2), wall, 0, [-c, -s, 0]);
}

/**
 * Build the full staging mesh: countryside heightfield + lake water sheet +
 * layered side walls + forests + towns. Deterministic for a given seed.
 */
export function buildStaging(seed: number): StagingMesh {
  const soup = new SoupBuilder();

  // --- terrain heightfield, jittered grid, flat-shaded --------------------------
  const N = 288; // cells per side (~0.38 km cells — faceted but not chunky)
  const cell = (2 * GROUND_HALF) / N;
  // lattice with consistent per-vertex jitter so neighbouring faces share verts;
  // boundary rows stay unjittered so the side walls meet the terrain crack-free
  const px = new Float32Array((N + 1) * (N + 1));
  const py = new Float32Array((N + 1) * (N + 1));
  const pz = new Float32Array((N + 1) * (N + 1));
  for (let j = 0; j <= N; j++) {
    for (let i = 0; i <= N; i++) {
      const id = j * (N + 1) + i;
      const jx = (hash2(i, j, seed + 7) - 0.5) * 0.45 * cell;
      const jy = (hash2(i, j, seed + 8) - 0.5) * 0.45 * cell;
      const x = -GROUND_HALF + i * cell + (i > 0 && i < N ? jx : 0);
      const y = -GROUND_HALF + j * cell + (j > 0 && j < N ? jy : 0);
      px[id] = x;
      py[id] = y;
      pz[id] = heightAt(x, y, seed);
    }
  }
  const SUBMERGED = -0.18; // faces entirely below this hide under the water sheet
  for (let j = 0; j < N; j++) {
    for (let i = 0; i < N; i++) {
      const i00 = j * (N + 1) + i;
      const i10 = i00 + 1;
      const i01 = i00 + (N + 1);
      const i11 = i01 + 1;
      if ([i00, i10, i11, i01].every((q) => pz[q] < SUBMERGED)) continue;
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

  // --- lake water sheet (z = 0, full slab; visible only where terrain dips) ----
  const H = GROUND_HALF;
  soup.quad([-H, -H, 0], [H, -H, 0], [H, H, 0], [-H, H, 0], WATER, 1, [0, 0, 1]);

  // --- side walls: terrain edge down through sediment bands ----------------------
  // built from the same boundary lattice points as the terrain, so no cracks
  const wallSide = (at: (t: number) => number, out: [number, number, number]) => {
    for (let t = 0; t < N; t++) {
      const a = at(t);
      const b = at(t + 1);
      let zTopA = pz[a];
      let zTopB = pz[b];
      for (const [zBot, col] of WALL_BANDS) {
        soup.tri([px[a], py[a], zTopA], [px[b], py[b], zTopB], [px[b], py[b], zBot], col, 0, out);
        soup.tri([px[a], py[a], zTopA], [px[b], py[b], zBot], [px[a], py[a], zBot], col, 0, out);
        zTopA = zBot;
        zTopB = zBot;
      }
    }
  };
  wallSide((t) => t, [0, -1, 0]); // south (j = 0)
  wallSide((t) => N * (N + 1) + t, [0, 1, 0]); // north (j = N)
  wallSide((t) => t * (N + 1), [-1, 0, 0]); // west (i = 0)
  wallSide((t) => t * (N + 1) + N, [1, 0, 0]); // east (i = N)

  // --- forests + towns (seeded, gated by the same heightfield) -------------------
  const trees = placeTrees(seed);
  for (let i = 0; i < trees.length; i++) addTree(soup, trees[i], i, seed);
  for (const town of placeTowns(seed)) {
    for (const hs of town.houses) addHouse(soup, hs, seed);
  }

  return soup.build();
}
