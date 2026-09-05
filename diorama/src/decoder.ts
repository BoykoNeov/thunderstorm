// Main-thread client for decode.worker.ts: promise-per-request over a small
// pool of workers, round-robin. gzip inflation inside ONE worker is async but
// single-threaded, so a 63 MB supercell brick (~100 ms to inflate) serialized
// behind the previous one — the ring starved at 60× even though the GPU was
// idle. N workers inflate N bricks in parallel; the caller (main.ts) still
// limits how many frames are in flight. Pool size follows the machine but is
// capped: more workers than in-flight requests just idle.

interface DecodeReply {
  id: number;
  buffer?: ArrayBuffer;
  error?: string;
}

/** Worker count: half the logical cores, clamped to [1, max] (default 4). */
export function decoderPoolSize(hardwareConcurrency: number | undefined, max = 4): number {
  const cores = hardwareConcurrency && hardwareConcurrency > 0 ? hardwareConcurrency : 2;
  return Math.max(1, Math.min(max, Math.floor(cores / 2)));
}

export class BrickDecoder {
  private workers: Worker[] = [];
  private nextWorker = 0;
  private nextId = 1;
  private pending = new Map<number, { resolve: (d: Uint8Array) => void; reject: (e: Error) => void }>();

  constructor(poolSize = decoderPoolSize(navigator.hardwareConcurrency)) {
    for (let i = 0; i < poolSize; i++) {
      const w = new Worker(new URL("./decode.worker.ts", import.meta.url), { type: "module" });
      w.onmessage = (e: MessageEvent<DecodeReply>) => {
        const p = this.pending.get(e.data.id);
        if (!p) return;
        this.pending.delete(e.data.id);
        if (e.data.buffer) p.resolve(new Uint8Array(e.data.buffer));
        else p.reject(new Error(e.data.error ?? "decode failed"));
      };
      w.onerror = (e) => {
        // one worker failing fails every pending request: a partial pool
        // could otherwise leave frames waiting forever on the dead worker
        const err = new Error(`decode worker: ${e.message}`);
        for (const p of this.pending.values()) p.reject(err);
        this.pending.clear();
      };
      this.workers.push(w);
    }
  }

  get size(): number {
    return this.workers.length;
  }

  request(url: string, expectedBytes: number): Promise<Uint8Array> {
    const id = this.nextId++;
    const w = this.workers[this.nextWorker];
    this.nextWorker = (this.nextWorker + 1) % this.workers.length;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      w.postMessage({ id, url, expectedBytes });
    });
  }
}
