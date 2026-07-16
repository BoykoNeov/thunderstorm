// Main-thread client for decode.worker.ts: promise-per-request over a single
// worker. gzip inflation is stream-async inside the worker, so one worker
// overlaps many requests; the caller (main.ts) limits how many frames are in
// flight.

interface DecodeReply {
  id: number;
  buffer?: ArrayBuffer;
  error?: string;
}

export class BrickDecoder {
  private worker: Worker;
  private nextId = 1;
  private pending = new Map<number, { resolve: (d: Uint8Array) => void; reject: (e: Error) => void }>();

  constructor() {
    this.worker = new Worker(new URL("./decode.worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (e: MessageEvent<DecodeReply>) => {
      const p = this.pending.get(e.data.id);
      if (!p) return;
      this.pending.delete(e.data.id);
      if (e.data.buffer) p.resolve(new Uint8Array(e.data.buffer));
      else p.reject(new Error(e.data.error ?? "decode failed"));
    };
    this.worker.onerror = (e) => {
      const err = new Error(`decode worker: ${e.message}`);
      for (const p of this.pending.values()) p.reject(err);
      this.pending.clear();
    };
  }

  request(url: string, expectedBytes: number): Promise<Uint8Array> {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.worker.postMessage({ id, url, expectedBytes });
    });
  }
}
