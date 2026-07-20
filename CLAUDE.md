# Thunderstorm Simulator

Education/outreach thunderstorm simulator: a headless physics engine (CM1) produces
precomputed storm scenarios; an Unreal Engine 5 app plays them back with volumetric
clouds, lightning, rain/hail, selectable data layers, and teaching UI (sounding/indices
panels, annotations). Progression: single-cell → multicell → supercell, including
modest terrain.

## Core principles

1. **Physics through simulation.** Any parameter that affects storm development
   (CAPE, shear, moisture, terrain, seed) must act through the CM1 simulation — never
   script storm outcomes with empirical if-this-then-that rules. Diagnostic-only
   quantities (radar dBZ, lightning flash rate/placement) are computed from simulated
   fields via published parameterizations, never feed back into the simulation, and
   are labeled as diagnostics in the UI. Every parameterization cites its paper in docs/.
2. **Legibility over photorealism.** The app teaches why storms form: annotations,
   comparisons, and honest "forecast → outcome" panels beat pretty rain.
3. **UE is a dumb player.** All science and derived quantities are computed in the
   pipeline — including skew-T/hodograph plots (rendered to images with MetPy) and
   lightning event lists (positions/times/polarity). Unreal only renders scenario
   packages. Adding a data layer must never require touching physics; adding a
   scenario must never require touching UE code.
4. **Wall-clock matters.** Iterate at coarse resolution (1 km preview, 500 m sanity
   pass), render final resolution once. Real levers: vertical grid stretching,
   `adapt_dt`, reduced/compressed output (netCDF-4 deflate, int16 scale/offset packing
   in post — NOT "half-precision output", which doesn't exist), moving domain
   (`imove` — flat scenarios ONLY, incompatible with terrain; motion is constant and
   estimated a priori via Bunkers), and running two scenarios concurrently at 4 MPI
   ranks each (code is memory-bandwidth-bound; this often beats one 8-rank run).
   Single precision is CM1's default — not an optimization to add. Final resolution
   is chosen only after the Phase 0 benchmark gate. Planning number for 250 m + NSSL
   on this machine: 15–30 h (NOT reliably overnight); 333–500 m may be the realistic
   final.

## Architecture

scenario config (JSON) → CM1 (WSL2 Ubuntu, headless) → netCDF (WSL ext4) → Python
post-processor (WSL: xarray/MetPy; derived fields, terrain-to-Cartesian regridding,
decimation, VDB writing) → scenario package (VDB sequence + surface-layer textures +
plots + event lists + manifest JSON) → scenarios/ → UE5 playback app (Windows)

## Known technical decisions & constraints

- **CM1 config:** Weisman–Klemp analytic sounding; NSSL 2-moment microphysics
  **ptype=27** (27 has a true hail category; 26 is graupel-only); `output_format=2`
  (netCDF); `adapt_dt`; warm-bubble initiation with seeded random perturbations;
  `rstfrq` restart files on long runs (a crash at hour 18 must not be a total loss).
- **CIN is a design task, not a config value:** the WK sounding has no independent
  CIN knob; a modified sounding generator (capped mixed layer / McCaul–Weisman-style
  buoyancy redistribution) is required to dial CIN while holding CAPE.
- **Multicell initiation is a scenario-design decision:** one bubble = one cell;
  multicell needs multiple bubbles, line forcing, or low-level noise.
- **Terrain output is on terrain-following surfaces:** the pipeline must interpolate
  to Cartesian z before VDB export (properly, in Python — CM1's built-in
  interpolation is self-described as quick-and-dirty).
- **UE Sparse Volume Textures are Experimental, with hard limits:** max 2 attribute
  textures / 8 channels total per SVT; all grids share one transform; the bounding-box
  center must be static across the sequence (pad a fixed box); streaming degrades
  above ~30–50 MB/frame — that number IS the decimation budget. Fallback plugin
  (eidosmontreal/unreal-vdb) is archived/unmaintained — test before relying on it.
- **Niagara particles are driven from 2D near-surface textures** (qr/qg baked into
  the surface-layer stack), not by sampling SVTs (dicey).
- **Coordinate/units contract:** CM1 is SI/meters/right-handed; UE is
  centimeters/left-handed (Y flip). The conversion lives in exactly ONE pipeline
  module.
- **AI/editor tooling — Unreal MCP:** default to Epic's **official first-party
  Unreal MCP** (embedded editor MCP server, ships with **UE 5.8**, Experimental).
  Enable via Edit → Plugins → "Unreal MCP" (auto-enables Toolset Registry) → restart;
  wire Claude Code with the console command `ModelContextProtocol.GenerateClientConfig
  ClaudeCode` (writes `.mcp.json` to project root). Binds loopback `http://127.0.0.1:8000/mcp`
  (HTTP+SSE, no auth — local single-node only). Expose only playback/scene-inspection
  tools; never physics — science stays in the pipeline ("UE is a dumb player").
  Decision factors into the UE version pin (favors 5.8). If a hard constraint forces
  UE 5.5–5.7, fall back to a **Remote Control API**–based MCP (e.g. remiphilippe/mcp-unreal)
  to avoid adding maintained C++ to unreal/. Full comparison: docs/decision-unreal-mcp-2026-07-14.md.
- **Frame interpolation is an open decision** (Phase 1): output interval vs playback
  smoothness under time compression — more output frames vs material crossfade
  between SVT frames. Affects both CM1 output config and UE material design.
- **Lightning:** flash rate from graupel flux / updraft volume (McCaul et al. 2009
  style), origins placed in graupel–ice interface regions — computed in the pipeline,
  shipped as an event list; strokes drawn procedurally in Niagara. Explicit
  electrification (COMMAS/WRF-ELEC schemes) considered and deferred: 30–50%+ runtime
  for a visually indistinguishable result.

## Environment

- Dev machine: Windows 11, Ryzen 7800X3D (8C/16T), 64 GB RAM, RTX 5090. The GPU is
  idle during simulation (no production GPU cloud model has hail-grade microphysics) —
  accepted.
- CM1 + post-processing run in WSL2 Ubuntu; the UE5 project runs on Windows.
- CM1 raw output stays inside WSL ext4 — NEVER write simulation output through
  /mnt/* (the 9P bridge is slow). Only finished scenario packages are copied to M:.
- Configure `.wslconfig` (memory ~48 GB, processors 16) and relocate/mount the distro
  VHDX on a multi-TB drive — raw output can reach 300 GB–1 TB per scenario before
  cleanup. Raw output is disposable by design; the scenario package is the durable
  artifact.
- MPI (not OpenMP) on this single node; benchmark rank count once in Phase 0
  (try 6 vs 8 ranks; SMT is likely useless — memory-bound).

## Layout

- sim/ — scenario configs, CM1 namelists, WSL run scripts
- pipeline/ — Python post-processor. VDB writer implementation is documented in
  pipeline/README (pyopenvdb PyPI wheels are stale; candidates are Ubuntu
  `python3-openvdb`, conda-forge openvdb, or a small C++ dense-array→VDB converter)
- scenarios/ — finished scenario packages; the format is a versioned contract
  (manifest carries `format_version`; UE refuses newer major versions)
- unreal/ — UE5 project
- diorama/ — Storm Diorama web viewer (second visualization axis: isometric toy-scale,
  TS + WebGL2, no engine, Black-Hole-Lab architecture; a second "dumb player" of the
  same scenario packages via a web export — docs/design-diorama-web-viewer-2026-07-16.md)
- docs/ — science provenance (every parameterization cites its paper), reviews,
  decision records

## Conventions

- **Vertical exaggeration** is never baked into data; it is applied at render time
  only. Invariants: text/annotations remain undistorted (counter-scale), and particle
  motion remains plausible under exaggeration. (A naive Z-scale on a root container
  distorts glyphs and rain streaks — don't.) Useful range 1×–3×.
- **Time:** frames carry storm-time stamps; playback speed is a pure UI multiplier.
- **Seeds/reproducibility:** every scenario records its seed(s), CM1 build (binary
  hash, compiler flags), rank count, and domain decomposition. Verify bitwise
  reproducibility once in Phase 0; if unachievable, the contract downgrades to
  statistical equivalence + recorded output checksums.
- **Data/git policy — RESOLVED 2026-07-20 (owner):** raw netCDF is regenerable and
  never committed. Scenario packages live **in `scenarios/<name>/` inside the project
  folder**, but their payload stays **out of git history** — and **no Git LFS anywhere
  in this repo**. So "out of repo" means out of *history*, not out of the folder: the
  repo, the diorama dev server (`diorama/vite.config.ts` resolves
  `../scenarios/single_cell_500m/web`) and the UE project all see one path with no env
  wiring. `manifest.json` **is tracked** (the `!scenarios/**/manifest.json` negation) —
  it is the versioned contract UE checks `format_version` against, and a contract that
  isn't version-controlled isn't a contract; ~48 KB per 301-frame package. Nothing
  >10 MB in plain git. **Consequence, accepted:** packages are not backed up by git —
  regeneration from `sim/` + `pipeline/` is the recovery path (7.5 min for the Phase 1
  package). Rationale + layout: `scenarios/README.md`.

## Pinned versions

Keep current — SVT behavior shifts between UE releases. Filled through Phase 0:
- **CM1:** cm1r21.1 (binary sha256 in docs/phase0-cm1-build.md).
- **WSL/toolchain:** Ubuntu 24.04, gfortran 13, OpenMPI 4.1.6, netCDF C+Fortran
  (system libs). MPI, single node.
- **Python env lockfile:** **RECORDED — pipeline/ENVIRONMENT.md + pipeline/env-vdb.yml
  (2026-07-15).** Two envs, different interpreters, deliberately no `requirements.txt`
  (system python is `EXTERNALLY-MANAGED`; a pip file would advertise reproducibility that
  doesn't exist). (a) **Pipeline runtime = system apt** on Ubuntu 24.04.4: python3
  **3.12.3**, numpy **1.26.4**, scipy **1.11.4**, netCDF4 **1.6.5** (matplotlib 3.6.3 is
  installed but NOT load-bearing — no MetPy; plots are Phase 2/4). (b) **VDB writer =
  micromamba conda-forge `vdb` env**: openvdb **13.0.0** on python 3.14.6 — a *runtime*
  dep of `export` (dense2vdb dynamically links `envs/vdb/lib`), not build-time-only.
  Spike-grade: records what is true; `--explicit`/apt-pin hardening deferred to Phase 2.
- **OpenVDB:** conda-forge **openvdb 13.0.0** (writer lib; on-disk file-format
  **v225**) — **PIN LOCKED, empirically confirmed against UE 5.8 (2026-07-14, Phase 1
  task 3, docs/phase1-task3-svt-import.md).** UE 5.8 bundles the identical
  `openvdb-13.0.0` (`OPENVDB_FILE_VERSION = 225`), and its `USparseVolumeTextureFactory`
  imported the full 300-frame v225 sequence headless into a 300-frame
  `AnimatedSparseVolumeTexture` (160×160×64; Tex A RGBA16F = cloud/ice/rain/graupelhail,
  Tex B R16F = dbz; 21 s build). Only *visual streaming playback* remains an owner-gated
  editor check.
- **UE 5.x.y (exact):** **5.8.0** (`5.8.0-55116800+++UE5+Release-5.8`, CL 55116800).
  Installed and launches (2026-07-14). Note: the Epic launcher must be **Run as
  administrator** on first UE launch or the VC++ prereq install fails with
  `LS-0019-IS-*`.
- **Unreal MCP:** **official/embedded** (UE 5.8 ships it; confirmed available in
  the 5.8.0 install's plugin list). No Remote Control fallback needed. Enable via
  Edit → Plugins → "Unreal MCP" (auto-enables Toolset Registry) → restart, then
  wire Claude Code with `ModelContextProtocol.GenerateClientConfig ClaudeCode`.

**Production run config (locked by Phase 0 benchmark gate — docs/phase0-benchmark.md):**
`mpirun -np 8`, no explicit core binding, NSSL `ptype=27`. Final resolution
**333 m default** (overnight-able incl. terrain), **250 m** for flat/imove hero
runs (no terrain), **500 m** preview tier. Reproducibility verified **bitwise**.

## Status / phasing

Do not start a phase without explicit go from the owner.

- **Phase 0 (benchmark gate COMPLETE — 2026-07-14):** CM1 built in WSL
  (docs/phase0-cm1-build.md); canonical Weisman–Klemp supercell validated
  (docs/phase0-validation.md — split into counter-rotating movers, peak w 60.6 m/s
  @ 83 min, PASS); throughput benchmarked and **benchmark gate resolved**
  (docs/phase0-benchmark.md — 333 m default / 250 m flat hero / 500 m preview; np=8;
  bitwise reproducible). .wslconfig set (48 GB / 16 proc).
  **VHDX relocation — DONE (2026-07-14):** the Ubuntu WSL VHDX was moved off C:
  (the OS NVMe) to **`M:\wsl\Ubuntu\ext4.vhdx`** (Toshiba 7.4 TB HDD). Method:
  `wsl --terminate Ubuntu` → copy VHDX → repoint the distro's registry `BasePath`
  (`HKCU\...\Lxss\{5b1d55ef-…}`) to `M:\wsl\Ubuntu` → verified boot from M: (user
  `boiko`, write test PASS). CM1's raw-write path averages only tens of MB/s, so the
  HDD is not an I/O bottleneck. Two follow-ups: (a) the stale old copy on C: is still
  locked by the WSL utility VM and clears on the next full `wsl --shutdown` — not worth
  blipping BOINC/Docker for 7.6 GB; (b) the VHDX max virtual size is **1024 GB
  (default)** — fine for Phase 1's 333 m workhorse (raw ≪ 1 TB), but the **250 m-terrain
  hero runs (Phase 3) can approach 1 TB raw and would hit this ceiling. Provision the
  VHDX larger before the first hero run** (`wsl --manage Ubuntu --resize`, then
  `resize2fs`) — but NOT to 2 TB: M: is a ~72%-full backup drive, so the cap must stay
  below M:'s safe headroom (owner's call on the exact number). ⚠ **ACL gotcha for
  relocated VHDXs (hit + fixed 2026-07-16):** distro start re-grants disk access to the
  utility VM's per-boot SID under the USER's session token, which needs WRITE_DAC on the
  VHDX — implicit under `%LOCALAPPDATA%`, absent on M: (`Authenticated Users:(M)` only).
  Symptom: `Wsl/Service/CreateInstance/MountDisk/HCS/E_ACCESSDENIED` after any Host
  Compute Service restart, while `wsl --mount --vhd … --bare` of the same file works.
  Fix applied: `icacls M:\wsl /grant "boiko:(OI)(CI)F"` (+ on ext4.vhdx). Details in
  docs/phase1-svt-streaming-views-rootcause.md.
- **Phase 1:** pipeline de-risking spike — a full-length, multi-grid,
  few-hundred-frame VDB sequence through UE SVT (explicitly NOT a one-frame demo);
  single-cell storm playback end to end. **Task 3 import/build VALIDATED; visual
  playback PENDING OWNER (2026-07-14, docs/phase1-task3-svt-import.md):** full 300-frame
  v225 synthetic sequence imported headless into a 300-frame `AnimatedSparseVolumeTexture`
  in UE 5.8 — all three non-visual binding tests pass (frame count, multi-grid channel
  identity, static bbox) → openvdb pin locked. The task's namesake **in-editor visual
  streaming playback is still owed by the owner** (owner-gated handoff in the task doc).
  **Task 5 (real post-processor) COMPLETE — 2026-07-15, docs/phase1-task5-pipeline.md:**
  `pipeline/cm1post/` + `export_scenario.py` turn real CM1 netCDF into a 301-frame VDB
  sequence + manifest (0.46 GB; **peak 3.51 MB/frame** vs the 30–50 MB budget; imports
  headless into a 301-frame SVT in 11.6 s). The spike caught two silent contract errors
  the synthetic fixture could not: the locked 40×40 km crop **clipped** the real cold-pool
  outflow (real half-width 23.25 km → box now 52×52×18 km), and `ice = qi` **dropped
  snow** (→ `qi+qs`; qs/qi ≈ 0.29–0.53 by mass). Both amended into
  docs/phase1-svt-budget.md. **Known UE behaviour:** the SVT factory unions active voxels
  across the sequence and tightens/re-bases the box (208×208×72 @ −25875 → 186×186×65 @
  −23125) — lossless, and the UE app must take placement from the **asset's transform**,
  never the manifest's `origin_m` (adding it on top lands the volume 2750 m off).
  **RENDER FIXED (2026-07-15 evening) — docs/session-handoff-2026-07-15-visuals.md:**
  the storm renders full-size (46.5 km) on a real GPU in Simulate. Root causes: (1) the
  placement rule was wrong — on a real RHI the component DOES apply the SVT frame
  transform, so the correct actor transform is **scale=100 (m→cm), location=(0,0,0)**
  (the ×25000 rule made it 250× oversized; manifest `ue_placement_rule` corrected and the
  shipped manifest regenerated, 2026-07-16); (2)
  `r.HeterogeneousVolumes.MaxTraceDistance` 300 m default → 100 km (persisted in the probe
  project ini); (3) **the editor world never streams non-resident SVT frames** — frame 0
  only; all visual verification must run in Simulate/PIE. Visual-improvement work (scene
  foundation done: physical sun 75000 lux, manual exposure, fog, 200 km ground plane,
  ambient VolumetricCloud; density/albedo tuning + rain/hail/lightning pending) is in the
  handoff doc. **The "lowest-mip / blob" issue is SOLVED (2026-07-16 session 3,
  docs/phase1-svt-streaming-views-rootcause.md): root cause was `bIssueBlockingRequests=true`
  on the HeterogeneousVolumeComponent (engine default false; left on while debugging).
  The debug overlay's "Requested Mip: 3.4e38" was an artifact — that field excludes blocking
  requests by design and is NOT a view counter; the earlier "view-driven / zero views /
  second gate" theories are retracted. With the flag false, the editor world streams fine
  over MCP (offscreen captures, no PIE, no clicks; visible-but-unfocused editor window with
  `bThrottleCPUWhenNotForeground=false` suffices). Overlay residency bars scale ×1.5 at
  150 % DPI (frame-255 bar is off a 1700 px capture — test with frame <120). The
  StormVolume actor + fix are SAVED to disk (owner Save All, 2026-07-16) and the debug
  scaffolding is torn down (BP_ConsoleExec BeginPlay reduced to two idempotent
  debug-off resets; `bThrottleCPUWhenNotForeground=False` persisted in editor prefs;
  inject_view.py deleted).** **Lighting/exposure pass DONE (2026-07-16 session 4,
  docs/phase1-lighting-pass-2026-07-16.md): scene reads as daylight, storm legible at 35 km
  (EV bias −13, fog 5e-5/falloff 0.01, template VolumetricCloud hidden — it camouflaged the
  storm; frame 150 is the classic-Cb hero frame, NOT 255 which is late-stage diffuse; all
  unsaved pending owner Save All). Two hard-won rules: MI scalar edits apply only at the
  NEXT PIE start (never live — sweeps need one Simulate cycle per value; the 07-15 "live in
  PIE" claim and the 07-16 sweep2 results are retracted), and `Density Scale` saturates
  visually above ~1 on the engine default SparseVolumeMaterial — core solidity needs the
  task-5 custom material, not this knob.**
  **Custom SVT volume material DONE + SAVED (2026-07-16 session 5,
  docs/phase1-svt-custom-material-2026-07-16.md):** /Game/SVT_REAL/M_StormVolume (+ MI,
  bound to the component and saved to disk over MCP) maps the four hydrometeor channels
  to physical extinction (Extinction→MP_SubsurfaceColor, Albedo→MP_BaseColor; SVT param
  name must stay "SparseVolumeTexture"; weights 1.0 cloud / 0.10 ice / 0.02 rain /
  0.005 graupelhail × "Extinction Scale", default 1000 by sweep — solid core,
  translucent anvil; no saturation, each decade a distinct step). Persistence lesson:
  the level is One-File-Per-Actor — component edits dirty the actor package under
  `__ExternalActors__`, never the map package, and `AssetTools.save_assets
  {"asset_paths": []}` saves everything headlessly (no owner Save All needed).
  Unreal MCP is now fully wired: EditorToolset /
  NiagaraToolsets / ConfigSettingsToolset plugins enabled in SvtProbe → 25 toolsets incl.
  CaptureViewport, StartPIE/StopPIE, generic property access, material/Blueprint authoring.
  **Method lesson, load-bearing:** `-nullrhi` underpinned all of task 3's and task 5's
  binding validation and is **structurally incapable** of catching render defects — it
  reported `verdict = READY` over an unsaved level, a lightless scene, a non-persisting
  actor label, and a screenshot loop that wrote no files. Any future "SVT works" claim
  must come from a real RHI.
  **PHASE 1 CLOSED — 2026-07-20, docs/phase1-completion-2026-07-20.md.** Both former
  "still open" items are resolved: the **package-storage decision** (owner, 2026-07-20 —
  in-tree under `scenarios/`, payload out of git history, no LFS; see the Data/git policy
  above) and the **Python env lockfile** (recorded 2026-07-15 — pipeline/ENVIRONMENT.md +
  pipeline/env-vdb.yml; see Pinned versions). The Phase 1 spike package is consolidated in
  `scenarios/single_cell_500m/` (525 MB) with its `manifest.json` tracked in git.
  **Two owner-owed live checks are carried forward, NOT discharged** (both are
  "Claude-verified on a real RHI / owner not yet signed off", the same class as the
  diorama's): task 3's namesake **in-editor visual streaming playback** — the capability
  is proven (07-15/07-16 render, streaming and material sessions all ran on a real RHI in
  Simulate), but the owner has never formally signed it off; and the **diorama 5c pan
  gestures**, driven only by synthetic PointerEvents (see the design doc's OWNER-OWED
  note). Neither blocks Phase 2.
- **Phase 2:** scenario system + selectable UI layers + radar view.
- **Phase 3:** multicell/supercell scenarios + seed-driven outcome variation + terrain.
- **Phase 4:** lightning, hail swaths, rain/hail particles, polish.

Full advisor pressure-test of this plan: docs/advisor-review-2026-07-09.md
