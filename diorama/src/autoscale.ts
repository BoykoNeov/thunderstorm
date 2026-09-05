// Dynamic render scale (?rs=auto) — pure decision logic, unit-tested.
//
// The march cost is ∝ drawn pixels, and render scale is the quality/fps lever
// the design doc names (§6). On a weak GPU a fixed scale is either too slow
// or needlessly soft; this holds the frame-rate cap by moving the scale
// between `min` and `max` from a per-frame cost measurement:
//
//  - "gpu" mode: the measurement is the GPU time of one rendered frame
//    (EXT_disjoint_timer_query_webgl2 via gputimer.ts). Cost ∝ scale², so the
//    new scale is current·sqrt(goal/measured), where goal = headroom·target.
//    Scaling DOWN is immediate (an overloaded frame is visible); scaling UP is
//    limited to two steps per decision so a still scene does not pop.
//  - "raf" mode (no timer extension — Firefox/Safari): the measurement is the
//    rendered-frame spacing. That saturates at the cap, so it can only say
//    "too slow", never "headroom": scale down when spacing exceeds 1.3× the
//    target, and PROBE up one step after a quiet interval that backs off
//    (5 s → 10 → … 60 s) whenever a probe was followed by a retreat.
//
// Decisions are rate-limited (≥ minFrames frames and ≥ minInterval ms since
// the last change): a resize reallocates every render target and resets the
// idle accumulation, so it must not churn. The caller feeds ONLY frames where
// the heavy passes actually ran (a converged still skips the march and would
// otherwise read as "free" and drive the scale up).

export interface AutoScaleOpts {
  min: number;
  max: number;
  /** fraction of the target frame time to aim for (leaves room for the browser's own work) */
  headroom: number;
  /** scale quantum — decisions land on multiples of this */
  step: number;
  /** rate limit: rendered frames between decisions */
  minFrames: number;
  /** rate limit: ms between changes */
  minInterval: number;
}

export const AUTO_DEFAULTS: AutoScaleOpts = {
  min: 0.5,
  max: 1,
  headroom: 0.8,
  step: 0.05,
  minFrames: 20,
  minInterval: 500,
};

export type AutoScaleMode = "gpu" | "raf";

export class AutoScaler {
  scale: number;
  private frames = 0;
  private lastChange = -Infinity;
  // raf-mode probing
  private probeInterval = 5000;
  private lastProbe = -Infinity;
  private quietSince = -Infinity;

  constructor(
    readonly mode: AutoScaleMode,
    readonly opts: AutoScaleOpts = AUTO_DEFAULTS,
    initial = 1,
  ) {
    this.scale = Math.min(opts.max, Math.max(opts.min, initial));
  }

  private quantize(s: number): number {
    const q = Math.round(s / this.opts.step) * this.opts.step;
    return Math.min(this.opts.max, Math.max(this.opts.min, Number(q.toFixed(6))));
  }

  /**
   * Feed one rendered frame's measurement (ms) against the target frame time
   * (ms). Returns the new scale when it changes, else null.
   */
  update(measuredMs: number, targetMs: number, now: number): number | null {
    if (!(measuredMs > 0) || !(targetMs > 0)) return null;
    this.frames++;
    if (this.frames < this.opts.minFrames || now - this.lastChange < this.opts.minInterval) return null;
    const next = this.mode === "gpu" ? this.decideGpu(measuredMs, targetMs) : this.decideRaf(measuredMs, targetMs, now);
    if (next === null || next === this.scale) return null;
    this.scale = next;
    this.frames = 0;
    this.lastChange = now;
    return next;
  }

  private decideGpu(measured: number, target: number): number | null {
    const goal = this.opts.headroom * target;
    // deadband: hold while within (0.7·goal, goal]
    if (measured <= goal && measured >= goal * 0.7) return null;
    let s = this.scale * Math.sqrt(goal / measured);
    if (s > this.scale) s = Math.min(s, this.scale + 2 * this.opts.step);
    return this.quantize(s);
  }

  private decideRaf(measured: number, target: number, now: number): number | null {
    if (measured > 1.3 * target) {
      // too slow: retreat. If this follows a recent probe, back the probing off.
      if (now - this.lastProbe < 2000) this.probeInterval = Math.min(60000, this.probeInterval * 2);
      this.quietSince = now;
      return this.quantize(this.scale * Math.sqrt((0.9 * target) / measured));
    }
    if (measured <= 1.05 * target) {
      if (this.quietSince === -Infinity) this.quietSince = now;
      if (now - this.quietSince >= this.probeInterval && this.scale < this.opts.max) {
        this.lastProbe = now;
        this.quietSince = now;
        return this.quantize(this.scale + this.opts.step);
      }
      return null;
    }
    // between 1.05× and 1.3×: not quiet, not yet a retreat
    this.quietSince = now;
    return null;
  }
}
