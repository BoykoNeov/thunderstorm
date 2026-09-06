// Scenario selection (T7) — the diorama plays ONE scenario package at a time.
//
// Which one is a startup choice, deliberately: the whole GL pipeline (the ring
// of 24 volume textures, the parallel dbz ring, the shadow caches, the volume
// box, the decode constants) is sized to the package's grid, and packages
// differ in grid — supercell_333m is 540×540×54 @ 333 m, its coarse export is
// 270×270×27 @ 666 m, single_cell_500m is 208×208×72 @ 250 m. The viewer is already grid-agnostic WITHIN one load
// (every size derives from the loaded manifest), so rather than tear down and
// rebuild every GPU resource in place, switching scenarios RELOADS the page
// with a new `?scenario=`. Every closure-captured grid constant then re-derives
// cleanly from the new manifest, with zero risk of half-updated GL state or a
// leaked texture. This matches the viewer's grain: it is URL-param-driven at
// startup already. The pure helpers here are unit-tested; the DOM/reload wiring
// lives in main.ts. Server side: the dev server maps /data/<name>/* onto
// ../scenarios/<name>/web/* and lists packages at /scenarios.json (vite.config.ts).

// One entry of the dev server's /scenarios.json discovery list. Just enough to
// label the picker honestly (grid + resolution + detail level); the
// authoritative per-package contract stays web_manifest.json, fetched only for
// the SELECTED scenario. `vite.config.ts` types its listScenarios() return as
// ScenarioSummary[] and IMPORTS this interface, so the two halves of the wire
// format cannot drift apart silently — add a field here and the server fails
// to typecheck until it emits one.
//
// The last three are optional because most packages do not have them:
// `source_run` is the CM1 run a package was exported from (two packages sharing
// one source_run are the SAME STORM at different detail), and
// source_voxel_m/decimation_factor are present only on a coarsened web export
// (pipeline: export-web --web-voxel-m). Their presence is what the label uses
// to say "lighter" vs "full detail" — a data-driven test, never a name list.
export interface ScenarioSummary {
  name: string;
  voxel_m: number;
  nx: number;
  ny: number;
  nz: number;
  frames: number;
  source_run?: string;
  source_voxel_m?: number;
  decimation_factor?: number;
}

// The package the viewer opens when the URL names none (or names one the server
// does not serve). Owner call 2026-09-06: the supercell is the showcase storm
// and the COARSE export is the default one, because it is the variant that
// streams without stalling on a modest machine; the full-detail 333 m package
// is kept and is one click away in the picker (which labels the pair "lighter"
// vs "full detail" — see scenarioLabel). Changing this does NOT break an old
// bookmark: resolveScenario honours a served `?scenario=` param over this.
export const DEFAULT_SCENARIO = "supercell_333m_coarse";

/**
 * Decide which scenario to load from the URL param and the served list.
 *
 * - a `param` the server actually serves wins (honours the user's URL);
 * - otherwise the preferred default if it is served;
 * - otherwise the first served package (alphabetical, from the server);
 * - and if discovery returned nothing (e.g. a production build with no dev
 *   middleware), fall back to the param or the default as a best effort so a
 *   single hand-placed package still loads.
 */
export function resolveScenario(
  param: string | null,
  available: string[],
  preferred: string = DEFAULT_SCENARIO,
): string {
  if (param && available.includes(param)) return param;
  if (available.includes(preferred)) return preferred;
  if (available.length > 0) return available[0];
  return param ?? preferred;
}

/** The /data root for a scenario's web files — matches the server's map. */
export function dataRoot(scenario: string): string {
  return `/data/${encodeURIComponent(scenario)}`;
}

/**
 * URL (search string) to switch to another scenario, preserving EVERY other
 * param (az/el/layer/sx/…) so a switch keeps the current view and tuning; only
 * `scenario` is set/replaced. Returned as `?a=b&…` for assignment to
 * `location.search`, which reloads.
 */
export function scenarioSwitchUrl(currentSearch: string, next: string): string {
  const p = new URLSearchParams(currentSearch);
  p.set("scenario", next);
  return `?${p.toString()}`;
}

/**
 * Do two packages show the same storm at different detail?
 *
 * They do iff they were exported from the same CM1 run (`source_run` in the web
 * manifest, which a coarsened export copies verbatim from its parent). Names
 * are NOT the test: `supercell_333m_coarse` happens to be a suffix of its
 * parent's name today, but a future coarse export could be named anything, and
 * two unrelated packages could share a prefix.
 */
export function detailSiblings(s: ScenarioSummary, all: ScenarioSummary[]): boolean {
  if (!s.source_run) return false;
  return all.some((o) => o.name !== s.name && o.source_run === s.source_run);
}

/**
 * A compact, honest picker label: name, grid, native resolution — and, WHEN AND
 * ONLY WHEN the same storm is served at more than one detail level, a
 * plain-language tag saying which one this is.
 *
 * The tag is conditional on purpose. "full detail" is a meaningless boast on a
 * package with no lighter sibling, and it would print on all four packages if
 * it keyed off `decimation_factor` alone; it is informative only where the
 * viewer is actually offering the user a choice between two renderings of one
 * storm. That is exactly the case this label exists to make evident.
 *
 * Pass `all` (the served list) to enable the tag; called with one argument the
 * label degrades to the pre-2026-09-06 form rather than guessing.
 */
export function scenarioLabel(s: ScenarioSummary, all: ScenarioSummary[] = []): string {
  const dims = `${s.nx}×${s.ny}×${s.nz}`;
  const vox = s.voxel_m > 0 ? ` @ ${Math.round(s.voxel_m)} m` : "";
  let tag = "";
  if (detailSiblings(s, all)) {
    const f = s.decimation_factor ?? 1;
    tag = f > 1 ? ` · lighter (${f}× coarser)` : " · full detail";
  }
  return `${s.name} · ${dims}${vox}${tag}`;
}
