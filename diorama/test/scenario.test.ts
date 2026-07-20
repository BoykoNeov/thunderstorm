import { describe, expect, it } from "vitest";
import {
  DEFAULT_SCENARIO,
  dataRoot,
  resolveScenario,
  scenarioLabel,
  scenarioSwitchUrl,
  type ScenarioSummary,
} from "../src/scenario";

describe("resolveScenario", () => {
  const list = ["single_cell_333m", "single_cell_500m"];

  it("honours a URL param the server actually serves", () => {
    expect(resolveScenario("single_cell_333m", list)).toBe("single_cell_333m");
  });

  it("falls back to the preferred default when the param names nothing served", () => {
    expect(resolveScenario("does_not_exist", list)).toBe("single_cell_500m");
    expect(resolveScenario(null, list)).toBe("single_cell_500m");
  });

  it("falls back to the first served package when the default is absent", () => {
    // alphabetical order from the server; 333m sorts first
    expect(resolveScenario(null, ["single_cell_333m", "zzz"])).toBe("single_cell_333m");
    expect(resolveScenario("nope", ["single_cell_333m", "zzz"])).toBe("single_cell_333m");
  });

  it("best-effort loads when discovery returned nothing (no dev middleware)", () => {
    // a hand-placed package still loads: param wins, else the compiled default
    expect(resolveScenario("hand_placed", [])).toBe("hand_placed");
    expect(resolveScenario(null, [])).toBe(DEFAULT_SCENARIO);
  });
});

describe("scenarioSwitchUrl", () => {
  it("sets scenario while preserving every other param (view survives a switch)", () => {
    const out = scenarioSwitchUrl("?az=90&el=20&layer=dbz", "single_cell_333m");
    const p = new URLSearchParams(out);
    expect(p.get("scenario")).toBe("single_cell_333m");
    expect(p.get("az")).toBe("90");
    expect(p.get("el")).toBe("20");
    expect(p.get("layer")).toBe("dbz");
  });

  it("replaces an existing scenario param rather than appending a second", () => {
    const out = scenarioSwitchUrl("?scenario=single_cell_500m&sx=2", "single_cell_333m");
    const p = new URLSearchParams(out);
    expect(p.getAll("scenario")).toEqual(["single_cell_333m"]);
    expect(p.get("sx")).toBe("2");
  });

  it("works from an empty search string", () => {
    expect(scenarioSwitchUrl("", "single_cell_500m")).toBe("?scenario=single_cell_500m");
  });
});

describe("dataRoot", () => {
  it("matches the server's /data/<name>/ map", () => {
    expect(dataRoot("single_cell_500m")).toBe("/data/single_cell_500m");
  });

  it("percent-encodes anything unusual (defensive; real names are plain)", () => {
    expect(dataRoot("a b")).toBe("/data/a%20b");
  });
});

describe("scenarioLabel", () => {
  const s = (o: Partial<ScenarioSummary>): ScenarioSummary => ({
    name: "single_cell_500m", voxel_m: 250, nx: 208, ny: 208, nz: 72, frames: 301, ...o,
  });

  it("shows name, grid and native resolution", () => {
    expect(scenarioLabel(s({}))).toBe("single_cell_500m · 208×208×72 @ 250 m");
    expect(scenarioLabel(s({ name: "single_cell_333m", voxel_m: 333, nx: 126, ny: 126, nz: 54 })))
      .toBe("single_cell_333m · 126×126×54 @ 333 m");
  });

  it("omits the resolution when voxel size is unknown", () => {
    expect(scenarioLabel(s({ voxel_m: 0 }))).toBe("single_cell_500m · 208×208×72");
  });
});
