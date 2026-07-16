// Playback timing — pure functions over the manifest's storm-time stamps.
//
// Charter conventions: frames carry storm-time stamps; playback speed is a
// pure UI multiplier. The clock state itself lives in main.ts; everything
// here is stateless and unit-tested (Black Hole Lab discipline).

/** A position between two frames: sample = mix(frame i0, frame i1, f). */
export interface FramePos {
  i0: number;
  i1: number;
  /** crossfade fraction in [0, 1); 0 means exactly on frame i0 */
  f: number;
}

/**
 * Locate storm time t within the (strictly increasing) frame time stamps.
 * Clamps outside the range; i1 == i0 on the last frame so callers never
 * index past the end.
 */
export function locate(times: number[], t: number): FramePos {
  const n = times.length;
  if (n === 0) throw new Error("locate: no frames");
  if (t <= times[0]) return { i0: 0, i1: n > 1 ? 1 : 0, f: 0 };
  if (t >= times[n - 1]) return { i0: n - 1, i1: n - 1, f: 0 };
  // binary search: largest i with times[i] <= t
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) lo = mid;
    else hi = mid;
  }
  const span = times[hi] - times[lo];
  return { i0: lo, i1: hi, f: span > 0 ? (t - times[lo]) / span : 0 };
}

/**
 * Advance storm time by dtStorm (storm seconds), looping over [t0, t1).
 * The loop restart is a jump cut by design — no crossfade across the wrap.
 */
export function advance(t: number, dtStorm: number, t0: number, t1: number): number {
  const span = t1 - t0;
  if (span <= 0) return t0;
  let next = t + dtStorm;
  if (next >= t1 || next < t0) {
    next = t0 + (((next - t0) % span) + span) % span;
  }
  return next;
}

/**
 * The frame indices playback wants resident, in priority order: the current
 * pair first, then the read-ahead window (wrapping — playback loops).
 */
export function wantedFrames(i0: number, ahead: number, n: number): number[] {
  const count = Math.min(ahead + 2, n);
  const out: number[] = [];
  for (let k = 0; k < count; k++) out.push((i0 + k) % n);
  return out;
}
