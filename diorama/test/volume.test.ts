// The quantization contract: the TS decode must invert the pipeline's encoder
// (pipeline/cm1post/webvol.py) within the log-step error bound. encodeLogU8
// here is a line-for-line port of the Python; if either side changes, this
// file is the tripwire.

import { describe, expect, it } from "vitest";
import {
  decodeConstants,
  decodeLinearU8,
  decodeLogU8,
  decodeSignedU8,
  encodeLinearU8,
  encodeLogU8,
} from "../src/volume";

const THR = 1e-4; // config.THRESHOLDS for every mixing-ratio channel
const QMAX = 0.01245; // measured graupelhail max over the real sequence

describe("log-uint8 quantization round trip", () => {
  it("zero and below-threshold values encode to code 0 and decode to 0", () => {
    expect(encodeLogU8(0, THR, QMAX)).toBe(0);
    expect(encodeLogU8(THR * 0.999, THR, QMAX)).toBe(0);
    expect(decodeLogU8(0, THR, QMAX)).toBe(0);
  });

  it("endpoints map to the endpoint codes", () => {
    // just above threshold -> code 1 -> decodes to the threshold itself
    expect(encodeLogU8(THR * 1.0001, THR, QMAX)).toBe(1);
    expect(decodeLogU8(1, THR, QMAX)).toBeCloseTo(THR, 12);
    expect(encodeLogU8(QMAX, THR, QMAX)).toBe(255);
    expect(decodeLogU8(255, THR, QMAX)).toBeCloseTo(QMAX, 12);
  });

  it("round-trip relative error is bounded by half a log step", () => {
    // codes are uniform in log(q); rounding moves q by at most half a step
    const halfStep = Math.pow(QMAX / THR, 0.5 / 254) - 1;
    for (let i = 0; i < 2000; i++) {
      // strictly above threshold: q <= threshold is culled to code 0 by contract
      const q = THR * Math.pow(QMAX / THR, (i + 1) / 2000);
      const rt = decodeLogU8(encodeLogU8(q, THR, QMAX), THR, QMAX);
      expect(Math.abs(rt - q) / q).toBeLessThanOrEqual(halfStep * 1.0001);
    }
  });

  it("decode is monotone in the code value", () => {
    let prev = 0;
    for (let v = 1; v <= 255; v++) {
      const q = decodeLogU8(v, THR, QMAX);
      expect(q).toBeGreaterThan(prev);
      prev = q;
    }
  });

  it("degenerate channel (qmax <= threshold) is all-zero both ways", () => {
    expect(encodeLogU8(0.5, THR, THR)).toBe(0);
    expect(decodeLogU8(200, THR, THR)).toBe(0);
  });
});

// dBZ (slice 5b): a LINEAR uint8 map over (threshold, vmax]. Separate contract
// from the log channels — the shipped manifest's real numbers below.
const DBZ_THR = 5.0;
const DBZ_MAX = 72.21371459960938;

describe("linear-uint8 dBZ quantization round trip", () => {
  it("zero and below-threshold values encode to code 0 and decode to 0", () => {
    expect(encodeLinearU8(0, DBZ_THR, DBZ_MAX)).toBe(0);
    expect(encodeLinearU8(DBZ_THR, DBZ_THR, DBZ_MAX)).toBe(0); // q <= thr culled
    expect(encodeLinearU8(DBZ_THR * 0.999, DBZ_THR, DBZ_MAX)).toBe(0);
    // decode of code 0 is EMPTY air, never the palette floor (5 dBZ)
    expect(decodeLinearU8(0, DBZ_THR, DBZ_MAX)).toBe(0);
  });

  it("endpoints map to the endpoint codes", () => {
    expect(encodeLinearU8(DBZ_THR * 1.0001, DBZ_THR, DBZ_MAX)).toBe(1);
    expect(decodeLinearU8(1, DBZ_THR, DBZ_MAX)).toBeCloseTo(DBZ_THR, 10);
    expect(encodeLinearU8(DBZ_MAX, DBZ_THR, DBZ_MAX)).toBe(255);
    expect(decodeLinearU8(255, DBZ_THR, DBZ_MAX)).toBeCloseTo(DBZ_MAX, 10);
  });

  it("round-trip absolute error is bounded by half a linear step", () => {
    const halfStep = (DBZ_MAX - DBZ_THR) * (0.5 / 254);
    for (let i = 0; i < 2000; i++) {
      const q = DBZ_THR + (DBZ_MAX - DBZ_THR) * ((i + 1) / 2000);
      const rt = decodeLinearU8(encodeLinearU8(q, DBZ_THR, DBZ_MAX), DBZ_THR, DBZ_MAX);
      expect(Math.abs(rt - q)).toBeLessThanOrEqual(halfStep * 1.0001);
    }
  });

  it("decode is monotone in the code value", () => {
    let prev = 0;
    for (let v = 1; v <= 255; v++) {
      const q = decodeLinearU8(v, DBZ_THR, DBZ_MAX);
      expect(q).toBeGreaterThan(prev);
      prev = q;
    }
  });

  it("degenerate plane (vmax <= threshold) is all-zero both ways", () => {
    expect(encodeLinearU8(50, DBZ_THR, DBZ_THR)).toBe(0);
    expect(decodeLinearU8(200, DBZ_THR, DBZ_THR)).toBe(0);
  });
});

// Updraft w (T8): SIGNED, symmetric about code 128. The one property that
// makes the updraft/downdraft boundary honest is that code 128 is EXACTLY 0 —
// not a fractional value that would paint false vertical motion along the zero
// line. `scale` is the FIXED manifest value (80 m/s), constant across scenarios.
const W_SCALE = 80.0;

// A line-for-line port of the encoder (webvol.encode_signed_u8) for round-trip
// checks: v = clip(round(128 + 127*clip(w,-s,s)/s), 0, 255).
function encodeSignedU8(w: number, scale: number): number {
  const ww = Math.max(-scale, Math.min(scale, w));
  return Math.max(0, Math.min(255, Math.round(128 + (127 * ww) / scale)));
}

describe("signed-uint8 w quantization", () => {
  it("code 128 decodes to EXACTLY zero (no false motion at the boundary)", () => {
    expect(decodeSignedU8(128, W_SCALE)).toBe(0);
    expect(encodeSignedU8(0, W_SCALE)).toBe(128);
  });

  it("the code ends span the full ±scale", () => {
    expect(decodeSignedU8(255, W_SCALE)).toBeCloseTo(W_SCALE, 12); // (255-128)/127 = 1
    expect(decodeSignedU8(1, W_SCALE)).toBeCloseTo(-W_SCALE, 12); // (1-128)/127 = -1
    // the encoder saturates beyond ±scale rather than wrapping
    expect(encodeSignedU8(200, W_SCALE)).toBe(255);
    expect(encodeSignedU8(-200, W_SCALE)).toBe(1);
  });

  it("is antisymmetric about zero: decode(128+n) == -decode(128-n)", () => {
    for (let n = 1; n <= 127; n++) {
      expect(decodeSignedU8(128 + n, W_SCALE)).toBeCloseTo(-decodeSignedU8(128 - n, W_SCALE), 12);
    }
  });

  it("round-trip error is within half a quantum (scale/127)", () => {
    const halfStep = W_SCALE / 127 / 2;
    for (let i = 0; i <= 400; i++) {
      const w = -W_SCALE + (2 * W_SCALE * i) / 400;
      const rt = decodeSignedU8(encodeSignedU8(w, W_SCALE), W_SCALE);
      expect(Math.abs(rt - w)).toBeLessThanOrEqual(halfStep * 1.0001);
    }
  });
});

// Composite reflectivity cref (T9): the RADAR PLAN VIEW. Its whole design rests
// on one measured identity — CM1's cref is bitwise dbz.max(axis=0), so the plan
// field ships the SAME (threshold, vmax) as the 3D dbz layer and decodes with the
// SAME linear map. That is what lets one NWS colormap serve both radar views
// exactly (one byte ⇒ one dBZ in both). These tests are the viewer-side tripwire
// for that: cref is decoded with decodeLinearU8 (the dbz decoder), never the log
// map, and matches dbz code-for-code when the scales agree.
describe("cref plan field shares the dbz linear decode (T9)", () => {
  it("uses the LINEAR map, not the log map the hydrometeors use", () => {
    // The real viewer-side bug risk is decoding cref with decodeLogU8 (a
    // copy-paste from the hydrometeor path). A mid code must land at the LINEAR
    // midpoint of (threshold, vmax], distinctly not the log one.
    const mid = decodeLinearU8(128, DBZ_THR, DBZ_MAX);
    expect(mid).toBeCloseTo(DBZ_THR + (DBZ_MAX - DBZ_THR) * (127 / 254), 10);
    expect(mid).not.toBeCloseTo(decodeLogU8(128, DBZ_THR, DBZ_MAX), 2);
  });

  it("code 0 is no-echo (transparent), code 1 is the threshold", () => {
    // the shader's `v > 0.5` gate: below-threshold columns paint nothing so the
    // toy ground shows through, exactly like the dbz plane. Never the 5 dBZ floor.
    expect(decodeLinearU8(0, DBZ_THR, DBZ_MAX)).toBe(0);
    expect(decodeLinearU8(1, DBZ_THR, DBZ_MAX)).toBeCloseTo(DBZ_THR, 10);
  });

  it("the shared-scale identity is load-bearing: decode is sensitive to vmax", () => {
    // cref shares dbz's (threshold, vmax) so one colormap serves both EXACTLY.
    // That equality only means something because the decode genuinely depends on
    // vmax — if a future ptype broke CM1's cref==dbz.max identity and shipped a
    // different vmax, the same byte would read as a different dBZ. The exporter's
    // standing check (webvol §15.6) is what forbids that; this shows the
    // dependence is real, so sharing the scale is not an incidental no-op.
    expect(decodeLinearU8(200, DBZ_THR, DBZ_MAX)).not.toBeCloseTo(
      decodeLinearU8(200, DBZ_THR, DBZ_MAX * 0.8),
      3,
    );
  });
});

describe("decodeConstants", () => {
  it("reproduces q = thr * exp(k * (v - 1)) matching decodeLogU8", () => {
    const ch = [
      { name: "cloud", plane: 0, encoding: "log-uint8" as const, threshold: THR, qmax: 0.008356, units: "kg/kg" },
      { name: "graupelhail", plane: 1, encoding: "log-uint8" as const, threshold: THR, qmax: QMAX, units: "kg/kg" },
    ];
    const { thr, k } = decodeConstants(ch);
    for (const [plane, spec] of ch.entries()) {
      for (const v of [1, 77, 200, 255]) {
        const viaConstants = thr[plane] * Math.exp(k[plane] * (v - 1));
        expect(viaConstants).toBeCloseTo(decodeLogU8(v, spec.threshold, spec.qmax), 10);
      }
    }
  });
});
