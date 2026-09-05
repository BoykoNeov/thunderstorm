// Per-pass GPU timing via EXT_disjoint_timer_query_webgl2 (perf instrument).
//
// rAF spacing is a poor cost signal: it is vsync-quantized, the upload pump
// and DOM writes ride on it, and headless Chrome adds its own jitter. This
// wraps each render pass in a TIME_ELAPSED query and keeps an exponential
// moving average per label, so a change to the march can be judged by the
// march's own GPU milliseconds — the number the ?stats HUD line and
// window.__stats.gpu report. Only one TIME_ELAPSED query may be active at a
// time, so passes are timed back-to-back, never nested.
//
// If the extension is missing (some mobile/ANGLE configurations, or Chrome
// with the extension disabled), every method is a no-op and `available` is
// false — the render loop is unchanged either way.

interface Pending {
  label: string;
  query: WebGLQuery;
}

interface TimerExt {
  TIME_ELAPSED_EXT: number;
  GPU_DISJOINT_EXT: number;
}

export class GpuTimer {
  readonly available: boolean;
  private ext: TimerExt | null;
  private pending: Pending[] = [];
  private active: Pending | null = null;
  /** EMA of GPU ms per label (alpha 0.1 → ~10-frame window). */
  readonly ms = new Map<string, number>();
  /** Most recent raw sample per label, ms. */
  readonly last = new Map<string, number>();
  private samples = 0;

  constructor(private gl: WebGL2RenderingContext, enabled: boolean) {
    this.ext = enabled ? (gl.getExtension("EXT_disjoint_timer_query_webgl2") as TimerExt | null) : null;
    this.available = this.ext !== null;
  }

  /** Start timing `label`. Ends any query still open (passes never nest). */
  begin(label: string): void {
    if (!this.ext) return;
    if (this.active) this.end();
    const query = this.gl.createQuery();
    if (!query) return;
    this.gl.beginQuery(this.ext.TIME_ELAPSED_EXT, query);
    this.active = { label, query };
  }

  end(): void {
    if (!this.ext || !this.active) return;
    this.gl.endQuery(this.ext.TIME_ELAPSED_EXT);
    this.pending.push(this.active);
    this.active = null;
  }

  /**
   * Collect finished queries (call once per frame, before the first begin).
   * A disjoint event (GPU clock change, context interruption) invalidates
   * every outstanding query, so those results are dropped, not recorded.
   */
  poll(): void {
    if (!this.ext) return;
    const gl = this.gl;
    const disjoint = gl.getParameter(this.ext.GPU_DISJOINT_EXT) as boolean;
    const keep: Pending[] = [];
    for (const p of this.pending) {
      const done = gl.getQueryParameter(p.query, gl.QUERY_RESULT_AVAILABLE) as boolean;
      if (!done) {
        keep.push(p);
        continue;
      }
      if (!disjoint) {
        const ns = gl.getQueryParameter(p.query, gl.QUERY_RESULT) as number;
        const v = ns / 1e6;
        this.last.set(p.label, v);
        const prev = this.ms.get(p.label);
        this.ms.set(p.label, prev === undefined ? v : prev + (v - prev) * 0.1);
        this.samples++;
      }
      gl.deleteQuery(p.query);
    }
    this.pending = keep;
  }

  /** Number of accepted samples so far (all labels) — lets a driver wait for warm-up. */
  get count(): number {
    return this.samples;
  }

  /** Plain object snapshot for window.__stats / logging. */
  snapshot(): Record<string, number> {
    const o: Record<string, number> = {};
    for (const [k, v] of this.ms) o[k] = Math.round(v * 100) / 100;
    return o;
  }

  /** One-line HUD text: "gpu 12.3 ms · march 9.8 · geo 0.4 · …". */
  hudLine(): string {
    if (!this.available) return "gpu timer unavailable";
    let total = 0;
    const parts: string[] = [];
    for (const [k, v] of this.ms) {
      total += v;
      parts.push(`${k} ${v.toFixed(1)}`);
    }
    return `gpu ${total.toFixed(1)} ms · ${parts.join(" · ")}`;
  }
}
