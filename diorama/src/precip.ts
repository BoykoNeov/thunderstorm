// Precipitation particles (slice 4): rain streaks and hail pellets as
// instanced GPU quads, driven by the NEAR-SURFACE voxel layers of the rain /
// graupelhail channels sampled directly from the resident 3D textures in the
// vertex shader (design doc §5.3 — no CPU readback, no separate surface
// stack). This module is the pure-CPU side: deterministic seeded instance
// buffers and the cyclic fall math, both unit-tested; the GLSL mirrors fallZ.
//
// Particles are presentation, not physics: they animate on WALL time (like
// the water ripples — storm time at 300× would teleport them), and their
// speeds/lengths scale with the storm's uniform display scale so a 2× storm
// sheds 2× rain — same transit time, same proportions, "the same storm shown
// larger" (charter: particle motion stays plausible under exaggeration).

export const FLOATS_PER_INSTANCE = 4; // u, v, phase, jitter

export interface PrecipSpec {
  /** instanced quad count */
  count: number;
  /** channel name whose near-surface field gates spawn density */
  gateChannel: "rain" | "graupelhail";
  /** decoded mixing ratio (kg/kg) where particles start appearing */
  qFloor: number;
  /** decoded mixing ratio (kg/kg) of full particle density */
  qFull: number;
  /** fall speed, km of display space per wall second, at 1× scale */
  fallSpeed: number;
  /** streak length along the fall axis, km at 1× scale */
  length: number;
  /** streak half-width, km (screen presence, not scaled — a hair, not a rod) */
  halfWidth: number;
  /** top of the fall cycle, km at 1× scale (roughly cloud base) */
  zTop: number;
  /** LDR tint (the scene target is tone-mapped before this pass) */
  color: [number, number, number];
  /** peak fragment alpha */
  alpha: number;
  /**
   * Spawn-pool footprint as a fraction of the volume-box half-extent: 1 =
   * uniform over the whole box, <1 = uniform in a centred disk. Presentation
   * only — the near-surface gate still decides visibility. Needed because
   * surface hail is REAL but tiny in area (measured ~1.5 km² at frames
   * 230–255 of the 500 m run): uniformly-spawned candidates would put ~0.4
   * pellets there. Assumes the cell stays near the domain centre (true for
   * this non-imove scenario; revisit for moving-domain scenarios).
   */
  spawnFrac: number;
}

// Tuned by eye against captures at frames 200–255 (near-surface rain first
// reaches the ground ~frame 200 of this run — the hero frame 150 is honestly
// rain-free at the surface) and against the measured gate-layer magnitudes:
// rain up to ~9e-3 kg/kg, hail only ~6e-4 kg/kg over ~1.5 km².
// Many fine faint lines beat few bold ones: at diorama camera distances the
// dense curtain fuses into the translucent gray sheet real rain reads as,
// while each line stays an individual streak up close.
export const RAIN: PrecipSpec = {
  count: 60000,
  gateChannel: "rain",
  qFloor: 2e-4,
  qFull: 2.5e-3,
  fallSpeed: 1.1,
  length: 1.05,
  halfWidth: 0.045,
  zTop: 2.0,
  color: [0.62, 0.72, 0.82],
  alpha: 0.35,
  spawnFrac: 1.0,
};

export const HAIL: PrecipSpec = {
  count: 4000,
  gateChannel: "graupelhail",
  qFloor: 1.5e-4,
  qFull: 8e-4,
  fallSpeed: 2.0,
  length: 0.16,
  halfWidth: 0.055,
  zTop: 2.0,
  color: [0.96, 0.97, 1.0],
  alpha: 0.8,
  spawnFrac: 0.35,
};

/** Same integer-lattice hash family as island.ts; deterministic everywhere. */
function hash1(i: number, seed: number): number {
  let h = (i * 374761393 + seed * 1442695041) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

/**
 * Per-instance static attributes: spawn (u, v) in the volume-box footprint
 * [0,1)², fall-cycle phase [0,1), and a size/speed jitter [0,1). Deterministic
 * for a given seed. `spawnFrac` < 1 concentrates the pool in a centred disk
 * (uniform by area); the gate sample still kills instances outside the shaft.
 */
export function buildPrecipInstances(count: number, seed: number, spawnFrac = 1): Float32Array {
  const data = new Float32Array(count * FLOATS_PER_INSTANCE);
  for (let i = 0; i < count; i++) {
    const o = i * FLOATS_PER_INSTANCE;
    if (spawnFrac < 1) {
      const r = (spawnFrac / 2) * Math.sqrt(hash1(i, seed));
      const a = 2 * Math.PI * hash1(i, seed + 404);
      data[o] = 0.5 + r * Math.cos(a);
      data[o + 1] = 0.5 + r * Math.sin(a);
    } else {
      data[o] = hash1(i, seed);
      data[o + 1] = hash1(i, seed + 101);
    }
    data[o + 2] = hash1(i, seed + 202);
    data[o + 3] = hash1(i, seed + 303);
  }
  return data;
}

/**
 * Cyclic fall: where along [zBot, zTop] a particle with `phase` sits at wall
 * time t. f is the cycle fraction (0 just spawned at zTop, →1 reaching zBot);
 * the GLSL in PRECIP_VERT mirrors this exactly.
 */
export function fallCycle(
  tWall: number,
  phase: number,
  speed: number,
  zTop: number,
  zBot: number,
): { z: number; f: number } {
  const span = zTop - zBot;
  const f = (((tWall * speed) / span + phase) % 1 + 1) % 1;
  return { z: zTop - f * span, f };
}

/** Ends-of-cycle fade so particles never pop in at the top or vanish mid-air. */
export function cycleFade(f: number): number {
  const up = Math.min(1, Math.max(0, f / 0.1));
  const down = Math.min(1, Math.max(0, (1 - f) / 0.15));
  return up * up * (3 - 2 * up) * (down * down * (3 - 2 * down));
}
