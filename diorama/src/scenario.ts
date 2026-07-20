// Scenario selection (T7) — the diorama plays ONE scenario package at a time.
//
// Which one is a startup choice, deliberately: the whole GL pipeline (the ring
// of 24 volume textures, the parallel dbz ring, the shadow caches, the volume
// box, the decode constants) is sized to the package's grid, and packages
// differ in grid — single_cell_500m is 208×208×72 @ 250 m, single_cell_333m is
// 126×126×54 @ 333 m. The viewer is already grid-agnostic WITHIN one load
// (every size derives from the loaded manifest), so rather than tear down and
// rebuild every GPU resource in place, switching scenarios RELOADS the page
// with a new `?scenario=`. Every closure-captured grid constant then re-derives
// cleanly from the new manifest, with zero risk of half-updated GL state or a
// leaked texture. This matches the viewer's grain: it is URL-param-driven at
// startup already. The pure helpers here are unit-tested; the DOM/reload wiring
// lives in main.ts. Server side: the dev server maps /data/<name>/* onto
// ../scenarios/<name>/web/* and lists packages at /scenarios.json (vite.config.ts).

// One entry of the dev server's /scenarios.json discovery list. Just enough to
// label the picker honestly (grid + resolution); the authoritative per-package
// contract stays web_manifest.json, fetched only for the SELECTED scenario.
export interface ScenarioSummary {
  name: string;
  voxel_m: number;
  nx: number;
  ny: number;
  nz: number;
  frames: number;
}

// The package the viewer falls back to when the URL names none (or names one
// the server does not serve). single_cell_500m is the Phase 1 dataset and the
// historical default DATA_DIR, so an old bookmarked URL keeps its storm.
export const DEFAULT_SCENARIO = "single_cell_500m";

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

/** A compact, honest picker label: name plus grid and native resolution. */
export function scenarioLabel(s: ScenarioSummary): string {
  const dims = `${s.nx}×${s.ny}×${s.nz}`;
  const vox = s.voxel_m > 0 ? ` @ ${Math.round(s.voxel_m)} m` : "";
  return `${s.name} · ${dims}${vox}`;
}
