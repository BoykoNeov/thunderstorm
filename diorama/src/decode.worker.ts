// Brick decode worker: fetch + gunzip off the main thread, so playback never
// blocks on network or DecompressionStream. The decoded buffer transfers back
// zero-copy.

import { loadBrick } from "./volume";

interface DecodeRequest {
  id: number;
  url: string;
  expectedBytes: number;
}

self.onmessage = (e: MessageEvent<DecodeRequest>) => {
  const { id, url, expectedBytes } = e.data;
  loadBrick(url, expectedBytes)
    .then((data) => {
      (self as unknown as Worker).postMessage({ id, buffer: data.buffer }, [data.buffer]);
    })
    .catch((err: unknown) => {
      (self as unknown as Worker).postMessage({ id, error: String(err) });
    });
};
