// GPU-texture ring buffer bookkeeping — pure (no WebGL), unit-tested.
//
// A fixed pool of slots (each backed by one 3D texture in main.ts) holds
// decoded frames. Assignment evicts the least-recently-used slot whose frame
// is not protected, so the frames the march is actively sampling can never
// be overwritten mid-render.

export class SlotPool {
  private slotFrame: (number | null)[];
  private frameSlot = new Map<number, number>();
  private stamp: number[];
  private tick = 0;

  constructor(readonly capacity: number) {
    if (capacity < 2) throw new Error("SlotPool: capacity must be >= 2 (crossfade binds a pair)");
    this.slotFrame = new Array<number | null>(capacity).fill(null);
    this.stamp = new Array<number>(capacity).fill(0);
  }

  /** Slot holding this frame, or null if not resident. */
  slotOf(frame: number): number | null {
    const s = this.frameSlot.get(frame);
    return s === undefined ? null : s;
  }

  /** Mark a resident frame as recently used (call when binding it). */
  touch(frame: number): void {
    const s = this.frameSlot.get(frame);
    if (s !== undefined) this.stamp[s] = ++this.tick;
  }

  /**
   * Find a slot for `frame`: the existing one if already resident, else a
   * free slot, else evict the LRU slot whose frame is not in `keep`.
   * Returns null only if every slot is protected.
   */
  assign(frame: number, keep: ReadonlySet<number>): number | null {
    const existing = this.frameSlot.get(frame);
    if (existing !== undefined) {
      this.stamp[existing] = ++this.tick;
      return existing;
    }
    let best = -1;
    let bestStamp = Infinity;
    for (let s = 0; s < this.capacity; s++) {
      const f = this.slotFrame[s];
      if (f === null) {
        best = s;
        break;
      }
      if (!keep.has(f) && this.stamp[s] < bestStamp) {
        best = s;
        bestStamp = this.stamp[s];
      }
    }
    if (best < 0) return null;
    const old = this.slotFrame[best];
    if (old !== null) this.frameSlot.delete(old);
    this.slotFrame[best] = frame;
    this.frameSlot.set(frame, best);
    this.stamp[best] = ++this.tick;
    return best;
  }

  /** Resident frame indices (for tests/HUD). */
  resident(): number[] {
    return [...this.frameSlot.keys()];
  }

  /**
   * Forget every residency (the textures themselves are untouched, but no frame
   * is considered loaded). Used when a layer switch (slice 5b dBZ) needs the
   * sequence to re-stream so the parallel dbz plane arrives alongside each rgba
   * brick — a brief re-buffer on a diagnostic-layer toggle is acceptable.
   */
  clear(): void {
    this.slotFrame.fill(null);
    this.frameSlot.clear();
    this.stamp.fill(0);
    this.tick = 0;
  }
}
