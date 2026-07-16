// The quantization contract: the TS decode must invert the pipeline's encoder
// (pipeline/cm1post/webvol.py) within the log-step error bound. encodeLogU8
// here is a line-for-line port of the Python; if either side changes, this
// file is the tripwire.

import { describe, expect, it } from "vitest";
import { decodeConstants, decodeLogU8, encodeLogU8 } from "../src/volume";

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
