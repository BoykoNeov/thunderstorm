import { describe, expect, it } from "vitest";
import { advance, locate, wantedFrames } from "../src/playback";

// the real manifest: 301 frames, 12 s apart, 0..3600 s
const TIMES = Array.from({ length: 301 }, (_, i) => i * 12);

describe("locate", () => {
  it("hits exact frame stamps with f = 0", () => {
    for (const i of [0, 1, 150, 299]) {
      expect(locate(TIMES, i * 12)).toEqual({ i0: i, i1: i + 1, f: 0 });
    }
  });

  it("interpolates between stamps", () => {
    const p = locate(TIMES, 150 * 12 + 3);
    expect(p.i0).toBe(150);
    expect(p.i1).toBe(151);
    expect(p.f).toBeCloseTo(0.25, 12);
  });

  it("clamps below and above the range", () => {
    expect(locate(TIMES, -5)).toEqual({ i0: 0, i1: 1, f: 0 });
    expect(locate(TIMES, 3600)).toEqual({ i0: 300, i1: 300, f: 0 });
    expect(locate(TIMES, 1e9)).toEqual({ i0: 300, i1: 300, f: 0 });
  });

  it("is consistent across every frame boundary", () => {
    for (let i = 0; i < 300; i++) {
      const p = locate(TIMES, i * 12 + 6);
      expect(p.i0).toBe(i);
      expect(p.i1).toBe(i + 1);
      expect(p.f).toBeCloseTo(0.5, 12);
    }
  });

  it("handles non-uniform spacing", () => {
    const t = [0, 10, 40, 100];
    expect(locate(t, 25).i0).toBe(1);
    expect(locate(t, 25).f).toBeCloseTo(0.5, 12);
    expect(locate(t, 70).i0).toBe(2);
    expect(locate(t, 70).f).toBeCloseTo(0.5, 12);
  });

  it("single frame degenerates safely", () => {
    expect(locate([42], 42)).toEqual({ i0: 0, i1: 0, f: 0 });
    expect(locate([42], 100)).toEqual({ i0: 0, i1: 0, f: 0 });
  });
});

describe("advance", () => {
  it("moves forward within the range", () => {
    expect(advance(100, 12, 0, 3600)).toBe(112);
  });

  it("wraps at the end (loop)", () => {
    expect(advance(3595, 10, 0, 3600)).toBeCloseTo(5, 12);
  });

  it("wraps multiple spans", () => {
    expect(advance(0, 3600 * 2 + 7, 0, 3600)).toBeCloseTo(7, 9);
  });

  it("zero dt is identity", () => {
    expect(advance(1234, 0, 0, 3600)).toBe(1234);
  });

  it("never returns t1 itself", () => {
    expect(advance(3588, 12, 0, 3600)).toBe(0);
  });
});

describe("wantedFrames", () => {
  it("is the pair plus the read-ahead window", () => {
    expect(wantedFrames(10, 3, 301)).toEqual([10, 11, 12, 13, 14]);
  });

  it("wraps at the sequence end (playback loops)", () => {
    expect(wantedFrames(299, 3, 301)).toEqual([299, 300, 0, 1, 2]);
  });

  it("never exceeds the frame count and never repeats", () => {
    const w = wantedFrames(1, 10, 4);
    expect(w).toEqual([1, 2, 3, 0]);
  });
});
