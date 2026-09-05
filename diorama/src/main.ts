// Storm Diorama — slice 3: diorama staging. Three passes per frame: the
// low-poly countryside slab rasterizes into a G-buffer; the fullscreen
// composite raymarches the storm volume over it (the storm's shadow march
// darkens the toy landscape) against a pastel backdrop; a tilt-shift pass
// finishes the miniature read. Streaming playback is slice 2, unchanged: a
// decode worker inflates gzipped bricks off the main thread; a ring of 3D
// textures streams ahead of the play head (≤1 upload per rAF); the shader
// crossfades the two frames bracketing fractional storm time.
// Design: docs/design-diorama-web-viewer-2026-07-16.md §2, §4, §5.2, slice 3.

import { ACC_CAP, jitterSeq, nextCount, sameView, type ViewKey } from "./accum";
import { AutoScaler } from "./autoscale";
import {
  basis,
  clampOrbit,
  direction,
  kmPerPixel,
  panAltitude,
  panGround,
  type OrbitState,
} from "./camera";
import { cssGradientStops, dbzCssGradientStops, wCssGradientStops } from "./colormap";
import { BrickDecoder } from "./decoder";
import {
  compileProgram,
  createColorTarget,
  createCrefTexture,
  createDbzTexture,
  createGBuffer,
  createInstancedVAO,
  createMeshVAO,
  createNoiseTexture,
  createShadowCacheTexture,
  createVolumeTexture,
  drawFullscreen,
  getGL,
  uploadCref,
  uploadDbz,
  uploadVolume,
  uploadVolumeSlab,
  type ColorTarget,
  type GBuffer,
} from "./gl";
import { planRing, RING_BUDGET_BYTES, uploadSlabs } from "./budget";
import { GpuTimer } from "./gputimer";
import { buildStaging, GROUND_HALF } from "./land";
import { buildNoise3D, NOISE_SIZE } from "./noise3d";
import { multiply, perspective, project, view } from "./mat";
import { advance, locate, wantedFrames } from "./playback";
import { buildPrecipInstances, HAIL, RAIN, type PrecipSpec } from "./precip";
import { niceScaleBar } from "./scalebar";
import { SlotPool } from "./ring";
import {
  dataRoot,
  resolveScenario,
  scenarioLabel,
  scenarioSwitchUrl,
  type ScenarioSummary,
} from "./scenario";
import { volumeBox } from "./scene";
import { decodeConstants, loadManifest, type WebManifest } from "./volume";
import { BAKE_FRAG, FRAG, FXAA_FRAG, GEO_FRAG, GEO_VERT, POST_FRAG, PRECIP_FRAG, PRECIP_VERT, VERT } from "./shaders";

// Extinction weights per species — the numbers proven in the UE material
// (docs/phase1-svt-custom-material-2026-07-16.md), so both axes read alike.
const WEIGHTS = { cloud: 1.0, ice: 0.1, rain: 0.02, graupelhail: 0.005 };
// km^-1 per weighted (kg/kg): 2000 → σ ≈ 10/km in a 5 g/kg core (opaque within
// ~0.5 km) while the ~0.1 g/kg anvil edge stays translucent. Tuned by eye.
const EXT_SCALE = 2000.0;

// Side-lit relative to the default camera (az 45°): one flank in sun, one in
// shade — that ratio is what makes the cauliflower read as 3D.
const SUN = direction((100 * Math.PI) / 180, (40 * Math.PI) / 180);

// Streaming envelope. The ring, not full residency, is the design (must work
// on lesser GPUs too). Slot count + read-ahead come from a GPU byte budget
// (budget.ts planRing): 24 slots × 12.5 MB for the 208³-class bricks ≈ 300 MB,
// fewer for the 63 MB supercell bricks (which would otherwise pin 1.5 GB).
// Capacity must comfortably exceed the protected window (read-ahead + 2 wanted
// + 2 last-bound): texSubImage3D into a texture the GPU drew from moments ago
// forces a driver sync-wait (measured 50–77 ms spikes with only 2 rotating
// slots); ~10 rotating slots keep every upload ~1–2 ms. ?vram=MB overrides.
// One texSubImage3D call blocks the main thread for the whole copy; bricks
// bigger than this are uploaded as z-slabs over consecutive rAFs (budget.ts
// uploadSlabs). 16 MB keeps the 12.5 MB Phase-1 brick on the single-call path.
const UPLOAD_CHUNK_BYTES = 16 * 1024 * 1024;
const MAX_INFLIGHT = 4; // concurrent fetch+gunzip requests in the worker

// Mesh-pass projection planes (rays are generated analytically; these only
// bound the depth buffer — see mat.ts round-trip test).
const NEAR = 0.2; // km
const FAR = 700; // km

const canvas = document.getElementById("view") as HTMLCanvasElement;
const hud = document.getElementById("hud") as HTMLDivElement;
const errBox = document.getElementById("err") as HTMLDivElement;
const bar = document.getElementById("bar") as HTMLDivElement;
const playBtn = document.getElementById("play") as HTMLButtonElement;
const speedSel = document.getElementById("speed") as HTMLSelectElement;
const fpsInput = document.getElementById("fps") as HTMLInputElement;
const scrub = document.getElementById("scrub") as HTMLInputElement;
const clockEl = document.getElementById("clock") as HTMLSpanElement;
const scenarioSel = document.getElementById("scenario") as HTMLSelectElement;
const sbBox = document.getElementById("scalebar") as HTMLDivElement;
const sbRule = document.getElementById("sbRule") as HTMLDivElement;
const sbLabel = document.getElementById("sbLabel") as HTMLDivElement;
const statsEl = document.getElementById("stats") as HTMLDivElement;

const params = new URLSearchParams(location.search);
// render scale: the quality/fps lever (cost ∝ pixels). ?rs=auto holds the fps
// cap by moving the scale between 0.5 and 1 from the measured frame cost
// (autoscale.ts) — the lesser-GPU mode; a number pins it (rs=2 supersamples).
const rsParam = params.get("rs") ?? "1";
const rsAuto = rsParam === "auto";
let renderScale = rsAuto ? 1 : Number(rsParam) || 1;
const collectStats = params.has("stats");
// GPU byte budget for the rgba ring (?vram=MB; see the streaming envelope above)
const vramMB = Number(params.get("vram"));
const ringBudget = Number.isFinite(vramMB) && vramMB > 0 ? Math.max(64, vramMB) * 1024 * 1024 : RING_BUDGET_BYTES;
// march step budgets (perf instruments; the defaults ARE the shipped look):
// ?steps= primary march samples per ray (uSteps), ?sun= secondary sun-march
// samples per primary sample. Exposed so a cost breakdown can be measured
// without editing the shader — never lower the defaults from a single probe.
// ?debug=cost paints a per-pixel sun-march sample count heat map (perf diagnostic)
const debugMode = params.get("debug") === "cost" ? 1 : 0;
// march start-offset dither: `ign` = interleaved gradient noise (Jimenez 2014,
// a structured screen-space pattern whose residue is high-frequency and reads
// as fine grain), `hash` = the white-noise hash the viewer shipped with. Both
// average to the same converged still under idle accumulation.
const ditherIgn = (params.get("dither") ?? "ign") !== "hash";
// ?step=: primary-march step-length floor in DISPLAY km (0 = the fixed-count
// march the viewer shipped with). `auto` (default) = the longest in-box ray's
// step at uSteps (box horizontal extent / steps), so no ray samples coarser
// than the shipped worst case while short rays stop spending 280 samples on a
// few km: march −38 % on the hero frame, A/B mean difference 1/255 over 1–8 %
// of pixels (jitter-level; captures in the 2026-09-05 perf record).
const stepParam = params.get("step") ?? "auto";
const stepsParam = Math.min(512, Math.max(8, Math.round(Number(params.get("steps") ?? "280") || 280)));
const sunSteps = Math.min(64, Math.max(2, Math.round(Number(params.get("sun") ?? "28") || 28)));
const stagingSeed = Number(params.get("seed") ?? "1337") || 1337;
const tiltShift = params.get("ts") !== "0"; // ?ts=0 disables the DOF pass
// FXAA on the final LDR image (beauty step 5): de-jaggies the aliased staging
// silhouettes (the G-buffer has no MSAA). ON by default; ?fxaa=0 disables. Runs
// as the LAST pass, so it forces sceneT to exist even when tilt-shift/accum are
// off (composite can no longer draw straight to screen — FXAA needs a texture).
const fxaaOn = params.get("fxaa") !== "0";
// idle temporal accumulation (beauty step 4): when the view AND the bound storm
// frame hold still, average successive jittered renders into a float buffer for
// a grain-free "beauty still". ON by default; ?acc=0 restores the always-live
// look (and, with it, a live animation clock while paused). The actual enable
// also needs EXT_color_buffer_float — resolved inside start() as accEnabled.
const accumOn = params.get("acc") !== "0";
// storm display scale — UNIFORM magnification (proportions stay true),
// render-time only, never baked into data (charter); staging stays 1×, so the
// landscape reads smaller under the bigger storm — that contrast is the point
const stormScale = Math.min(3, Math.max(1, Number(params.get("sx") ?? "2") || 2));
const precipOn = params.get("precip") !== "0"; // ?precip=0 disables the particles
// ?anim=0 pins the wall-clock animation (water ripples, rain-veil scroll, precip
// fall) at t=0 so two captures of the same URL are bit-comparable — the A/B
// verification recipe needs it; it never affects storm time or playback.
const animOn = params.get("anim") !== "0";
// numeric param where 0 is a legitimate value (the `|| default` idiom eats it)
const numParam = (name: string, def: number) => {
  const raw = params.get(name);
  const v = Number(raw);
  return raw !== null && Number.isFinite(v) ? v : def;
};
// cloud edge detail-erosion strength (?er=0 disables — the pre-erosion look)
const erosion = Math.min(1, Math.max(0, numParam("er", 0.45)));
// rain-veil extinction weight (?veil=0 disables the veil entirely)
const veilW = Math.max(0, numParam("veil", 0.12));
// sun-transmittance light cache — OFF by default (opt in with ?lc=1). The baked
// R8 half-res cache (beauty step 0) stair-steps the deeply self-shadowed cloud
// core into hard cube facets (the coarse texels crush exp(-tau) and clamp dark);
// the live per-sample sun march is smooth and reads as a realistic soft-gray Cb
// base, at no measured cost on this GPU (rs=4 GPU-bound: 208 vs 215 ms — cache is
// marginally SLOWER here, "shadow march is not the bottleneck"). Kept as opt-in
// insurance for weak GPUs, but note it does not currently serve them — it ships a
// broken image; a real weak-GPU fix means storing tau (or R16F), not just more
// texels (8-bit quantization is a co-cause resolution alone won't touch).
const lightCache = params.get("lc") === "1";
// haze-only samples read the baked cache (one fetch) instead of the live sun
// march: ON by default — open air is where the cache is faithful, and those
// samples were ~60 % of the march after the LOD fix. ?hazelc=0 for the A/B.
// The cache is therefore ALWAYS baked at upload now (≈0.5 ms GPU per brick).
const hazeCache = params.get("hazelc") !== "0";
// multi-scatter octaves (beauty 1): octave weight (?msw=0 → single scatter) and
// per-octave optical-depth attenuation (?msa=). msw lifts shadowed cores from
// black to luminous grey; msNorm keeps the sunlit side at the same level.
const msW = Math.max(0, numParam("msw", 0.55));
const msA = Math.min(1, Math.max(0.05, numParam("msa", 0.35)));
// silver-lining forward spike on thin sun-facing edges (?silver=0 disables).
const silver = Math.max(0, numParam("silver", 0.15));
// sunlit haze inside the box (beauty 3): extinction lit by the cached sun
// transmittance → crepuscular gloom under/beside the anvil and a soft backlit
// atmosphere. km^-1; ?rays=0 disables (restores the empty-air skip).
// This is now the SURFACE (peak) value: the haze is height-graded exp(-alt/rayh)
// — dense near the platter, ~0 aloft — a real vertical profile, not the uniform
// soup a constant fill implied. Grading to ~0 at the box top also removes the
// boxy anvil-level glow the constant term produced.
// NOTE: the old constant-fill range (0.0004-0.0008) is VOID — that integrated
// over the whole ~18 km box, so it capped low to avoid a milky slab. With the
// column now concentrated in the low ~rayh km, the integral is ~rayh/boxheight
// smaller, so the surface value can go higher before washout. Re-swept fresh
// (temp/step3v2): clean up to 0.010 now that the deck also fades before the XY
// walls (see the shader's `edge` term). 0.004 shows the backlit under-anvil glow
// and low gloom without over-hazing head-on; owner tunes 0.003-0.008 via ?rays=.
const rays = Math.max(0, numParam("rays", 0.004));
// haze scale height (storm-km): how deep the haze layer feels. ~1.5 km is a
// typical aerosol scale height (well-mixed boundary layer); smaller = a tighter
// low deck, larger = haze reaches further up. Owner's taste dial via ?rayh=.
const rayh = Math.max(0.1, numParam("rayh", 1.5));
// tonemap (beauty 6): AgX by default — it holds white on the bright sunlit
// cauliflower where the ACES fit skews orange near clipping. ?tm=aces reverts.
// Owner-gated taste default: presented as an A/B, not self-picked here.
const tonemap = (params.get("tm") ?? "agx") === "agx" ? 1 : 0;
// warm/cool split-tone in the grade pass (beauty 6): highlights warm, shadows
// cool — the warm/cool tension of storm-light photography. ?split=0 disables.
const split = Math.max(0, numParam("split", 1));
// cross-section (slice 5a): a movable false-color cut plane through the storm's
// interior. OFF by default (an inspection tool, not a beauty default → shipped
// look unchanged): ?xsec=x|y|z (or 1|2|3) picks the axis, ?xpos=0..1 the plane
// position, ?xmax= the g/kg mapped to the top of the colormap. Keys ,/. nudge
// the plane and \ cycles the axis at runtime. The sliced field is the RAW data
// (no erosion/veil), so it reports the simulation honestly, not the beauty pass.
const AXIS_NAME = ["off", "east–west (x)", "north–south (y)", "vertical (z)"];
const axisFromParam = (s: string | null): number => {
  if (s === null) return 0;
  const m: Record<string, number> = { x: 1, y: 2, z: 3, "1": 1, "2": 2, "3": 3, "0": 0 };
  return m[s.toLowerCase()] ?? 0;
};
let xsecAxis = axisFromParam(params.get("xsec"));
let xsecPos = Math.min(1, Math.max(0, numParam("xpos", 0.5)));
const xsecMax = Math.max(0.1, numParam("xmax", 10)); // g/kg at the colormap top

// data layer: ?layer=dbz swaps the storm to a dBZ radar-reflectivity diagnostic
// (5b); ?layer=w to the signed updraft field (T8); ?layer=cref to the composite-
// reflectivity RADAR PLAN view (T9). dbz/w are emissive max-along-view-ray
// projections that replace the cloud march; cref is a 2D view-INDEPENDENT map
// painted flat on the ground. Off by default (?layer=hydro, the shipped
// hydrometeor look): when hydro NO extra plane is fetched/decoded/uploaded and
// the march is bit-unchanged. The panel (or `d`) toggles at runtime. Diagnostic
// layers are labeled (charter).
type Layer = "hydro" | "dbz" | "w" | "cref";
const layerParam = params.get("layer");
let layer: Layer =
  layerParam === "dbz" ? "dbz" : layerParam === "w" ? "w" : layerParam === "cref" ? "cref" : "hydro";
// updraft-w render knobs (T8), all in m/s. uWClip is the FIXED colour-domain
// clip (|w|≥clip saturates); defaults to the manifest scale below so red = the
// same m/s everywhere — a tighter fixed ?wclip only trades headroom for
// resolution, still cross-scenario-constant. uWDead/uWRamp hide/ramp weak air.
const wClipParam = numParam("wclip", 0); // 0 ⇒ use the manifest scale (set after load)
const wDead = Math.max(0, numParam("wdead", 2)); // |w| below this is transparent
const wRamp = Math.max(0.5, numParam("wramp", 8)); // alpha ramp width above the deadband

// scale bar (slice 5c): a live cartographic rule for the STORM (the staging is
// decorative and stays 1×). ON by default — it is the teaching half of the
// scale chip — and toggleable with `?scalebar=0` / key `b` for clean captures.
let scaleBarOn = params.get("scalebar") !== "0";
const SCALE_BAR_MAX_PX = 150; // longest the rule may draw; niceScaleBar fits under it

// starting view, overridable for tuning/captures: ?az=45&el=11&d=145&fov=34
// (deg, km). The default elevation is low enough that the sea horizon sits in
// frame above the platter — elevation must stay below ~fov/2 to see it at all.
let orbit: OrbitState = {
  target: { x: 0, y: 0, z: 3.5 },
  azimuth: ((Number(params.get("az") ?? "45") || 45) * Math.PI) / 180,
  elevation: ((Number(params.get("el") ?? "11") || 11) * Math.PI) / 180,
  distance: Number(params.get("d") ?? "145") || 145,
  fovY: ((Number(params.get("fov") ?? "34") || 34) * Math.PI) / 180,
};
// Whether the user pinned elevation explicitly (?el=): if so the cref plan view
// respects it for reproducible captures instead of framing overhead.
const elExplicit = params.get("el") !== null;
// The radar PLAN view is a flat ground map; at the default 11° it would read as
// an edge-on smear, not "the top-down product from TV". Entering cref nudges the
// camera near-overhead (azimuth/distance untouched, orbit still free afterward —
// the data is view-independent). Restored on leaving. 78° keeps a whisker of the
// toy-scene depth cue while the map dominates.
const CREF_ELEVATION = (78 * Math.PI) / 180;

function fmt(t: number): string {
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}

async function start() {
  const gl = getGL(canvas);
  // RGBA16F render target needs this extension; without it accumulation is a
  // no-op (accEnabled false ⇒ no float target, no clock freeze, live look).
  const floatOK = !!gl.getExtension("EXT_color_buffer_float");
  const accEnabled = accumOn && floatOK;
  // per-pass GPU timers (?stats only — the query objects are not free)
  const gpu = new GpuTimer(gl, collectStats || rsAuto);
  // ?rs=auto: GPU-time mode when the timer extension exists, else the
  // rAF-spacing fallback (down-only with periodic probes — see autoscale.ts)
  const autoScaler = rsAuto ? new AutoScaler(gpu.available ? "gpu" : "raf") : null;
  statsEl.style.display = collectStats ? "block" : "none";
  const progGeo = compileProgram(gl, GEO_VERT, GEO_FRAG);
  const progVol = compileProgram(gl, VERT, FRAG);
  const progPost = compileProgram(gl, VERT, POST_FRAG);
  const progPrecip = compileProgram(gl, PRECIP_VERT, PRECIP_FRAG);
  const progBake = compileProgram(gl, VERT, BAKE_FRAG);
  const progFxaa = compileProgram(gl, VERT, FXAA_FRAG);
  const loc = (p: WebGLProgram, n: string) => gl.getUniformLocation(p, n);
  gl.useProgram(progFxaa);
  gl.uniform1i(loc(progFxaa, "uTex"), 0); // always samples unit 0

  // ---- scenario selection (T7) ----------------------------------------------
  // Discover the served packages (best-effort — a production build without the
  // dev middleware just gets an empty list and the default still loads), decide
  // which to play, and populate the picker. A switch RELOADS the page with a new
  // ?scenario= (see scenario.ts): the grid differs between packages, so every
  // GL resource is re-derived from scratch rather than rebuilt in place.
  let scenarios: ScenarioSummary[] = [];
  try {
    const r = await fetch("/scenarios.json");
    if (r.ok) scenarios = (await r.json()) as ScenarioSummary[];
  } catch {
    // discovery is optional; resolveScenario falls back to the default below
  }
  const scenario = resolveScenario(params.get("scenario"), scenarios.map((s) => s.name));
  const root = dataRoot(scenario);
  // Show the picker only when there is a genuine choice (≥2 packages served).
  if (scenarios.length > 1) {
    scenarioSel.replaceChildren();
    for (const s of scenarios) {
      const o = document.createElement("option");
      o.value = s.name;
      o.textContent = scenarioLabel(s);
      o.selected = s.name === scenario;
      scenarioSel.appendChild(o);
    }
    scenarioSel.style.display = "";
    scenarioSel.addEventListener("change", () => {
      location.search = scenarioSwitchUrl(location.search, scenarioSel.value);
    });
  }

  const man: WebManifest = await loadManifest(`${root}/web_manifest.json`);
  const { nx, ny, nz } = man.grid;
  const frameBytes = nx * ny * nz * 4;
  const dbzBytes = nx * ny * nz; // R8, one byte/voxel (slice 5b)
  const planeBytes = nx * ny * nz; // R8 — dbz and w are both one byte/voxel
  const crefBytes = nx * ny; // R8 2D plan plane (T9); the DECOMPRESSED size —
  // frame.cref_bytes is the gzipped size, loadBrick checks the inflated length.
  // Updraft w (T8) is feature-detected on the manifest key, NOT the version
  // (charter): a pre-T8 package simply omits `extra_fields.w` and the layer is
  // never offered. If ?layer=w was asked for on a package without it, fall back.
  const wSpec = man.extra_fields?.w;
  const hasW = !!wSpec;
  if (layer === "w" && !hasW) layer = "hydro";
  // Composite reflectivity `cref` (T9), same feature-detect discipline: the plan
  // view is offered only when the package ships `plan_fields.cref`.
  const crefSpec = man.plan_fields?.cref;
  const hasCref = !!crefSpec;
  if (layer === "cref" && !hasCref) layer = "hydro";
  // Colour-domain clip: the FIXED manifest scale unless a tighter fixed ?wclip
  // was given. Never a per-sequence max (would break "same colour = same m/s").
  const wClip = wClipParam > 0 ? wClipParam : wSpec?.scale ?? 80;
  let dbzActive = layer === "dbz"; // gates all dbz fetch/decode/upload
  let wActive = layer === "w"; // gates all w fetch/decode/upload (parallel to dbz)
  let crefActive = layer === "cref"; // gates all cref fetch/decode/upload
  // Elevation to restore when leaving the cref plan view (null ⇒ not overridden).
  let elevBeforeCref: number | null = null;
  // A package opened directly on the plan view frames overhead on first paint
  // (unless ?el pinned it for a capture), so it reads as a map immediately.
  if (crefActive && !elExplicit) {
    elevBeforeCref = orbit.elevation;
    orbit.elevation = CREF_ELEVATION;
  }
  const times = man.frames.map((f) => f.time_s);
  const nFrames = man.frames.length;
  const tEnd = times[nFrames - 1];
  const box = volumeBox(man, stormScale);
  const dec = decodeConstants(man.volume.channels);

  // Sun-transmittance cache resolution: half the volume grid on each axis.
  // 24 × 104×104×36 × 1 B ≈ 9.3 MB total — negligible next to the ~300 MB ring.
  const CACHE_DIV = 2;
  const cacheX = Math.ceil(nx / CACHE_DIV);
  const cacheY = Math.ceil(ny / CACHE_DIV);
  const cacheZ = Math.ceil(nz / CACHE_DIV);

  // ---- staging (decorative, never sim terrain — design doc §5.2) ------------
  const staging = createMeshVAO(gl, buildStaging(stagingSeed).data);

  // ---- detail noise (presentation only: edge erosion + rain veil) -----------
  // bound once on unit 5 — nothing else touches that unit, so it stays bound
  const noiseTex = createNoiseTexture(gl, NOISE_SIZE, buildNoise3D(1));
  gl.activeTexture(gl.TEXTURE5);
  gl.bindTexture(gl.TEXTURE_3D, noiseTex);
  gl.activeTexture(gl.TEXTURE0);

  // ---- precipitation instances (slice 4; presentation, never physics) -------
  const rainVAO = createInstancedVAO(gl, buildPrecipInstances(RAIN.count, stagingSeed + 11, RAIN.spawnFrac));
  const hailVAO = createInstancedVAO(gl, buildPrecipInstances(HAIL.count, stagingSeed + 23, HAIL.spawnFrac));
  const planeOf = (name: string) => man.volume.channels.find((c) => c.name === name)?.plane;

  // ---- playback state -------------------------------------------------------
  // storm time is the single source of truth; speed is a pure UI multiplier
  const startFrame = params.get("frame");
  const startIdx = Math.min(nFrames - 1, Math.max(0, Number(startFrame ?? "0") || 0));
  let tStorm = startFrame !== null ? times[startIdx] : 0;
  let playing = startFrame === null; // autoplay unless inspecting one frame
  let speed = Number(speedSel.value); // storm seconds per wall second
  let buffering = true;

  // ---- streaming state ------------------------------------------------------
  const ring = planRing(frameBytes, ringBudget);
  const RING_CAPACITY = ring.slots;
  const READ_AHEAD = ring.readAhead; // frames beyond the current pair kept warm
  const pool = new SlotPool(RING_CAPACITY);
  const textures: WebGLTexture[] = [];
  for (let i = 0; i < RING_CAPACITY; i++) textures.push(createVolumeTexture(gl, nx, ny, nz));
  // one sun-transmittance cache per ring slot, baked when the slot is filled
  const shadowTex: WebGLTexture[] = [];
  for (let i = 0; i < RING_CAPACITY; i++) shadowTex.push(createShadowCacheTexture(gl, cacheX, cacheY, cacheZ));
  // dBZ plane ring (slice 5b): parallel to `textures`, one R8 volume per slot,
  // filled in the SAME upload block as its rgba brick so the bound pair always
  // has dbz resident. Allocated lazily on first dBZ activation — the hydrometeor
  // default pays zero bytes for it (bit-unchanged-when-off discipline).
  let dbzTex: WebGLTexture[] | null = null;
  function ensureDbzTex() {
    if (dbzTex) return;
    dbzTex = [];
    for (let i = 0; i < RING_CAPACITY; i++) dbzTex.push(createDbzTexture(gl, nx, ny, nz));
  }
  if (dbzActive) ensureDbzTex();
  // w plane ring (T8): the exact same lazy R8-per-slot pattern as dbz — allocated
  // only on first w activation, so the hydrometeor default pays zero bytes for it.
  // createDbzTexture/uploadDbz are generic R8-3D helpers, reused here.
  let wTex: WebGLTexture[] | null = null;
  function ensureWTex() {
    if (wTex) return;
    wTex = [];
    for (let i = 0; i < RING_CAPACITY; i++) wTex.push(createDbzTexture(gl, nx, ny, nz));
  }
  if (wActive) ensureWTex();
  // cref plan ring (T9): same lazy pattern, but a 2D R8 texture (cref is a plan
  // product, not a volume) — tiny (nx·ny ≈ 43 KB/slot), so ~1 MB total.
  let crefTex: WebGLTexture[] | null = null;
  function ensureCrefTex() {
    if (crefTex) return;
    crefTex = [];
    for (let i = 0; i < RING_CAPACITY; i++) crefTex.push(createCrefTexture(gl, nx, ny));
  }
  if (crefActive) ensureCrefTex();
  const bakeFBO = gl.createFramebuffer()!;
  const decoder = new BrickDecoder();
  const inflight = new Set<number>();
  // a decoded frame: the rgba brick always, the dbz/w/cref plane only when its
  // layer is active (only one extra plane is ever active at a time).
  const ready = new Map<
    number,
    { rgba: Uint8Array; dbz: Uint8Array | null; w: Uint8Array | null; cref: Uint8Array | null }
  >();
  let lastGood: { fa: number; fb: number; mix: number } | null = null;
  // an in-progress multi-slab upload (big bricks only; null on the Phase-1 path)
  let uploading: {
    frame: number;
    slot: number;
    slabs: [number, number][];
    next: number;
    data: { rgba: Uint8Array; dbz: Uint8Array | null; w: Uint8Array | null; cref: Uint8Array | null };
  } | null = null;
  // resident = assigned a slot AND fully uploaded (a slab job in flight is not)
  const resident = (f: number) => pool.slotOf(f) !== null && uploading?.frame !== f;
  // stream generation: bumped on a layer toggle so in-flight requests from the
  // previous layer (which may lack the dbz plane) are discarded on arrival
  // rather than uploaded as a stale rgba-only frame.
  let streamGen = 0;

  function requestFrame(f: number) {
    const gen = streamGen;
    inflight.add(f);
    const rgbaP = decoder.request(`${root}/${man.frames[f].rgba}`, frameBytes);
    const dbzP = dbzActive
      ? decoder.request(`${root}/${man.frames[f].dbz}`, dbzBytes)
      : Promise.resolve<Uint8Array | null>(null);
    const wP =
      wActive && man.frames[f].w
        ? decoder.request(`${root}/${man.frames[f].w}`, planeBytes)
        : Promise.resolve<Uint8Array | null>(null);
    const crefP =
      crefActive && man.frames[f].cref
        ? decoder.request(`${root}/${man.frames[f].cref}`, crefBytes)
        : Promise.resolve<Uint8Array | null>(null);
    Promise.all([rgbaP, dbzP, wP, crefP])
      .then(([rgba, dbz, w, cref]) => {
        if (gen === streamGen) ready.set(f, { rgba, dbz, w, cref });
      })
      .catch((e: unknown) => console.error(`frame ${f}:`, e))
      .finally(() => {
        if (gen === streamGen) inflight.delete(f);
      });
  }

  // Layer switch: reset streaming so the sequence re-streams under the new layer
  // (dbz mode adds the dbz plane to each brick). A brief re-buffer on a
  // diagnostic-layer toggle is acceptable (advisor). bumping streamGen orphans
  // the old requests; clearing the pool forgets residency so wanted frames
  // re-fetch. dbz textures are allocated on demand the first time we go dbz.
  function switchLayer(next: Layer) {
    if (next === layer) return;
    if (next === "w" && !hasW) return; // never switch to an unshipped layer
    if (next === "cref" && !hasCref) return;
    // Camera framing (T9): the plan view frames near-overhead so a flat map does
    // not read as an edge-on smear; leaving restores the prior elevation. Skipped
    // when ?el pinned it (a deliberate capture angle). azimuth/distance untouched
    // and orbit stays free afterward — the cref field is view-independent.
    if (!elExplicit) {
      if (next === "cref" && layer !== "cref") {
        elevBeforeCref = orbit.elevation;
        orbit.elevation = CREF_ELEVATION;
      } else if (layer === "cref" && next !== "cref" && elevBeforeCref !== null) {
        orbit.elevation = elevBeforeCref;
        elevBeforeCref = null;
      }
    }
    layer = next;
    dbzActive = layer === "dbz";
    wActive = layer === "w";
    crefActive = layer === "cref";
    if (dbzActive) ensureDbzTex();
    if (wActive) ensureWTex();
    if (crefActive) ensureCrefTex();
    streamGen++;
    inflight.clear();
    ready.clear();
    pool.clear();
    uploading = null; // its data lacks the new layer's plane; the frame re-streams
    lastGood = null;
    buffering = true;
    updateLayerUI();
  }

  // ---- controls -------------------------------------------------------------
  bar.style.display = "flex";
  scrub.max = String(tEnd);
  scrub.value = String(tStorm);

  function setPlaying(p: boolean) {
    playing = p;
    playBtn.textContent = p ? "⏸" : "▶";
  }
  setPlaying(playing);

  playBtn.addEventListener("click", () => setPlaying(!playing));
  speedSel.addEventListener("change", () => (speed = Number(speedSel.value)));

  // frame-rate cap (default 60, max 240): rAF still fires at display refresh,
  // but we render only once the target interval has elapsed. This throttles the
  // whole loop (streaming pump included) — fine, since even the fastest 300×
  // playback needs only ~25 uploads/s, well under the 60 fps default.
  const clampFps = (v: number) => Math.min(240, Math.max(15, Math.round(v) || 60));
  let fpsCap = clampFps(numParam("fps", 60));
  fpsInput.value = String(fpsCap);
  fpsInput.addEventListener("change", () => {
    fpsCap = clampFps(Number(fpsInput.value));
    fpsInput.value = String(fpsCap);
  });
  let scrubbing = false;
  scrub.addEventListener("input", () => {
    scrubbing = true;
    tStorm = Number(scrub.value);
  });
  scrub.addEventListener("change", () => (scrubbing = false));

  function stepFrame(dir: number) {
    setPlaying(false);
    const i = locate(times, tStorm).i0;
    tStorm = times[Math.min(nFrames - 1, Math.max(0, i + dir))];
  }
  window.addEventListener("keydown", (e) => {
    if (e.key === " ") {
      e.preventDefault();
      setPlaying(!playing);
    }
    if (e.key === "[") stepFrame(-1);
    if (e.key === "]") stepFrame(+1);
    // cross-section: , / . slide the cut plane, \ cycles the axis (off→x→y→z)
    if (e.key === ",") { xsecPos = Math.max(0, xsecPos - 0.02); updateXsecUI(); }
    if (e.key === ".") { xsecPos = Math.min(1, xsecPos + 0.02); updateXsecUI(); }
    if (e.key === "\\") { xsecAxis = (xsecAxis + 1) % 4; updateXsecUI(); }
    // toggle the dBZ radar diagnostic layer (slice 5b)
    if (e.key === "d" || e.key === "D") switchLayer(layer === "dbz" ? "hydro" : "dbz");
    // toggle the scale bar (slice 5c) — for clean captures
    if (e.key === "b" || e.key === "B") {
      scaleBarOn = !scaleBarOn;
      sbBox.style.display = scaleBarOn ? "block" : "none";
    }
  });

  // Three drag gestures on the canvas, all leaving the others' state alone:
  //   left   → orbit (azimuth/elevation)
  //   right  → pan across the ground (shift+left too — a trackpad's two-finger
  //            right-click is awkward to drag with)
  //   middle → raise/lower the look-at point (alt+left too, for the same
  //            reason: plenty of trackpads have no middle button)
  // Both pans convert pixels at the target's depth, so the scene tracks the
  // cursor at any zoom. `dragging` stays "a drag of ANY kind is in progress" —
  // the accumulation gate reads it, and a still must not average across motion.
  type DragMode = "orbit" | "ground" | "altitude";
  let dragging = false;
  let dragMode: DragMode = "orbit";
  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    dragMode =
      e.button === 1 || e.altKey ? "altitude" : e.button === 2 || e.shiftKey ? "ground" : "orbit";
    canvas.setPointerCapture(e.pointerId);
  });
  const endDrag = () => {
    dragging = false;
    dragMode = "orbit";
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  // without this the right-drag pops the browser context menu on release
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  // …and without this a middle-press can arm Chrome's autoscroll puck, which
  // would hijack the altitude drag. Must be on the compat MOUSE event: calling
  // preventDefault on pointerdown does not reliably suppress it. (The page has
  // no scrollable region, so this may be belt-and-braces — it costs nothing.)
  canvas.addEventListener("mousedown", (e) => {
    if (e.button === 1) e.preventDefault();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    if (dragMode === "ground") {
      orbit = panGround(orbit, e.movementX, e.movementY, canvas.clientHeight);
    } else if (dragMode === "altitude") {
      orbit = panAltitude(orbit, e.movementY, canvas.clientHeight);
    } else {
      orbit = clampOrbit({
        ...orbit,
        azimuth: orbit.azimuth - e.movementX * 0.005,
        elevation: orbit.elevation + e.movementY * 0.005,
      });
    }
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    orbit = clampOrbit({ ...orbit, distance: orbit.distance * Math.exp(e.deltaY * 0.001) });
  }, { passive: false });

  // ---- data-layer legend + HUD (slice 5a cross-section, 5b dBZ) -------------
  // A DOM legend (undistorted under ?sx, unlike anything drawn in the volume):
  // the ramp is painted from the SAME curve the shader uses, with honest units.
  // Shown for the dBZ layer always (the whole volume is the diagnostic) and, in
  // hydrometeor mode, only while a cross-section cut is active (5a behaviour).
  const xlegend = document.getElementById("xlegend") as HTMLDivElement;
  const xlTitle = document.getElementById("xlTitle") as HTMLDivElement;
  const xlBar = document.getElementById("xlBar") as HTMLDivElement;
  const xlMin = document.getElementById("xlMin") as HTMLSpanElement;
  const xlMax = document.getElementById("xlMax") as HTMLSpanElement;
  const xlAxis = document.getElementById("xlAxis") as HTMLDivElement;
  const dbzThr = man.dbz.threshold;
  const dbzMax = man.dbz.vmax;

  // ---- data-layer panel (T8) ------------------------------------------------
  // A teaching-grade selector: one radio row per shipped layer, each labeled with
  // a DIAGNOSTIC badge iff the manifest flags it so (charter: diagnostics labeled;
  // the flag is READ, never hardcoded, so the panel cannot drift from the
  // contract). The updraft row is feature-detected on `hasW`. `?layer=`/keys stay
  // as accelerators — this panel just makes the choice discoverable. The two
  // radar rows are named to keep the §2.3 distinction legible in the panel
  // itself: "Radar (dBZ)" is the 3D view-ray MIP; "Composite reflectivity" is
  // the T9 view-independent plan map. cref is feature-detected on `hasCref`.
  const layersPanel = document.getElementById("layers") as HTMLDivElement;
  const layerDefs: { id: Layer; name: string; diagnostic: boolean }[] = [
    { id: "hydro", name: "Hydrometeors", diagnostic: false },
    { id: "dbz", name: "Radar (dBZ)", diagnostic: man.dbz.diagnostic },
    ...(hasW ? [{ id: "w" as Layer, name: "Updraft (w)", diagnostic: wSpec!.diagnostic }] : []),
    ...(hasCref
      ? [{ id: "cref" as Layer, name: "Composite reflectivity", diagnostic: crefSpec!.diagnostic }]
      : []),
  ];
  const layerRadios = new Map<Layer, HTMLInputElement>();
  for (const def of layerDefs) {
    const row = document.createElement("label");
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "layer";
    radio.checked = def.id === layer;
    radio.addEventListener("change", () => {
      if (radio.checked) switchLayer(def.id);
    });
    const nm = document.createElement("span");
    nm.className = "lname";
    nm.textContent = def.name;
    row.append(radio, nm);
    if (def.diagnostic) {
      const badge = document.createElement("span");
      badge.className = "ldiag";
      badge.textContent = "DIAGNOSTIC";
      badge.title = "computed from the simulated fields, not a prognostic variable";
      row.append(badge);
    }
    layersPanel.append(row);
    layerRadios.set(def.id, radio);
  }
  layersPanel.style.display = "block";

  // Honest domain extents, DERIVED (slice 5c) — these were literal "52 km wide,
  // 18 km tall" text, which is correct for this package (208×208×72 @ 250 m) but
  // would silently lie the first time a scenario ships a different crop.
  const kmText = (v: number) => v.toFixed(v % 1 ? 1 : 0);
  const domW = (man.grid.nx * man.grid.voxel_m) / 1000;
  const domD = (man.grid.ny * man.grid.voxel_m) / 1000;
  const domH = (man.grid.nz * man.grid.voxel_m) / 1000;
  const extentText =
    (Math.abs(domW - domD) < 1e-6
      ? `${kmText(domW)} km wide`
      : `${kmText(domW)} × ${kmText(domD)} km across`) + `, ${kmText(domH)} km tall`;

  function updateLayerUI() {
    const isDbz = layer === "dbz";
    const isW = layer === "w";
    const isCref = layer === "cref";
    layerRadios.forEach((r, id) => (r.checked = id === layer)); // keep the panel in sync
    // HUD: controls + honest scale + staging disclaimer + a diagnostic banner
    // when a diagnostic layer is active (charter: diagnostics are labeled). The
    // updraft w banner carries NO ⚠ — w is prognostic (a real simulated field),
    // but the MIP note is still honest about view-dependence.
    hud.textContent =
      `drag orbit · right-drag pan · middle-drag height · wheel zoom · space play/pause · [ ] frame step\n` +
      `\\ cross-section · d dBZ layer · b scale bar · layer panel top-right\n` +
      `this storm is ${extentText}` +
      (stormScale !== 1 ? ` — shown at ${stormScale}× scale` : "") + `\n` +
      `land, towns & forests are decorative staging, not simulation data` +
      (precipOn && layer === "hydro" ? `\nrain & hail are stylized particles gated by the simulated near-surface fields` : "") +
      (isDbz ? `\n⚠ DIAGNOSTIC: radar reflectivity (dBZ), computed from the simulated fields — max-intensity projection (peak dBZ along the line of sight)` : "") +
      (isW ? `\nupdraft w (m/s): the simulated vertical wind — strongest |w| along each view ray, red rising / blue sinking` : "") +
      (isCref ? `\n⚠ DIAGNOSTIC: composite reflectivity (dBZ) — the RADAR PLAN VIEW, column-max echo painted on the ground. View-INDEPENDENT: unlike the dBZ layer's line-of-sight MIP, it does not change as you orbit` : "");

    // legend palette + units follow the layer. cref shares the dbz ramp exactly
    // (same threshold/vmax by identity), so one colormap serves both radar views.
    if (isDbz || isCref) {
      xlTitle.textContent = isCref
        ? "composite reflectivity (diagnostic)"
        : "dBZ reflectivity (diagnostic)";
      xlBar.style.background = `linear-gradient(to right, ${dbzCssGradientStops(dbzThr, dbzMax)})`;
      xlMin.textContent = `${Math.round(dbzThr)} dBZ`;
      xlMax.textContent = `${Math.round(dbzMax)} dBZ`;
    } else if (isW) {
      xlTitle.textContent = "updraft w (m/s)";
      xlBar.style.background = `linear-gradient(to right, ${wCssGradientStops()})`;
      xlMin.textContent = `−${Math.round(wClip)}`;
      xlMax.textContent = `+${Math.round(wClip)} m/s`;
    } else {
      xlTitle.textContent = "total hydrometeors";
      xlBar.style.background = `linear-gradient(to right, ${cssGradientStops(12)})`;
      xlMin.textContent = "0";
      xlMax.textContent = `${xsecMax} g/kg`;
    }
    xlegend.style.display = isDbz || isW || isCref || xsecAxis > 0 ? "block" : "none";
    xlAxis.textContent =
      xsecAxis > 0 && !isCref
        ? `cut plane: ${AXIS_NAME[xsecAxis]} · ${Math.round(xsecPos * 100)}%  ( , / . move )`
        : isDbz
        ? "peak reflectivity along each view ray"
        : isW
        ? "peak |w| along each view ray, coloured by sign"
        : isCref
        ? "column-max reflectivity — view-independent plan (map) product"
        : "";
  }
  const updateXsecUI = updateLayerUI; // xsec key handlers refresh the same UI
  updateLayerUI();
  sbBox.style.display = scaleBarOn ? "block" : "none";
  // last-written scale-bar geometry, so the render loop only touches the DOM
  // when the zoom actually changed (a per-frame style write forces layout).
  let sbLastLabel = "";
  let sbLastPx = -1;

  // ---- render targets (recreated on resize) ----------------------------------
  // These MUST be declared before resize() runs — resize() writes accT/accN.
  let gbuf: GBuffer | null = null;
  let sceneT: ColorTarget | null = null; // composite output (when not direct-to-screen)
  let blurT: ColorTarget | null = null; // tilt-shift ping-pong
  let accT: ColorTarget | null = null; // RGBA16F idle-accumulation running average
  // accumulation bookkeeping (see accum.ts): frames averaged so far, the last
  // view key, and the frozen animation clock while a still is converging.
  let accN = 0;
  let prevKey: ViewKey | null = null;
  let tFrozen = 0;

  function resize() {
    const dpr = window.devicePixelRatio * renderScale;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    gbuf?.dispose();
    gbuf = createGBuffer(gl, canvas.width, canvas.height);
    // sceneT exists whenever we do NOT draw the composite straight to screen
    // (tilt-shift, accumulation, and/or FXAA on); blurT only for tilt-shift;
    // accT only for accumulation. All-off keeps the direct-to-screen fast path.
    if (tiltShift || accEnabled || fxaaOn) {
      sceneT?.dispose();
      sceneT = createColorTarget(gl, canvas.width, canvas.height);
    }
    if (tiltShift) {
      blurT?.dispose();
      blurT = createColorTarget(gl, canvas.width, canvas.height);
    }
    if (accEnabled) {
      accT?.dispose();
      accT = createColorTarget(gl, canvas.width, canvas.height, gl.RGBA16F);
      accN = 0; // resize invalidates accumulation history
    }
  }
  window.addEventListener("resize", resize);
  resize();

  // ---- static uniforms (volume program) --------------------------------------
  const thr = new Float32Array(4);
  const k = new Float32Array(4);
  for (const c of man.volume.channels) {
    thr[c.plane] = dec.thr[c.plane];
    k[c.plane] = dec.k[c.plane];
  }
  const w = man.volume.channels.map((c) => WEIGHTS[c.name as keyof typeof WEIGHTS] ?? 0);
  // The primary march splits species: cloud/ice/graupel keep the UE-parity
  // weights; rain leaves the cloud sum and becomes the veil (darker albedo,
  // noise-modulated, weight veilW). Shadow marches see the same total the eye
  // does (minus the noise), so the veil darkens the landscape like real rain.
  const rainPlane = planeOf("rain");
  const wCld = w.map((v, i) => (i === rainPlane ? 0 : v));
  const wShadow = w.map((v, i) => (i === rainPlane ? veilW : v));
  const veilMask = [0, 0, 0, 0];
  if (rainPlane !== undefined) veilMask[rainPlane] = veilW;
  // storm-km box size (display / sx): veil noise coords stay scale-invariant
  const sizeStorm = {
    x: (box.max.x - box.min.x) / stormScale,
    y: (box.max.y - box.min.y) / stormScale,
    z: (box.max.z - box.min.z) / stormScale,
  };
  gl.useProgram(progVol);
  gl.uniform3f(loc(progVol, "uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(loc(progVol, "uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(loc(progVol, "uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(loc(progVol, "uVolA"), 0);
  gl.uniform1i(loc(progVol, "uVolB"), 1);
  gl.uniform1i(loc(progVol, "uAlbedo"), 2);
  gl.uniform1i(loc(progVol, "uNormalTex"), 3);
  gl.uniform1i(loc(progVol, "uDepthTex"), 4);
  gl.uniform1f(loc(progVol, "uNear"), NEAR);
  gl.uniform1f(loc(progVol, "uFar"), FAR);
  gl.uniform4fv(loc(progVol, "uThr"), thr);
  gl.uniform4fv(loc(progVol, "uK"), k);
  gl.uniform4f(loc(progVol, "uWeights"), wShadow[0], wShadow[1], wShadow[2], wShadow[3]);
  gl.uniform4f(loc(progVol, "uWeightsCld"), wCld[0], wCld[1], wCld[2], wCld[3]);
  gl.uniform4f(loc(progVol, "uRainVeil"), veilMask[0], veilMask[1], veilMask[2], veilMask[3]);
  // Uniform magnification must keep optical depth invariant: paths through the
  // storm are stormScale× longer in km, so per-km extinction divides by the
  // scale (and the sun-march cap grows with it). The 2× storm then looks like
  // the same cloud shown bigger — not a denser one.
  gl.uniform1f(loc(progVol, "uExtScale"), EXT_SCALE / stormScale);
  gl.uniform1f(loc(progVol, "uSteps"), stepsParam);
  const minStep = stepParam === "auto"
    ? Math.max(box.max.x - box.min.x, box.max.y - box.min.y) / stepsParam
    : Math.max(0, Number(stepParam) || 0);
  gl.uniform1f(loc(progVol, "uMinStep"), minStep);
  gl.uniform1i(loc(progVol, "uSunSteps"), sunSteps);
  gl.uniform1f(loc(progVol, "uDebug"), debugMode);
  gl.uniform1f(loc(progVol, "uHazeCache"), hazeCache ? 1 : 0);
  gl.uniform1f(loc(progVol, "uDither"), ditherIgn ? 1 : 0);
  gl.uniform1f(loc(progVol, "uExposure"), 0.75);
  gl.uniform1f(loc(progVol, "uShadowKm"), 15 * stormScale);
  gl.uniform1i(loc(progVol, "uNoise"), 5);
  gl.uniform1i(loc(progVol, "uShadowA"), 6);
  gl.uniform1i(loc(progVol, "uShadowB"), 7);
  gl.uniform1f(loc(progVol, "uUseCache"), lightCache ? 1 : 0);
  gl.uniform3f(loc(progVol, "uSizeStorm"), sizeStorm.x, sizeStorm.y, sizeStorm.z);
  gl.uniform1f(loc(progVol, "uErosion"), erosion);
  // sigC is per DISPLAY km (÷sx), so "coreness" renormalizes by sx: the same
  // storm erodes identically at any display scale (core threshold 0.8 km⁻¹)
  gl.uniform1f(loc(progVol, "uCoreNorm"), 1.25 * stormScale);
  gl.uniform1f(loc(progVol, "uMsW"), msW);
  gl.uniform1f(loc(progVol, "uMsA"), msA);
  gl.uniform1f(loc(progVol, "uSilver"), silver);
  gl.uniform1f(loc(progVol, "uRays"), rays);
  gl.uniform1f(loc(progVol, "uHazeH"), rayh);
  gl.uniform1f(loc(progVol, "uTonemap"), tonemap);
  gl.uniform1f(loc(progVol, "uXmax"), xsecMax);
  // dBZ diagnostic layer (slice 5b): the plane on unit 8 + its linear-decode
  // constants. uLayer is set per-frame (it toggles at runtime).
  gl.uniform1i(loc(progVol, "uDbzA"), 8);
  gl.uniform1f(loc(progVol, "uDbzThr"), man.dbz.threshold);
  gl.uniform1f(loc(progVol, "uDbzMax"), man.dbz.vmax);
  // updraft w (T8): plane on unit 9 + physical decode scale + fixed colour clip +
  // deadband/ramp. uLayer is set per-frame (it toggles at runtime).
  gl.uniform1i(loc(progVol, "uWA"), 9);
  gl.uniform1f(loc(progVol, "uWScale"), wSpec?.scale ?? 80);
  gl.uniform1f(loc(progVol, "uWClip"), wClip);
  gl.uniform1f(loc(progVol, "uWDead"), wDead);
  gl.uniform1f(loc(progVol, "uWRamp"), wRamp);
  // composite reflectivity plan plane (T9): 2D texture on unit 10. It shares the
  // dbz decode (uDbzThr/uDbzMax) by identity, so no extra scale uniforms.
  gl.uniform1i(loc(progVol, "uCref"), 10);

  // ---- static uniforms (precip program) --------------------------------------
  // The shared VOL_COMMON chunk gives this program the same names/values as
  // the volume pass; particle speeds/lengths pre-scale by the display scale so
  // the bigger storm sheds bigger rain (same transit time, same proportions).
  gl.useProgram(progPrecip);
  gl.uniform3f(loc(progPrecip, "uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(loc(progPrecip, "uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(loc(progPrecip, "uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(loc(progPrecip, "uVolA"), 0);
  gl.uniform1i(loc(progPrecip, "uVolB"), 1);
  gl.uniform1i(loc(progPrecip, "uDepthTex"), 4);
  gl.uniform4fv(loc(progPrecip, "uThr"), thr);
  gl.uniform4fv(loc(progPrecip, "uK"), k);
  gl.uniform4f(loc(progPrecip, "uWeights"), wShadow[0], wShadow[1], wShadow[2], wShadow[3]);
  gl.uniform1f(loc(progPrecip, "uExtScale"), EXT_SCALE / stormScale);
  gl.uniform1f(loc(progPrecip, "uShadowKm"), 15 * stormScale);
  // Same three cache bindings as progVol — an unset sampler defaults to unit 0
  // and would read the volume brick as a shadow cache.
  gl.uniform1i(loc(progPrecip, "uShadowA"), 6);
  gl.uniform1i(loc(progPrecip, "uShadowB"), 7);
  gl.uniform1f(loc(progPrecip, "uUseCache"), lightCache ? 1 : 0);
  gl.uniform1i(loc(progPrecip, "uSunSteps"), sunSteps);
  gl.uniform2f(loc(progPrecip, "uTilt"), 0.1, 0.04); // slight wind-shear lean
  gl.uniform1f(loc(progPrecip, "uGateZ"), 2.5 / nz); // ~625 m: the near-surface layers
  gl.uniform1f(loc(progPrecip, "uMaxR"), GROUND_HALF - 1); // rain stays on the diorama slab

  function drawPrecip(spec: PrecipSpec, vao: WebGLVertexArrayObject, count: number) {
    const plane = planeOf(spec.gateChannel);
    if (plane === undefined) return; // package without that channel: no particles
    const mask = [0, 0, 0, 0];
    mask[plane] = 1;
    gl.uniform4f(loc(progPrecip, "uGateMask"), mask[0], mask[1], mask[2], mask[3]);
    gl.uniform1f(loc(progPrecip, "uQFloor"), spec.qFloor);
    gl.uniform1f(loc(progPrecip, "uQFull"), spec.qFull);
    gl.uniform1f(loc(progPrecip, "uFallSpeed"), spec.fallSpeed * stormScale);
    gl.uniform1f(loc(progPrecip, "uLen"), spec.length * stormScale);
    gl.uniform1f(loc(progPrecip, "uHalfWidth"), spec.halfWidth);
    gl.uniform1f(loc(progPrecip, "uZTop"), spec.zTop * stormScale);
    gl.uniform3f(loc(progPrecip, "uColor"), spec.color[0], spec.color[1], spec.color[2]);
    gl.uniform1f(loc(progPrecip, "uAlphaMax"), spec.alpha);
    gl.bindVertexArray(vao);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, count);
    gl.bindVertexArray(null);
  }

  // ---- sun-transmittance bake (pass 0) --------------------------------------
  // Static uniforms: the bake MUST see exactly what the shadow march sees today
  // — wShadow weights, the scale-corrected extinction, the same uShadowKm cap —
  // so cache shadows match the live march (uMix defaults to 0: sigmaShadowAt
  // reads only uVolA, the brick on unit 0).
  gl.useProgram(progBake);
  gl.uniform3f(loc(progBake, "uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(loc(progBake, "uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(loc(progBake, "uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(loc(progBake, "uVolA"), 0);
  gl.uniform1i(loc(progBake, "uVolB"), 0); // unused (uMix=0), pointed somewhere valid
  gl.uniform4fv(loc(progBake, "uThr"), thr);
  gl.uniform4fv(loc(progBake, "uK"), k);
  gl.uniform4f(loc(progBake, "uWeights"), wShadow[0], wShadow[1], wShadow[2], wShadow[3]);
  gl.uniform1f(loc(progBake, "uExtScale"), EXT_SCALE / stormScale);
  gl.uniform1f(loc(progBake, "uShadowKm"), 15 * stormScale);
  gl.uniform2f(loc(progBake, "uCacheXY"), cacheX, cacheY);
  gl.uniform1i(loc(progBake, "uSunSteps"), sunSteps);

  // Bake one ring slot's sun-transmittance cache: a fullscreen draw per z-slice
  // (framebufferTextureLayer selects the layer). Called from the upload block,
  // so the cache is filled in the same rAF as the brick, before any bind.
  function bakeShadow(slot: number) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, bakeFBO);
    gl.viewport(0, 0, cacheX, cacheY);
    gl.useProgram(progBake);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_3D, textures[slot]);
    for (let z = 0; z < cacheZ; z++) {
      gl.framebufferTextureLayer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, shadowTex[slot], 0, z);
      gl.uniform1f(loc(progBake, "uSliceZ"), (z + 0.5) / cacheZ);
      drawFullscreen(gl);
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  // ---- pacing stats (?stats — read by the headless verification driver) -----
  const stats = {
    deltas: [] as number[],
    stalls: 0,
    uploads: 0,
    drawn: 0,
    uploadMs: [] as number[], // texSubImage3D wall cost per upload
    stallInfo: [] as { ready: number; inflight: number; resident: number }[],
    gpu: {} as Record<string, number>, // EMA GPU ms per pass (see gputimer.ts)
    gpuSamples: 0,
    fps: 0, // EMA of rendered frames per second
    rs: 1, // current render scale (moves under ?rs=auto)
  };
  let fpsEma = 0;
  let lastHudStats = 0;
  if (collectStats) (window as unknown as { __stats: typeof stats }).__stats = stats;

  // ---- frame loop -----------------------------------------------------------
  let lastNow = performance.now();
  let lastRaf = lastNow; // every heartbeat, rendered or not — for the period estimate
  let rafPeriod = 0; // EMA of the display's rAF spacing, ms
  let nextRender = lastNow; // scheduled time of the next rendered frame
  function frame(now: number) {
    requestAnimationFrame(frame); // schedule next heartbeat before any early-out

    // frame-rate cap. rAF only fires on the display's own grid, so a 60 cap
    // cannot be "16.7 ms since the last render": on a 144 Hz panel that rule
    // rendered every THIRD tick (20.8 ms → 48 fps, measured). Instead keep an
    // ideal schedule (nextRender advances by exact intervals) and render on the
    // heartbeat that lands CLOSEST to it — ticks alternate 2/3 apart but the
    // average is exactly the cap. Falling behind (tab hidden) resets the
    // schedule rather than accumulating a debt. lastNow (which drives dtWall)
    // advances only on rendered frames, so playback speed stays correct.
    const minInterval = 1000 / fpsCap;
    const rawRaf = now - lastRaf;
    lastRaf = now;
    if (rawRaf > 0 && rawRaf < 100) rafPeriod = rafPeriod === 0 ? rawRaf : rafPeriod + (rawRaf - rafPeriod) * 0.1;
    if (now + 0.5 * rafPeriod < nextRender) return;
    nextRender = Math.max(nextRender, now - minInterval) + minInterval;

    const rawDtMs = now - lastNow;
    const dtWall = Math.min(rawDtMs / 1000, 0.1); // clamp tab-away gaps
    lastNow = now;
    if (collectStats || rsAuto) {
      gpu.poll(); // harvest last frame's queries before issuing new ones
      const inst = 1000 / Math.max(rawDtMs, 0.01);
      fpsEma = fpsEma === 0 ? inst : fpsEma + (inst - fpsEma) * 0.1;
    }

    // 1. what does the play head need?
    let pos = locate(times, tStorm);
    const wanted = wantedFrames(pos.i0, READ_AHEAD, nFrames);
    const wantedSet = new Set(wanted);

    // 2. schedule decodes for missing frames, in priority order
    for (const f of wanted) {
      if (inflight.size >= MAX_INFLIGHT) break;
      if (pool.slotOf(f) === null && !inflight.has(f) && !ready.has(f)) requestFrame(f);
    }

    // 3. upload at most ONE decoded brick per rAF (12.5 MB — keeps the GPU
    //    copy off the critical path; 60 uploads/s ≫ 25 frames/s at 300×)
    for (const f of ready.keys()) if (!wantedSet.has(f)) ready.delete(f); // stale scrub leftovers
    const keep = new Set(wantedSet);
    if (lastGood) {
      keep.add(lastGood.fa);
      keep.add(lastGood.fb);
    }
    if (uploading) keep.add(uploading.frame); // a half-filled slot must not be evicted
    // The extra planes + the sun-cache bake land with the LAST slab, so a slot
    // is complete (rgba + planes + cache) the moment `uploading` clears.
    const finishUpload = (slot: number, data: NonNullable<ReturnType<typeof ready.get>>) => {
      // dbz plane into the SAME slot, so the bound pair always has dbz
      // resident when the layer is active (streamGen guarantees data.dbz is
      // present here whenever dbzActive — stale rgba-only frames were orphaned)
      if (dbzActive && data.dbz && dbzTex) uploadDbz(gl, dbzTex[slot], nx, ny, nz, data.dbz);
      if (wActive && data.w && wTex) uploadDbz(gl, wTex[slot], nx, ny, nz, data.w);
      if (crefActive && data.cref && crefTex) uploadCref(gl, crefTex[slot], nx, ny, data.cref);
      bakeShadow(slot); // fill the slot's sun cache in the same rAF (haze + ?lc=1)
    };
    if (uploading) {
      // continue a multi-slab upload: one slab per rAF, then finish
      const u0 = performance.now();
      gpu.begin("upload");
      const [z0, z1] = uploading.slabs[uploading.next++];
      uploadVolumeSlab(gl, textures[uploading.slot], nx, ny, z0, z1, uploading.data.rgba);
      if (uploading.next >= uploading.slabs.length) {
        finishUpload(uploading.slot, uploading.data);
        stats.uploads++;
        uploading = null;
      }
      gpu.end();
      if (collectStats && stats.uploadMs.length < 2000) stats.uploadMs.push(performance.now() - u0);
    } else {
      for (const f of wanted) {
        const data = ready.get(f);
        if (!data) continue;
        const slot = pool.assign(f, keep);
        if (slot !== null) {
          const u0 = performance.now();
          gpu.begin("upload");
          const slabs = uploadSlabs(nz, nx * ny * 4, UPLOAD_CHUNK_BYTES);
          if (slabs.length === 1) {
            // the whole brick in one call (the Phase-1 path, unchanged)
            uploadVolume(gl, textures[slot], nx, ny, nz, data.rgba);
            finishUpload(slot, data);
            stats.uploads++;
          } else {
            // big brick: first slab now, the rest over the next rAFs. The slot
            // is assigned (so nothing else claims it) but NOT resident until
            // the job completes — see resident() below.
            const [z0, z1] = slabs[0];
            uploadVolumeSlab(gl, textures[slot], nx, ny, z0, z1, data.rgba);
            uploading = { frame: f, slot, slabs, next: 1, data };
          }
          gpu.end();
          if (collectStats && stats.uploadMs.length < 2000) stats.uploadMs.push(performance.now() - u0);
          ready.delete(f);
        }
        break;
      }
    }

    // 4. advance the clock — but never past frames that aren't resident yet
    //    (playback holds, storm time never skips)
    if (playing && !scrubbing) {
      const tNext = advance(tStorm, dtWall * speed, 0, tEnd);
      const posNext = locate(times, tNext);
      const ok = resident(posNext.i0) && resident(posNext.i1);
      if (ok) tStorm = tNext;
      else {
        stats.stalls++;
        if (collectStats && stats.stallInfo.length < 500) {
          stats.stallInfo.push({ ready: ready.size, inflight: inflight.size, resident: pool.resident().length });
        }
      }
      pos = locate(times, tStorm);
    }

    // 5. bind the pair (falling back to the last complete pair while buffering)
    const sa = resident(pos.i0) ? pool.slotOf(pos.i0) : null;
    const sb = resident(pos.i1) ? pool.slotOf(pos.i1) : null;
    let bind: { fa: number; fb: number; mix: number } | null = null;
    if (sa !== null && sb !== null) {
      bind = { fa: pos.i0, fb: pos.i1, mix: pos.f };
      lastGood = bind;
      buffering = false;
    } else {
      bind = lastGood;
      buffering = true;
    }

    // idle temporal accumulation: when the camera AND the bound frame pair hold
    // perfectly still, re-render with a fresh jitter each rAF and average into a
    // float buffer → the grain dissolves to a clean still. Any drag/scrub/frame
    // change makes `same` false, which resets the count and unfreezes the clock,
    // so motion (and playback) look exactly as they do live. While a still is
    // converging the animation clock (tAnim) is frozen so water/veil/precip do
    // not smear the average — pausing therefore freezes the whole miniature.
    const key: ViewKey = {
      az: orbit.azimuth, el: orbit.elevation, dist: orbit.distance,
      fovY: orbit.fovY,
      targetX: orbit.target.x, targetY: orbit.target.y, targetZ: orbit.target.z,
      fa: bind?.fa ?? -1, fb: bind?.fb ?? -1, mix: bind?.mix ?? -1,
      xsec: xsecAxis, xpos: xsecPos,
      layer: layer === "dbz" ? 1 : layer === "w" ? 2 : layer === "cref" ? 3 : 0,
    };
    const same = accEnabled && !dragging && !scrubbing && sameView(prevKey, key);
    prevKey = key;
    accN = nextCount(same, accN);
    if (!same) tFrozen = now / 1000;
    const tAnim = !animOn ? 0 : same ? tFrozen : now / 1000;
    const converged = same && accN >= ACC_CAP;

    if (bind && gbuf) {
      pool.touch(bind.fa);
      pool.touch(bind.fb);
      const cam = basis(orbit);
      const aspect = canvas.width / canvas.height;
      const viewProj = multiply(perspective(orbit.fovY, aspect, NEAR, FAR), view(cam));

      // Composite straight to screen only when tilt-shift, accumulation AND FXAA
      // are all off (today's fast path); otherwise into sceneT for the post
      // chain. FXAA must flip this to false on its own — miss it and the
      // composite draws straight past FXAA, which then silently never runs.
      const directToScreen = !tiltShift && !accEnabled && !fxaaOn;
      const compositeFbo = directToScreen ? null : sceneT!.fbo;

      // The heavy passes (staging, 280-step raymarch, precip, accumulate) are
      // skipped once the still has converged — accT already holds the finished
      // image and only the cheap present below re-runs, so idle GPU load drops.
      if (!converged) {
        // -- pass 1: staging mesh into the g-buffer ----------------------------
        gpu.begin("geo");
        gl.bindFramebuffer(gl.FRAMEBUFFER, gbuf.fbo);
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.enable(gl.DEPTH_TEST);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        gl.useProgram(progGeo);
        gl.uniformMatrix4fv(loc(progGeo, "uViewProj"), false, viewProj);
        gl.bindVertexArray(staging.vao);
        gl.drawArrays(gl.TRIANGLES, 0, staging.count);
        gl.bindVertexArray(null);
        gl.disable(gl.DEPTH_TEST);

        // -- pass 2: volume raymarch + surface shading + backdrop --------------
        gpu.begin("march");
        gl.bindFramebuffer(gl.FRAMEBUFFER, compositeFbo);
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.useProgram(progVol);
        gl.uniform2f(loc(progVol, "uRes"), canvas.width, canvas.height);
        gl.uniform3f(loc(progVol, "uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
        gl.uniform3f(loc(progVol, "uCamRight"), cam.right.x, cam.right.y, cam.right.z);
        gl.uniform3f(loc(progVol, "uCamUp"), cam.up.x, cam.up.y, cam.up.z);
        gl.uniform3f(loc(progVol, "uCamFwd"), cam.forward.x, cam.forward.y, cam.forward.z);
        gl.uniform1f(loc(progVol, "uFovTan"), Math.tan(orbit.fovY / 2));
        gl.uniform1f(loc(progVol, "uMix"), bind.mix);
        gl.uniform1f(loc(progVol, "uXsec"), xsecAxis);
        gl.uniform1f(loc(progVol, "uXpos"), xsecPos);
        gl.uniform1f(loc(progVol, "uLayer"), layer === "dbz" ? 1 : layer === "w" ? 2 : layer === "cref" ? 3 : 0);
        gl.uniform1f(loc(progVol, "uTime"), tAnim);
        // fresh jitter per accumulation pass while holding still; 0 during motion
        // and with ?acc=0 ⇒ bit-for-bit today's image.
        gl.uniform1f(loc(progVol, "uJitter"), same ? jitterSeq(accN) : 0);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fa)!]);
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fb)!]);
        gl.activeTexture(gl.TEXTURE2);
        gl.bindTexture(gl.TEXTURE_2D, gbuf.albedo);
        gl.activeTexture(gl.TEXTURE3);
        gl.bindTexture(gl.TEXTURE_2D, gbuf.normal);
        gl.activeTexture(gl.TEXTURE4);
        gl.bindTexture(gl.TEXTURE_2D, gbuf.depth);
        // sun-transmittance caches for the bound pair (units 6/7); the slots were
        // baked in the same rAF they were filled, so no stale cache is possible.
        // Left bound for the precip pass, which reads them too.
        gl.activeTexture(gl.TEXTURE6);
        gl.bindTexture(gl.TEXTURE_3D, shadowTex[pool.slotOf(bind.fa)!]);
        gl.activeTexture(gl.TEXTURE7);
        gl.bindTexture(gl.TEXTURE_3D, shadowTex[pool.slotOf(bind.fb)!]);
        // dBZ plane (unit 8): nearest bound frame (fa). Its slot is guaranteed
        // filled — in dbz mode every resident brick was uploaded with its dbz.
        if (dbzActive && dbzTex) {
          gl.activeTexture(gl.TEXTURE8);
          gl.bindTexture(gl.TEXTURE_3D, dbzTex[pool.slotOf(bind.fa)!]);
        }
        // w plane (unit 9): nearest bound frame (fa), same guarantee as dbz.
        if (wActive && wTex) {
          gl.activeTexture(gl.TEXTURE9);
          gl.bindTexture(gl.TEXTURE_3D, wTex[pool.slotOf(bind.fa)!]);
        }
        // cref plan plane (unit 10, 2D): nearest bound frame (fa), same guarantee.
        if (crefActive && crefTex) {
          gl.activeTexture(gl.TEXTURE10);
          gl.bindTexture(gl.TEXTURE_2D, crefTex[pool.slotOf(bind.fa)!]);
        }
        drawFullscreen(gl);

        // -- pass 2.5: precipitation particles (same target, before tilt-shift so
        //    the DOF treats rain like everything else; volume + depth textures are
        //    still bound on units 0/1/4) ---------------------------------------
        if (precipOn && layer === "hydro") {
          gpu.begin("precip");
          gl.enable(gl.BLEND);
          gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
          gl.useProgram(progPrecip);
          gl.uniformMatrix4fv(loc(progPrecip, "uViewProj"), false, viewProj);
          gl.uniform3f(loc(progPrecip, "uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
          gl.uniform1f(loc(progPrecip, "uMix"), bind.mix);
          gl.uniform1f(loc(progPrecip, "uTimeWall"), tAnim);
          gl.uniform1f(loc(progPrecip, "uXsec"), xsecAxis);
          gl.uniform1f(loc(progPrecip, "uXpos"), xsecPos);
          gl.uniform2f(loc(progPrecip, "uRes"), canvas.width, canvas.height);
          drawPrecip(RAIN, rainVAO.vao, RAIN.count);
          drawPrecip(HAIL, hailVAO.vao, HAIL.count);
          gl.disable(gl.BLEND);
        }

        // -- accumulate: running mean sceneT → accT --------------------------
        // accN==1 overwrites (fresh render, nothing to blend); accN>1 blends the
        // new render with weight 1/accN → a true running average. Because we
        // overwrite on every non-`same` frame, accT is never stale entering a
        // still period (no ghost from the previous convergence).
        gpu.begin("post");
        if (accEnabled && sceneT && accT) {
          gl.bindFramebuffer(gl.FRAMEBUFFER, accT.fbo);
          gl.viewport(0, 0, canvas.width, canvas.height);
          gl.useProgram(progPost); // radius 0 + grade 0 ⇒ plain copy
          gl.uniform1i(loc(progPost, "uTex"), 0);
          gl.uniform2f(loc(progPost, "uRes"), canvas.width, canvas.height);
          gl.uniform1f(loc(progPost, "uMaxRadius"), 0);
          gl.uniform1f(loc(progPost, "uGrade"), 0);
          gl.uniform2f(loc(progPost, "uDir"), 0, 0);
          if (accN > 1) {
            gl.enable(gl.BLEND);
            gl.blendColor(0, 0, 0, 1 / accN);
            gl.blendFunc(gl.CONSTANT_ALPHA, gl.ONE_MINUS_CONSTANT_ALPHA);
          }
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, sceneT.tex);
          drawFullscreen(gl);
          gl.disable(gl.BLEND);
        }
      }

      // -- present to screen (ALWAYS — even when the march was skipped, so the
      //    default framebuffer is never left undefined) -----------------------
      if (converged) gpu.begin("post"); // else still inside the post query
      if (!directToScreen) {
        const postSrc = accEnabled && accT ? accT.tex : sceneT!.tex;
        // FXAA (when on) is the final pass and owns the present-to-screen, so
        // the tilt-shift/blit chain writes into sceneT instead of screen; FXAA
        // reads it back out below. With FXAA off, that chain presents to screen
        // exactly as before (preFxaaFbo === null).
        const preFxaaFbo = fxaaOn ? sceneT!.fbo : null;
        gl.viewport(0, 0, canvas.width, canvas.height);
        if (tiltShift && sceneT && blurT) {
          // tilt-shift H (postSrc → blurT), then V + grade (blurT → preFxaaFbo).
          // Keep the sharp band pinned to the platter: project the diorama
          // centre at ground level and focus there.
          const c = project(viewProj, { x: orbit.target.x, y: orbit.target.y, z: 0 });
          const focusY = Math.min(0.85, Math.max(0.15, c.y * 0.5 + 0.5));
          const maxRadius = Math.min(12, canvas.height * 0.009);
          gl.useProgram(progPost);
          gl.uniform1i(loc(progPost, "uTex"), 0);
          gl.uniform2f(loc(progPost, "uRes"), canvas.width, canvas.height);
          gl.uniform1f(loc(progPost, "uFocusY"), focusY);
          // wider than slice 3's 0.20: at 2× vertical exaggeration the anvil
          // sits far above the focus line and a tight band smears it entirely
          gl.uniform1f(loc(progPost, "uBand"), 0.26);
          gl.uniform1f(loc(progPost, "uMaxRadius"), maxRadius);

          gl.bindFramebuffer(gl.FRAMEBUFFER, blurT.fbo);
          gl.uniform2f(loc(progPost, "uDir"), 1, 0);
          gl.uniform1f(loc(progPost, "uGrade"), 0);
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, postSrc);
          drawFullscreen(gl);

          // V + grade writes into sceneT (fxaa on) or screen (fxaa off). Legal
          // even when preFxaaFbo === sceneT: this pass samples only blurT, and
          // sceneT's composite content was already consumed by the H pass above.
          gl.bindFramebuffer(gl.FRAMEBUFFER, preFxaaFbo);
          gl.uniform2f(loc(progPost, "uDir"), 0, 1);
          gl.uniform1f(loc(progPost, "uGrade"), 1);
          gl.uniform1f(loc(progPost, "uSplit"), split);
          gl.bindTexture(gl.TEXTURE_2D, blurT.tex);
          drawFullscreen(gl);
        } else if (!fxaaOn) {
          // accumulation on, tilt-shift & FXAA off: blit postSrc → screen. When
          // FXAA is on with tilt-shift off we skip this blit and let FXAA read
          // postSrc directly — a blit here would be an illegal sceneT→sceneT
          // read-write when postSrc is sceneT (acc off).
          gl.bindFramebuffer(gl.FRAMEBUFFER, null);
          gl.useProgram(progPost);
          gl.uniform1i(loc(progPost, "uTex"), 0);
          gl.uniform2f(loc(progPost, "uRes"), canvas.width, canvas.height);
          gl.uniform1f(loc(progPost, "uMaxRadius"), 0);
          gl.uniform1f(loc(progPost, "uGrade"), 0);
          gl.uniform2f(loc(progPost, "uDir"), 0, 0);
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, postSrc);
          drawFullscreen(gl);
        }

        // -- pass 4: FXAA — the final present. Reads sceneT when tilt-shift ran
        //    (V+grade wrote it there), else postSrc directly (sceneT or accT).
        //    FXAA writes the screen, never its own source, so no feedback.
        if (fxaaOn) {
          const fxaaSrc = tiltShift ? sceneT!.tex : postSrc;
          gl.bindFramebuffer(gl.FRAMEBUFFER, null);
          gl.viewport(0, 0, canvas.width, canvas.height);
          gl.useProgram(progFxaa);
          gl.uniform2f(loc(progFxaa, "uRes"), canvas.width, canvas.height);
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, fxaaSrc);
          drawFullscreen(gl);
        }
      }
      gpu.end();
      stats.drawn++;

      // dynamic render scale: decide only on frames where the heavy passes
      // ran (a converged still skips the march and would read as free).
      if (autoScaler && !converged) {
        const measured = autoScaler.mode === "gpu"
          ? (gpu.ms.get("geo") ?? 0) + (gpu.ms.get("march") ?? 0) + (gpu.ms.get("precip") ?? 0) + (gpu.ms.get("post") ?? 0)
          : rawDtMs;
        // the target is the cap, but a display slower than the cap is the real ceiling
        const target = Math.max(minInterval, rafPeriod);
        const next = autoScaler.update(measured, target, now);
        if (next !== null) {
          renderScale = next;
          resize();
        }
      }
    }

    // 6. UI readout
    if (!scrubbing) scrub.value = String(tStorm);
    // "storm time" names what the clock counts: simulated time in the storm,
    // NOT wall time — the speed select is a pure multiplier over it (charter).
    clockEl.textContent =
      `storm time ${fmt(tStorm)} / ${fmt(tEnd)} · frame ${pos.i0}/${nFrames - 1}` +
      (buffering ? " · buffering…" : "");

    // scale bar (slice 5c): scene-km per pixel at the look-at depth, converted
    // to REAL storm km — the storm draws at `stormScale`× while the staging
    // stays 1×, so the bar must undo the magnification or it would overstate
    // the storm by that factor.
    if (scaleBarOn) {
      const sb = niceScaleBar(kmPerPixel(orbit, canvas.clientHeight) / stormScale, SCALE_BAR_MAX_PX);
      // guard on whole pixels (so a slow zoom writes ~once per pixel of change)
      // but SET the fractional width — rounding the drawn length would make the
      // bar disagree with its own label by up to half a pixel.
      const px = Math.round(sb.px);
      if (px !== sbLastPx) {
        sbRule.style.width = `${sb.px.toFixed(2)}px`;
        sbLastPx = px;
      }
      if (sb.label !== sbLastLabel) {
        sbLabel.textContent = sb.label;
        sbLastLabel = sb.label;
      }
    }

    if (collectStats) {
      stats.deltas.push(rawDtMs); // raw rAF spacing, ms
      if (stats.deltas.length > 4000) stats.deltas.shift();
      stats.gpu = gpu.snapshot();
      stats.gpuSamples = gpu.count;
      stats.fps = fpsEma;
      stats.rs = renderScale;
      // ?stats HUD line, refreshed 4×/s (a per-frame textContent write forces layout)
      if (now - lastHudStats > 250) {
        lastHudStats = now;
        statsEl.textContent =
          `${fpsEma.toFixed(0)} fps · ${canvas.width}×${canvas.height}` +
          (rsAuto ? ` · rs auto ${renderScale.toFixed(2)} (${autoScaler!.mode})` : ` · rs ${renderScale}`) +
          ` · ${gpu.hudLine()}` +
          (converged ? " · converged (march skipped)" : "");
      }
    }
  }
  requestAnimationFrame(frame);
}

start().catch((e: unknown) => {
  errBox.style.display = "block";
  errBox.textContent =
    `Storm Diorama failed to start:\n${e instanceof Error ? e.message : String(e)}\n\n` +
    `Is a scenario web export present under scenarios/<name>/web/? The dev server\n` +
    `lists packages at /scenarios.json and serves them at /data/<name>/.\n` +
    `(pipeline: export_scenario.py export-web — see docs/design-diorama-web-viewer-2026-07-16.md)`;
});
