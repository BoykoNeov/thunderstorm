// Idle-accumulation bookkeeping — pure (no WebGL), unit-tested.
//
// The volume march starts each ray at a per-pixel jittered offset (hash12) to
// hide banding; the residue is visible grain. When the view AND the displayed
// storm frame hold perfectly still (paused, or stalled on a buffering hold),
// we re-render with a DIFFERENT jitter each frame and average into a float
// buffer — the image converges to a grain-free "beauty still" in well under a
// second. Any change to the view or the bound frame resets the count instantly,
// so motion looks exactly as it does live.
//
// A "view key" captures everything that must be IDENTICAL between two rAFs for
// their renders to be averageable: camera orbit, the bound frame pair and the
// crossfade mix. Any change resets the count. (The animation clock is frozen by
// the caller while accumulating, so it is not part of the key.)

export interface ViewKey {
  az: number;
  el: number;
  dist: number;
  fovY: number;
  targetZ: number;
  fa: number;
  fb: number;
  mix: number;
}

export const ACC_CAP = 64; // converged after this many averaged frames

export function sameView(a: ViewKey | null, b: ViewKey): boolean {
  if (a === null) return false;
  return (
    a.az === b.az && a.el === b.el && a.dist === b.dist && a.fovY === b.fovY &&
    a.targetZ === b.targetZ && a.fa === b.fa && a.fb === b.fb && a.mix === b.mix
  );
}

/** Frames accumulated so far: 1 restarts, else count up to the cap. */
export function nextCount(same: boolean, prev: number, cap = ACC_CAP): number {
  return same ? Math.min(prev + 1, cap) : 1;
}

/** Low-discrepancy jitter offset for accumulation pass n (golden ratio). */
export function jitterSeq(n: number): number {
  return (n * 0.61803398875) % 1;
}
