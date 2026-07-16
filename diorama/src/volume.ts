// Scenario web-package reader: web_manifest.json + gzipped uint8 bricks.
//
// The manifest is the whole format contract (written by
// pipeline/cm1post/webvol.py). Decode of the log-uint8 quantization is
// mirrored here on the CPU purely so it can be unit-tested against the
// encoder's definition; the GPU does the same math in the shader.

export interface ChannelSpec {
  name: string;
  plane: number;
  encoding: "log-uint8";
  threshold: number;
  qmax: number;
  units: string;
}

export interface FrameRecord {
  index: number;
  time_s: number;
  rgba: string;
  dbz: string;
  rgba_bytes: number;
  dbz_bytes: number;
}

export interface WebManifest {
  web_format_version: string;
  grid: { nx: number; ny: number; nz: number; voxel_m: number; origin_m: [number, number, number] };
  volume: { layout: string; channels: ChannelSpec[] };
  dbz: { encoding: string; threshold: number; vmax: number; diagnostic: boolean };
  frames: FrameRecord[];
}

const SUPPORTED_MAJOR = 1;

export async function loadManifest(url: string): Promise<WebManifest> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`manifest fetch failed: ${res.status} ${url}`);
  const man = (await res.json()) as WebManifest;
  const major = parseInt(man.web_format_version.split(".")[0], 10);
  if (major > SUPPORTED_MAJOR) {
    throw new Error(`web_format_version ${man.web_format_version} is newer than this viewer (${SUPPORTED_MAJOR}.x)`);
  }
  return man;
}

/** Fetch one gzipped brick and inflate it (native DecompressionStream). */
export async function loadBrick(url: string, expectedBytes: number): Promise<Uint8Array> {
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`brick fetch failed: ${res.status} ${url}`);
  const stream = res.body.pipeThrough(new DecompressionStream("gzip"));
  const buf = await new Response(stream).arrayBuffer();
  if (buf.byteLength !== expectedBytes) {
    throw new Error(`brick ${url}: ${buf.byteLength} bytes, expected ${expectedBytes}`);
  }
  return new Uint8Array(buf);
}

/**
 * Per-channel decode constants for the shader:
 *   q(v) = threshold * exp(k * (v - 1))   for code v in 1..255, else 0
 * where k = ln(qmax/threshold) / 254. (Definition: pipeline/cm1post/webvol.py.)
 */
export function decodeConstants(channels: ChannelSpec[]): { thr: number[]; k: number[] } {
  const thr = channels.map((c) => c.threshold);
  const k = channels.map((c) => (c.qmax > c.threshold ? Math.log(c.qmax / c.threshold) / 254 : 0));
  return { thr, k };
}

/** CPU reference decode of one code value (mirrors the GLSL; unit-tested). */
export function decodeLogU8(v: number, threshold: number, qmax: number): number {
  if (v <= 0) return 0;
  if (qmax <= threshold) return 0;
  const k = Math.log(qmax / threshold) / 254;
  return threshold * Math.exp(k * (v - 1));
}

/** CPU reference encode (ports webvol.encode_log_u8; used only by tests). */
export function encodeLogU8(q: number, threshold: number, qmax: number): number {
  if (qmax <= threshold || q <= threshold) return 0;
  const t = Math.log(q / threshold) / Math.log(qmax / threshold);
  return Math.min(255, Math.max(1, Math.round(1 + 254 * t)));
}
