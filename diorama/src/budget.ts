// GPU-memory budget for the streaming ring — pure, unit-tested.
//
// The ring was sized as a fixed 24 slots when the only package was
// 208×208×72 (12.5 MB per RGBA8 brick → ~300 MB). A 540×540×54 supercell
// brick is 63 MB, so the same 24 slots would pin 1.5 GB of 3D textures (plus a
// parallel R8 ring per active diagnostic layer) — fine on a 32 GB card, fatal
// on a 4 GB laptop GPU. Slot count is therefore derived from a byte budget:
// as many slots as fit, clamped to [RING_MIN, RING_MAX].
//
// The floor matters as much as the cap: the pool must comfortably exceed the
// protected window (read-ahead + the bound pair + the last-bound pair), and
// re-uploading into a texture the GPU drew from moments ago forces a driver
// sync-wait (measured 50–77 ms with only 2 rotating slots). RING_MIN keeps
// ~4 rotating slots even for the biggest brick (10 = 2 read-ahead + 2 wanted
// + 2 last-bound + 4 rotating); read-ahead shrinks to fit.

export const RING_MAX = 24;
export const RING_MIN = 10;
/** Default GPU budget for the rgba ring, bytes (~300 MB — the Phase 1 envelope). */
export const RING_BUDGET_BYTES = 300 * 1024 * 1024;

export interface RingPlan {
  /** ring slots (3D textures) to allocate */
  slots: number;
  /** frames beyond the current pair to keep warm (never more than the ring can hold) */
  readAhead: number;
  /** bytes the rgba ring will pin */
  bytes: number;
}

/**
 * Slot count for a brick of `frameBytes`, under `budgetBytes`. `readAhead`
 * follows: the ring must hold the current pair + read-ahead + the previous
 * pair with ~4 slots to spare, so readAhead = slots - 8, clamped to
 * [2, wantedAhead].
 */
export function planRing(
  frameBytes: number,
  budgetBytes = RING_BUDGET_BYTES,
  wantedAhead = 10,
  minSlots = RING_MIN,
  maxSlots = RING_MAX,
): RingPlan {
  if (frameBytes <= 0) throw new Error("planRing: frameBytes must be positive");
  const fit = Math.floor(budgetBytes / frameBytes);
  const slots = Math.max(minSlots, Math.min(maxSlots, fit));
  const readAhead = Math.max(2, Math.min(wantedAhead, slots - 8));
  return { slots, readAhead, bytes: slots * frameBytes };
}

/**
 * Split a brick upload into z-slabs so no single texSubImage3D exceeds
 * `chunkBytes`. A 63 MB brick uploaded in one call stalls the main thread
 * for tens of ms (measured 200+ ms rAF gaps on the supercell package); slabs
 * of ~16 MB spread that over consecutive rAFs. Returns [z0, z1) ranges.
 * A brick at or under the chunk size is one range (today's behaviour).
 */
export function uploadSlabs(nz: number, bytesPerSlice: number, chunkBytes: number): [number, number][] {
  if (nz <= 0) return [];
  const slicesPerChunk = Math.max(1, Math.floor(chunkBytes / Math.max(bytesPerSlice, 1)));
  const out: [number, number][] = [];
  for (let z = 0; z < nz; z += slicesPerChunk) out.push([z, Math.min(nz, z + slicesPerChunk)]);
  return out;
}
