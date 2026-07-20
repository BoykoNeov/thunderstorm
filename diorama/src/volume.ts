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
  w?: string; // present only when the package ships the updraft field (T8)
  w_bytes?: number;
}

// Updraft `w` extra field (T8). SIGNED (blue↔red), so a distinct encoding from
// the log-uint8 hydrometeors and the linear dBZ: signed-linear-uint8, byte 128
// EXACTLY 0. `scale` is FIXED across scenarios (not fitted per sequence) — the
// colour domain is driven by it, never a per-sequence max. Feature-detected:
// `extra_fields.w` is absent in a pre-T8 package. Contract: cm1post/webvol.py.
export interface WSpec {
  file_suffix: string;
  encoding: string;
  units: string;
  diagnostic: boolean;
  scale: number;
}

export interface WebManifest {
  web_format_version: string;
  grid: { nx: number; ny: number; nz: number; voxel_m: number; origin_m: [number, number, number] };
  volume: { layout: string; channels: ChannelSpec[] };
  dbz: DbzSpec;
  extra_fields?: { w?: WSpec };
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

// -- dBZ diagnostic plane (slice 5b) ------------------------------------------
// dBZ is a SEPARATE manifest field (not in `volume.channels`) with a LINEAR
// uint8 map — it is already a log-scale quantity, so a second log would crush
// its dynamic range. Contract lives in pipeline/cm1post/webvol.py
// (encode_linear_u8): code 0 = below threshold (transparent), codes 1..255 span
// (threshold, vmax] linearly. The GLSL mirrors decodeLinearU8 in the march.

export interface DbzSpec {
  encoding: string;
  threshold: number;
  vmax: number;
  units: string;
  diagnostic: boolean;
}

/** CPU reference decode of one dBZ code (mirrors the GLSL; unit-tested). */
export function decodeLinearU8(v: number, threshold: number, vmax: number): number {
  if (v <= 0) return 0; // below threshold -> empty (NOT the palette floor)
  if (vmax <= threshold) return 0;
  return threshold + (vmax - threshold) * ((v - 1) / 254);
}

/** CPU reference encode (ports webvol.encode_linear_u8; used only by tests). */
export function encodeLinearU8(q: number, threshold: number, vmax: number): number {
  if (vmax <= threshold || q <= threshold) return 0;
  const t = (q - threshold) / (vmax - threshold);
  return Math.min(255, Math.max(1, Math.round(1 + 254 * t)));
}

// -- signed vertical velocity w (T8) ------------------------------------------
// w is SIGNED, so a symmetric map about code 128: value = (byte-128)/127*scale.
// Byte 128 is EXACTLY 0 (the updraft/downdraft boundary is exact, not rounded);
// codes 1..255 span [-scale, +scale]. Mirrors the GLSL wAt() and the encoder
// (webvol.encode_signed_u8). `scale` is the FIXED manifest scale.
export function decodeSignedU8(v: number, scale: number): number {
  return ((v - 128) / 127) * scale;
}
