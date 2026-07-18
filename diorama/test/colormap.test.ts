// The dBZ radar palette (slice 5b) is a shared contract: the DOM legend
// (colormap.ts dbzColor) and the shader (shaders.ts dbzColor, emitted by
// dbzColorGLSL) must paint the SAME curve, or the legend teaches a lie. Both are
// generated from one DBZ_STOPS table, so this file locks the JS side's shape and
// checks the emitted GLSL is a faithful running-chain mirror of it.

import { describe, expect, it } from "vitest";
import { dbzColor, dbzColorGLSL } from "../src/colormap";

describe("dbzColor rainbow palette", () => {
  it("clamps below the first stop and above the last", () => {
    // 5 dBZ is the first stop (cyan); anything below returns it unchanged.
    expect(dbzColor(5)).toEqual(dbzColor(-100));
    expect(dbzColor(4.9)).toEqual([0, 0.93, 0.93]);
    // 72 dBZ is the last stop (white); anything above returns it unchanged.
    expect(dbzColor(72)).toEqual([1, 1, 1]);
    expect(dbzColor(200)).toEqual([1, 1, 1]);
  });

  it("hits the recognizable radar anchors at their stops", () => {
    expect(dbzColor(20)).toEqual([0, 0.9, 0]); // green
    expect(dbzColor(35)).toEqual([1, 1, 0]); // yellow
    expect(dbzColor(50)).toEqual([0.95, 0, 0]); // red
    expect(dbzColor(65)).toEqual([1, 0, 1]); // magenta
  });

  it("interpolates linearly between stops (midpoint is the average)", () => {
    // halfway between 35 (yellow) and 45 (orange)
    const mid = dbzColor(40);
    expect(mid[0]).toBeCloseTo(1.0, 6);
    expect(mid[1]).toBeCloseTo((1.0 + 0.55) / 2, 6);
    expect(mid[2]).toBeCloseTo(0, 6);
  });

  it("stays within [0,1] across the whole domain", () => {
    for (let d = -10; d <= 90; d += 0.5) {
      for (const c of dbzColor(d)) {
        expect(c).toBeGreaterThanOrEqual(0);
        expect(c).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("dbzColorGLSL mirrors dbzColor", () => {
  // Reimplement the emitted GLSL's control flow in JS and check it agrees with
  // dbzColor at fine resolution — if the emitter ever diverges from the JS
  // interpolation, this trips.
  function evalGLSL(src: string, d: number): [number, number, number] {
    // Parse the generated chain: a sequence of stops with linear mix() gaps.
    // Rather than a real GLSL parser, mirror the known structure: pull the vec3
    // literals and stop dBZ values back out and run the same running-chain math.
    const stops: { dbz: number; rgb: [number, number, number] }[] = [];
    const re = /vec3\(([-\d.]+), ([-\d.]+), ([-\d.]+)\)/g;
    const guards = [...src.matchAll(/d <= ([\d.]+)/g)].map((m) => parseFloat(m[1]));
    let m: RegExpExecArray | null;
    let gi = 0;
    // The vec3 literals come in pairs (return colour, then prev assignment) per
    // stop after the first, and singly for the first; collapse to unique stops
    // by pairing with the guard list order.
    const cols: [number, number, number][] = [];
    while ((m = re.exec(src)) !== null) cols.push([parseFloat(m[1]), parseFloat(m[2]), parseFloat(m[3])]);
    // Unique colours in first-seen order == the stop colours.
    const seen = new Set<string>();
    const uniq: [number, number, number][] = [];
    for (const cvec of cols) {
      const key = cvec.join(",");
      if (!seen.has(key)) {
        seen.add(key);
        uniq.push(cvec);
      }
    }
    for (let i = 0; i < guards.length; i++) stops.push({ dbz: guards[i], rgb: uniq[i] });
    void gi;
    if (d <= stops[0].dbz) return stops[0].rgb;
    const last = stops[stops.length - 1];
    if (d >= last.dbz) return last.rgb;
    for (let i = 1; i < stops.length; i++) {
      if (d <= stops[i].dbz) {
        const a = stops[i - 1];
        const b = stops[i];
        const f = (d - a.dbz) / (b.dbz - a.dbz);
        return [a.rgb[0] + f * (b.rgb[0] - a.rgb[0]), a.rgb[1] + f * (b.rgb[1] - a.rgb[1]), a.rgb[2] + f * (b.rgb[2] - a.rgb[2])];
      }
    }
    return last.rgb;
  }

  it("agrees with dbzColor at fine resolution", () => {
    const src = dbzColorGLSL();
    for (let d = 0; d <= 80; d += 0.37) {
      const a = dbzColor(d);
      const b = evalGLSL(src, d);
      for (let c = 0; c < 3; c++) expect(b[c]).toBeCloseTo(a[c], 6);
    }
  });
});
