import { describe, expect, it } from "vitest";
import {
  DEFAULT_SCENARIO,
  dataRoot,
  detailSiblings,
  resolveScenario,
  scenarioLabel,
  scenarioSwitchUrl,
  type ScenarioSummary,
} from "../src/scenario";

describe("resolveScenario", () => {
  const list = ["single_cell_333m", "single_cell_500m", "supercell_333m", "supercell_333m_coarse"];

  it("honours a URL param the server actually serves", () => {
    expect(resolveScenario("single_cell_333m", list)).toBe("single_cell_333m");
  });

  it("falls back to the preferred default when the param names nothing served", () => {
    expect(resolveScenario("does_not_exist", list)).toBe(DEFAULT_SCENARIO);
    expect(resolveScenario(null, list)).toBe(DEFAULT_SCENARIO);
  });

  // The owner call this default encodes: open on the COARSE supercell. Asserted
  // by name and not merely via DEFAULT_SCENARIO, so that silently repointing the
  // constant at another package fails here instead of passing tautologically.
  it("opens on the coarse supercell, and a bookmark still overrides it", () => {
    expect(DEFAULT_SCENARIO).toBe("supercell_333m_coarse");
    expect(resolveScenario(null, list)).toBe("supercell_333m_coarse");
    expect(resolveScenario("supercell_333m", list)).toBe("supercell_333m");
    expect(resolveScenario("single_cell_500m", list)).toBe("single_cell_500m");
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

  // --- detail-level tag (2026-09-06): the point of the whole change is that a
  // user can SEE which of the two supercells is which, so assert the exact
  // strings that reach the dropdown, not just that a tag is present.
  const nat = s({
    name: "supercell_333m", voxel_m: 333, nx: 540, ny: 540, nz: 54, frames: 601,
    source_run: "/home/boiko/thunderstorm/runs/supercell333",
  });
  const crs = s({
    name: "supercell_333m_coarse", voxel_m: 666, nx: 270, ny: 270, nz: 27, frames: 601,
    source_run: "/home/boiko/thunderstorm/runs/supercell333",
    source_voxel_m: 333, decimation_factor: 2,
  });
  const other = s({ source_run: "/home/boiko/thunderstorm/runs/singlecell" });
  const all = [other, nat, crs];

  it("tags a same-storm pair so the choice is legible", () => {
    expect(scenarioLabel(crs, all))
      .toBe("supercell_333m_coarse · 270×270×27 @ 666 m · lighter (2× coarser)");
    expect(scenarioLabel(nat, all))
      .toBe("supercell_333m · 540×540×54 @ 333 m · full detail");
  });

  it("stays silent for a package with no sibling at another detail level", () => {
    // "full detail" is a boast with nothing to contrast against; it must not
    // print on the single-cell packages just because they are un-decimated.
    expect(scenarioLabel(other, all)).toBe("single_cell_500m · 208×208×72 @ 250 m");
    expect(scenarioLabel(nat, [nat])).toBe("supercell_333m · 540×540×54 @ 333 m");
  });

  it("degrades to the untagged form when the list is not passed", () => {
    expect(scenarioLabel(crs)).toBe("supercell_333m_coarse · 270×270×27 @ 666 m");
  });
});

describe("detailSiblings", () => {
  const mk = (name: string, run?: string): ScenarioSummary =>
    ({ name, voxel_m: 333, nx: 1, ny: 1, nz: 1, frames: 1, source_run: run });

  it("pairs by source run, not by name", () => {
    const a = mk("supercell_333m", "runs/supercell333");
    const b = mk("anything_at_all", "runs/supercell333");
    expect(detailSiblings(a, [a, b])).toBe(true);
    // a shared NAME prefix is not a pairing: different runs are different storms
    const c = mk("supercell_333m_v2", "runs/other");
    expect(detailSiblings(a, [a, c])).toBe(false);
  });

  it("is false for a package the server reported no source run for", () => {
    const a = mk("legacy_package", undefined);
    const b = mk("also_legacy", undefined);
    // two unknowns must NOT match each other into a bogus pair
    expect(detailSiblings(a, [a, b])).toBe(false);
  });

  it("does not pair a package with itself", () => {
    const a = mk("only_one", "runs/x");
    expect(detailSiblings(a, [a])).toBe(false);
  });
});
