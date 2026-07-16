import { describe, expect, it } from "vitest";
import { SlotPool } from "../src/ring";

const NONE = new Set<number>();

describe("SlotPool", () => {
  it("fills free slots before evicting", () => {
    const p = new SlotPool(3);
    expect(p.assign(10, NONE)).toBe(0);
    expect(p.assign(11, NONE)).toBe(1);
    expect(p.assign(12, NONE)).toBe(2);
    expect(p.resident().sort()).toEqual([10, 11, 12]);
  });

  it("re-assigning a resident frame returns its existing slot", () => {
    const p = new SlotPool(2);
    const s = p.assign(7, NONE);
    expect(p.assign(7, NONE)).toBe(s);
    expect(p.resident()).toEqual([7]);
  });

  it("evicts the least-recently-used frame", () => {
    const p = new SlotPool(2);
    p.assign(1, NONE);
    p.assign(2, NONE);
    p.touch(1); // 2 is now LRU
    const s = p.assign(3, NONE);
    expect(p.slotOf(2)).toBeNull();
    expect(p.slotOf(1)).not.toBeNull();
    expect(p.slotOf(3)).toBe(s);
  });

  it("never evicts a protected frame", () => {
    const p = new SlotPool(2);
    p.assign(1, NONE);
    p.assign(2, NONE);
    const keep = new Set([1]);
    p.touch(2); // 1 is LRU but protected
    p.assign(3, keep);
    expect(p.slotOf(1)).not.toBeNull();
    expect(p.slotOf(2)).toBeNull();
  });

  it("returns null when every slot is protected", () => {
    const p = new SlotPool(2);
    p.assign(1, NONE);
    p.assign(2, NONE);
    expect(p.assign(3, new Set([1, 2]))).toBeNull();
    expect(p.resident().sort()).toEqual([1, 2]);
  });

  it("slotOf misses return null", () => {
    const p = new SlotPool(2);
    expect(p.slotOf(99)).toBeNull();
  });

  it("rejects capacity < 2", () => {
    expect(() => new SlotPool(1)).toThrow();
  });
});
