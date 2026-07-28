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
  >10 MB in plain git. **AMENDED 2026-07-22 (owner, Phase 3 T2): `web/web_manifest.json`
  is tracked too.** A **web-only** package now exists (`supercell_333m` — no VDB, owner's
  §4.2 call), and for it the web manifest is the *only* contract: `manifest.build()` is
  SVT-shaped (per-VDB frame records, `SVT_TEXTURE_MAP`, `ue_placement_rule`), so building
  one with no VDB would advertise an SVT payload that isn't there. The rule is
  `scenarios/**/web/*` — **not** `scenarios/**/web/`, because git does not descend into
  an excluded *directory* and the directory form makes the negation unreachable.
  **Consequence, accepted:** packages are not backed up by git —
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
- **Phase 2 (STARTED 2026-07-20, owner go):** scenario system + selectable UI layers +
  radar view. Plan + task breakdown: `docs/phase2-plan-2026-07-20.md`.
  **Scope pinned by the owner:** diorama-first (**no UE app this phase** — `unreal/`
  stays empty, everything Claude-verifiable without an owner-gated editor); radar view =
  **2D composite-reflectivity plan view** (`cref`, view-independent — NOT the existing
  3D dBZ layer, which is a view-ray MIP); layers = **new physical fields** (updraft `w`)
  not just toggles; second scenario = **cheap single-cell variant** (advisor:
  a sheared storm is Phase 3 content, and the Y-flip motivation for it died with the UE
  deferral — **carried item #1 is deferred with the UE app, not discharged**).
  **T1 scenario system DONE (commits 89f0cf4, 6495960).** `cm1post/config.py` split into
  **`contract.py`** (frozen per `format_version`: channel names/order, SOURCE_FIELDS,
  thresholds, SVT texture map) and **`scenario.py`** (per-scenario: run dir, export
  voxel, crop box; NX/NY/NZ/ORIGIN_M now derived, so a scenario cannot declare a grid
  inconsistent with its own crop). Scenario configs live in `sim/scenarios/<name>.json`;
  `export_scenario.py` takes `--scenario`. Built as a **pure refactor with zero output
  change**, so all four regression gates are exact byte-identity: VDB manifest (34810
  chars) + `.densevol` (62300266 B) + web manifest (45381 chars) + web bricks, the array
  gates A/B'd against pre-refactor code extracted with `git archive` (no worktree).
  **Gate the data, never the container** — `.vdb` is not byte-reproducible and `.gz`
  carries an mtime in its header, so both would false-fail a naive `cmp`.
  **DECISION: `w` and `cref` are web-export-only this phase** — `contract.CHANNELS` and
  the SVT map stay frozen, because changing them forces an SVT import re-test that
  cannot happen (owner-gated editor; `-nullrhi` structurally can't validate render).
  Tex B keeps 3 spare channels for a deliberate later promotion.
  **Re-export is batched** after T3 (linear-Z dBZ) + T4 (`w`) + T5 (`cref`); T3 is where
  byte-identity is *supposed* to break.
  **T1c deck generator DONE** — the scenario system now drives *both* halves:
  `pipeline/gen_deck.py` + `cm1post/deck.py` render `sim/scenarios/<name>.json` over
  `sim/templates/base.namelist.input`, so a scenario cannot be simulated with one
  geometry and exported with another. **Template + overrides, never full generation**
  (~8 KB of Phase 0 numerics must not drift): 17 of 413 lines are touched, 396 stay
  byte-identical to the template and 410 to the committed hand-written deck.
  Substitution is **line-anchored text replacement** (`^\s*KEY\s*=`) — unanchored, `dz`
  also hits `dz_bot`/`dz_top` and `dx` hits `dx_inner`/`dx_outer`, and the corrupted deck
  still *runs*, just not the simulation asked for. The 17 keys are **four categories**,
  only the first in the JSON: scenario identity (required, never template-defaulted),
  geometry-derived (`tot_x_len` etc.), motion-coupled (`umove`/`vmove` forced 0 at
  `imove=0`, required at `imove=1`), and the `&param9` output block (template DNA).
  **The output block is ASSERTED, never generated** — deriving it from
  `contract.SOURCE_FIELDS` would shrink the deck (the validated deck writes `tke`, `uh`,
  `vort`, `lcl`/`lfc`/`pwat` that the analysis scripts use) and break the gate; instead
  `deck.check_output_flags` refuses unless `output_q`/`output_dbz`/`output_winterp` are
  on, which catches a run that burns hours and then turns out to have written no `dbz`.
  Gate: **344/344 keys reproduce** the hand-written `sim/single_cell/namelist.input` by
  parsed value (**not text** — the hand decks are not column-consistent, ` ptype =  5,`
  vs ` ptype =  27,`), and it is **non-circular** because the template is the Phase 0
  *validation* deck, so all 17 keys genuinely differ. **12/12 negative controls fire**
  (wrong-reference, substring clobber, missing/typo'd key, `imove` contradictions,
  output flags off, derived-geometry propagation) — a gate that has only ever passed is
  not yet known to work. **The claim earned is "reproduces the RUN", not just the deck:**
  the 3 residual text diffs are insignificant in Fortran free-format (both sides parse to
  the identical REAL), and with `isnd=5` the WK sounding is computed internally, so the
  namelist is CM1's *sole* scenario input — same binary + ranks ⇒ bitwise-identical run,
  inheriting the Phase 0 reproducibility verification. That is what makes the data
  policy's "regeneration from `sim/` + `pipeline/`" recovery path real. Faithfulness
  only, and *structurally* so: with one hand-written reference deck in existence T1c
  cannot prove more, since every future scenario's deck **is** the generator's output —
  cross-scenario generalization rides on T6. **T6 scoping note:** the unknown-key guard
  means a variant may differ only in the 22 `REQUIRED_KEYS` + `umove`/`vmove`, so
  "cheap" = a **grid/domain change**; a seed variant needs a new required key, and bubble
  geometry (`init3d.F`) or sounding thermodynamics need actual code. A **generic
  `run_scenario.sh`** is also deliberately left to T6 (`sim/single_cell/run.sh` still
  hardcodes run dir/ranks/provenance).
  **T2 DONE — manifest `web` block + `format_version` 1.1 (Phase 1 carried item #2
  DISCHARGED, no re-export).** The block is a **POINTER, not a census**: it carries
  `dir`/`manifest`/`web_format_version`/`consumer` and deliberately copies **no** grid,
  frame count, byte totals or qmax. That reason killed a whole rejected design (a
  `link-web` subcommand + cross-manifest consistency check + negative-control suite):
  `web/` is gitignored and regenerable while `manifest.json` is tracked, so any copied
  figure is false on a fresh clone and stale after re-export, while `web_manifest.json`
  stays authoritative. **A copy needs a consistency check; a pointer does not** —
  nothing duplicated, nothing to drift. Keeping it static also dodges the ordering
  problem (`export` writes the manifest *before* `export-web` runs) and keeps
  `manifest.build()` a **pure function of (Scenario, frames, provenance)**, which is what
  the gate rests on. **Versioning rule now written down:** MINOR = additive, 1.0-era
  readers keep working; MAJOR = channel names/order, SVT map, encodings, transform/units,
  layout. Load-bearing, not bookkeeping — a minor bump is the only safe kind while the
  UE contract stays frozen for want of an SVT re-test. `WEB_FORMAT_VERSION` moved into
  `contract.py` (webvol re-exports it, same pattern as `SVT_TEXTURE_MAP`) and **stays
  1.0** — the brick format is untouched, and the diorama checks only that field and never
  reads `manifest.json`. **Gate = T1b's diff, not a new control suite:** rebuild from
  committed inputs → exactly 2 structural differences (`format_version`, added `.web`)
  plus a census-leak check, then **revert those two and the bytes are identical (34810
  chars)** — which is what rules out a reordered key or reformatted float that "only 2
  changes" alone would permit. T1b's one-shot trick is now a standing gate:
  `pipeline/tests/test_manifest.py` **8/8**, reading committed files only (a second
  dividend of the tracked-manifest policy); T1c's 13 deck controls still pass. **A census in PROSE is still a census** (advisor, post-commit): the block's prose enumerated "two files per frame", which the structured key check cannot see and which T4/T5 falsify (signed `w` cannot ride in the 4-channel rgba plane) — inside a *tracked* contract file. Now an 8th regex gate, **fired against the pre-fix manifest before it passed**. `manifest.write`/`webvol.write_manifest` also pin `newline="\n"`: rebuilding a WSL-written package file from Windows silently CRLF-ed all 1932 lines, invisible to gates that read back in universal-newline mode.
  **T3 DONE — dBZ resampled in LINEAR Z (Phase 1 carried item #3 DISCHARGED).** `regrid.resample_dbz` converts to Z = 10^(dBZ/10), interpolates, converts
  back; both dbz call sites route through it. **A separate function, deliberately** — folding
  Z-space into the generic `resample()` would corrupt the four mixing-ratio channels sharing
  it. The error was **not cosmetic**: a 20/40 dBZ pair interpolates to 30.0 in dB vs the
  correct **37.03**, and on real frame 150 the peak correction is **+13.35 dB** with **6.53 %**
  of export voxels moved (this export upsamples 2×, so nearly every voxel is interpolated).
  **§9 says byte-identity is supposed to break here, so the gate had to be POSITIVE**
  (`pipeline/tests/test_regrid_dbz.py`, 10/10): a hand-computed midpoint that fails if the
  transform is dropped *or* applied twice; the **Jensen invariant** (10log₁₀ is concave ⇒
  `new ≥ old` everywhere, equality only at grid points) as the whole-field replacement for
  byte-identity; and no-inflation (interpolated Z ≤ max contributing Z), which is *why* the
  web `qmax` stays a valid bound and **why T3 cannot grow the bbox**. The Jensen gate is an
  inequality and `new ≥ old` also holds when new *is* old — its no-op and reversed-arrow
  negative controls are the only thing separating it from a gate that always passes. The
  bbox sweep is untouched either way: `active_mask` runs on the **native CM1 grid**,
  pre-resample. **`format_version` stays 1.1 — a DATA change is not a FORMAT change.**
  T3 first bumped it to 1.2; that was scope creep past the plan (§9 scoped the manifest
  deliverable to rewriting `caveat`, no bump) and is reverted. No channel name, order,
  encoding, texture map or layout moved, so a 1.0-era reader renders a linear-Z package
  and §7's SVT freeze holds; the method is recorded in `diagnostics.dbz.resampling`, where
  a consumer actually looks — which made the bump **redundant with the key added in the
  same change**, while costing a contract-vs-shipped skew hardcoded into two gates. A
  version number that moves for data changes stops meaning "format". **The shipped package
  is deliberately left stale** (re-export batched behind T4/T5 — a manifest regenerated now
  would advertise linear-Z over dB-resampled bricks, i.e. lie), so `test_manifest.py` reuses
  T2's trick: name the 2 expected diffs, revert them, require the rest byte-identical —
  **15/15 incl. 7 negative controls**, one a same-length edit (35838 chars either way) that
  a length check would miss.
  **T4 DONE — updraft `w` exported as a web-only field.** Source is `winterp` (already on
  scalar points — no destaggering). `w` violates three assumptions the five-channel path
  rests on, and the SIGNED one is the hazard: `regrid.resample` ends with `clip(0, None)`,
  so routing `w` through it **zeroes every downdraft** — no crash, no warning, just a storm
  whose air only goes up. Hence `regrid.resample_signed`, a separate entry point rather than
  a flag a caller can forget (T3's lesson: *a shared resampler encodes an assumption one
  field violates*). Encoding is **signed uint8 symmetric about code 128**, codes 1–255, code
  0 never occurs — rejected the affine map over the observed range because `w=0` then lands
  on a FRACTIONAL code (measured: code 91 → +0.02 m/s), painting false vertical motion along
  the updraft/downdraft boundary, the one feature a viewer reads off this field. Scale is
  **FIXED cross-scenario at ±80 m/s**, not per-sequence, so the same colour means the same
  m/s in every package (T6 exists to compare scenarios): this cell peaks +54.8 but the Phase
  0 supercell hit +60.6, so a per-sequence scale would ALREADY disagree between two runs
  made here and a 60 m/s scale would ALREADY clip one. Exporter **errors** rather than
  silently clipping if a sequence exceeds it. No deadband baked into the byte — transparency
  is a T8 render decision. **Crop caveat MEASURED, not asserted** (301-frame sweep): the
  condensate-sized box clips **0.000%** of |w|≥10 m/s and **0.005%** of ≥5 m/s (peak clipped
  6.30 m/s); the 10.8% at ≥0.5 m/s is broad environmental subsidence. Box NOT resized — it
  is shared with the VDB, whose bbox centre must stay static. Gates: `test_regrid_w.py`
  **10/10**, positive (byte-identity is unavailable when a change adds output by design), the
  key one being *a purely-negative field survives*, which also DEMONSTRATES the failure
  (`resample` → +0.000) so it is not just asserting today's code; 3 negative controls each
  reject a design actually considered. Verified end to end on real CM1: round-trip within
  exactly the half-quantum, 235 048 negative voxels present, and **`rgba` bricks
  BYTE-IDENTICAL to the shipped package** while `dbz` differs ≤51 codes (T3's correction,
  exactly where §9 puts it). **`WEB_FORMAT_VERSION` 1.0 → 1.1; package `format_version`
  stays 1.1.** The rule that settles this: *T3 changed values inside existing files → DATA →
  no bump; T4 adds a file, a block and an encoding → FORMAT → MINOR bump.* MAJOR would lock
  out `volume.ts` (`SUPPORTED_MAJOR = 1`, checked not assumed) — the very viewer T8 extends.
  Unlike T3's bump it is NOT redundant with a key added alongside it: the version declares
  the GENERATION, `extra_fields.w` declares the CAPABILITY, and **T8 must feature-detect on
  the key**. T4 is also the **first time `contract` moves AHEAD of the shipped package on a
  version number** — which broke `gate_web_block_present` (it asserted shipped == contract
  and has no revert mechanism); resolved by treating the skew as a named expected diff.
  `test_manifest.py` now **17/17**.
  **T5 DONE — composite reflectivity `cref` as a 2D web-only plan product
  (docs/phase2-plan-2026-07-20.md §15).** The whole design rests on one measurement taken
  BEFORE any code: CM1's `cref` is **BITWISE identical to `dbz.max(axis=0)`** in every one
  of 301 frames (worst |Δ| 0.000e+00, both maxima 72.213715 dBZ) — so `vmax` is borrowed
  from the dbz channel as an **identity**, one NWS colormap serves both views exactly, and
  the max-then-interp ordering invariant (`cref ≥ colmax`, never reverse; 0 violations on
  real frames) is licensed. **Rejected** computing cref as colmax of the *exported* dbz
  (biases −3.01 dB, silently redefines a standard radar product to "the part we
  exported"); took CM1's, per the charter. A **separate** `plan_fields`/`WEB_PLAN_FIELDS`
  block (not a `dims` key in T4's `extra_fields`) because RANK is the one thing a consumer
  can't discover from a raw brick — a 2D plane uploaded into a 3D texture is a silent
  garbage render. Caveat MEASURED (truncation above the 18 km box costs cref **0.000000
  dBZ** — no echo up there), then rewritten twice: the first fix committed **the T2 error
  one level over** — it asserted run-specific numbers ("~2 dB", "301 frames") inside the
  GENERIC per-scenario builder, where they'd ship into *every* scenario's manifest (T6
  would emit single_cell's figures into scenario #2's contract). Prose now keeps only
  STRUCTURAL claims; per-scenario numbers are computed into `observed_min/max`. A new
  `gate_no_run_specific_numbers_in_prose` fired against the pre-fix draft. Exporter carries
  a STANDING version of the identity check (fails export if a plan field's observed max
  exceeds the channel max it borrows). `test_regrid_cref.py` **13/13** (two gates rewritten
  after first passing: a tautology that encoded the same values twice, and an "applied
  twice" arm that overflowed to inf so the inequality held trivially). **`WEB_FORMAT_VERSION`
  1.1 → 1.2; package `format_version` stays 1.1.** Same rule as T4: adds a per-frame file +
  block → FORMAT → MINOR; MAJOR (tempting because the file has a different RANK) would lock
  out `volume.ts` (`SUPPORTED_MAJOR=1`) — the viewer T9 extends. **T9 feature-detects on
  `plan_fields.cref`, never the version.**
  **T6 DONE — second scenario `single_cell_333m` + generic runner + the batched T3–T5
  re-export (docs/phase2-plan-2026-07-20.md §16).** Three things landed together (owner
  folded §9's re-export into T6). (1) **The variant is a pure resolution change** and the
  deck PROVES it: `single_cell_333m` is the same zero-shear pulse cell at 333 m, and it is
  the first config the deck generator was NOT reverse-engineered from, so T6's gate is
  **differential** — its generated deck vs scenario 1's generated deck differs in **exactly
  9 of 344 keys** (5 declared: nx/ny/dx/dy/dtl + 4 derived), the VERTICAL grid byte-identical
  (dz/nz/ztop/stretch_z are not scenario keys). Run health = same storm family, shifted the
  way a finer grid should shift it: peak w **67.5** (vs 53), max dbz **78.0** (vs 71), max
  qhl **9.09 g/kg** (vs 4.7) — that shift IS the pedagogical signal, not noise. (2) **The box
  is condensate-driven horizontally, `w`-driven vertically** — the non-obvious T6 result,
  and it only surfaced because the box was MEASURED not matched. Condensate union (half
  20.48 km, top 16.25 km) is *narrower* than the 500 m cell (finer grid → more compact
  core), so tight-horizontal is right; but a condensate-tight z-top **clipped a 19 m/s
  updraft core** — the stronger 333 m updraft OVERSHOOTS the cloud top (significant |w| to
  17.25 km at ≥10, 18.75 km at ≥5). `w` is the only shipped field `active_mask` doesn't
  contain (signed, web-only). Final box **126×126×54 @ 333 m NATIVE voxel** (matching the
  500 m package's 250 m would UPSAMPLE 1.33×, the anti-pattern its own config apologises
  for), crop 20979/17982; symmetry measured **0.0 m** (centred storm); bbox PASS against the
  FINAL box. w-clip MEASURED at that box: |w|≥10 **0.0000%**, ≥5 0.0128% (peak clipped 6.98
  m/s) — same character as 500 m's caveat, weak motion in the 17.8–18 km damping layer.
  Package: VDB 0.19 GB peak 1.43 MB/frame, web 0.042 GB, w observed −48.15..+67.48 (inside
  ±80). (3) **Batched re-export**: `single_cell_500m` regenerated as linear-Z + w + cref
  (web 1.2); the bbox held (T3/T4/T5 did not move it). `test_manifest.py`'s staleness
  scaffolding TORN DOWN — `manifest.build()` now reproduces the shipped manifest
  byte-for-byte (36220 chars), so `gate_byte_identical` collapsed to a plain `==` and
  `gate_web_block_present` asserts shipped==contract (1.2); one negative control had gone
  no-op (it set the caveat to the now-current text) and was repaired to inject a wrong-dB
  string. Generic **`sim/run_scenario.sh`** (+ `scenario_info.py`, reads config through the
  real loader not grep) closes §10.6; `sim/single_cell/run.sh` deleted; a
  `require_measured_box` guard refuses export on a placeholder box but lets bbox/deck-gen
  through (no new-scenario deadlock). `test_scenario_t6.py` **11/11**, all suites green; the
  new package tracks **only manifest.json** in git (payload out of history, verified).
  **T7 DONE — diorama scenario selection (docs/phase2-plan-2026-07-20.md §17).** The dev
  server serves every `scenarios/<name>/web/` at `/data/<name>/` and lists packages at
  `/scenarios.json` (enumerated per request — a fresh export appears without a restart);
  the viewer picks one via a control-bar picker (shown only when ≥2 served) or
  `?scenario=<name>`, default `single_cell_500m`. **A switch RELOADS the page, it does not
  rebuild GL state** — the key call, and it turns on the fact that the viewer is ALREADY
  grid-agnostic within a load (nx/ny/nz, `volumeBox`, decode constants, cache dims, the
  24-slot ring all derive from the loaded `web_manifest.json`); the only things pinning it
  to one package were the hard-coded `DATA_DIR` + single manifest URL, both startup values.
  The two packages differ in GRID (208×208×72 @ 250 m vs 126×126×54 @ 333 m), so every GL
  resource is sized to a grid captured in the `start()` closure; a reload re-derives all of
  it cleanly (zero half-updated GL state) vs a large refactor of a 1000-line file to rebuild
  in place for no user-visible gain. Reload PRESERVES every other URL param (`scenarioSwitchUrl`
  sets only `scenario`), so the view/tuning survive. Beyond routing the data path through
  `root = dataRoot(scenario)`, the viewer needed NO change to render a different grid. Pure
  logic in `src/scenario.ts` (resolve precedence / switch-URL / label), `test/scenario.test.ts`
  **11/11**, full suite **117/117**. **Real-GPU verified** (headless Chrome, HUD polled to a
  streamed non-buffering frame — the standing no-`nullrhi` rule): both grids AND dbz-on-the-
  switched-scenario render end to end; the 333 m cell reads visibly more compact (the finer-grid
  signal). Security: scenario segment sanitized (`[A-Za-z0-9_.-]`, no `.`/`..`) + `startsWith`
  guard; the encoded-traversal 200 is vite's own dev module serving on `next()`, NOT the handler
  (body is the transformed module, not raw fs bytes) — universal vite-dev, dev-only. **No version
  moves** (viewer + dev-server only; the web manifest already carries `grid`).
  **T8 DONE — data-layer panel + updraft `w` (§18).** Teaching-grade top-right radio panel
  (Hydrometeors / Radar (dBZ) / Updraft (w)) with a manifest-driven DIAGNOSTIC badge, plus
  the `w` render path: the signed field streams parallel to the dbz ring (gated + lazy, hydro
  byte-untouched) and renders as a signed max-|w| view-ray projection on a colorblind-safe
  coolwarm map, colour domain FIXED at ±`extra_fields.w.scale` (same red = same m/s across
  packages — the 500 m/333 m cells compare directly). Feature-detected on `extra_fields.w`;
  viewer-only. Real-GPU both grids; hydro bit-identical with `w` off. 125/125 tests.
  **T9 DONE — composite-reflectivity radar plan view (§19). PHASE 2 COMPLETE.** The standard
  top-down TV radar product — CM1's column-max `cref`, VIEW-INDEPENDENT — distinct from the
  3D dBZ layer (a view-ray MIP that changes as you orbit; the §2.3 labeling trap). Ships as
  the 2D `.cref.gz` plan plane (lazy 2D-texture ring parallel to dbz/w) and is painted FLAT on
  the toy landscape at the ground surface point (occlusion-free, drapes over terrain), using
  the SAME NWS palette + dBZ scale as the dBZ layer — exact by identity (`cref ≡ dbz.max(axis=0)`,
  §15.1). The load-bearing decision was the CAMERA, not the render: a flat map at the default
  11° reads edge-on, so entering the layer frames near-overhead (78°, orbit free afterward;
  `?el=` pins a capture angle). The `uLayer=3` value collided with the `w` branches
  (`uLayer > 1.5`) in FOUR shader sites incl. the cut-face sheet's trailing `else` (would have
  painted cref as viridis hydrometeors) — fixed with `< 2.5` bounds + `else if (uLayer < 0.5)`;
  hydro untouched by construction. Feature-detected on `plan_fields.cref`; panel names it
  "Composite reflectivity" vs "Radar (dBZ)"; DIAGNOSTIC + view-independence in HUD/legend.
  Viewer-only, no version move. **Real-GPU verified both grids** (per-package vmax 72/78 read
  correctly; cref core fuller than the MIP per §15.3's max-then-interp). Orientation is earned
  from the WRITE CONVENTION not the capture (advisor): the symmetric centered cell makes an
  x↔y transpose pixel-identical, so what rules it out is `regrid.resample_dbz_2d`'s
  `reshape(ny,nx)` (x-fastest) matching the dbz/rgba bricks' `reshape(nz,ny,nx)` x-fastest
  order; the independent orientation TEST waits on the Phase 3 asymmetric asset (§2.1).
  128/128 tests, build clean.
- **Phase 3 (STARTED 2026-07-20, owner go):** FLAT convective-regime scenarios —
  supercell + seed-driven outcome variation + multicell. Plan + task breakdown:
  `docs/phase3-plan-2026-07-20.md`. **Scope pinned by the owner:** full flat set
  (supercell → seed → multicell), **diorama-only again** (no UE — Y-flip/carried-item-#1
  stays deferred with the UE app), **333 m overnight default** (no 250 m flat-imove hero).
  **Terrain SPLIT OUT to its own later phase** ("Phase 3T", before the old Phase 4) — the
  advisor's flat/terrain fork (`imove` and terrain are mutually exclusive) made into
  scheduling: terrain owns the new Cartesian-regridding module, the diorama heightfield
  render path, the static full-size domain (15–30 h class) and the VHDX resize, none of
  which the flat scenarios need. **Key framing (plan §2):** the base deck template IS the
  Phase 0 supercell validation deck (`iwnd=2`, `imove=1`, `umove/vmove` set), so the
  supercell scenario is a near-empty override set (stop overriding `iwnd`/`imove`) — cheapest
  task, not a shear-design task; multicell is a different CLASS of work (initiation likely
  needs `init3d.F` Fortran → must commit/tag modified CM1 source + fresh binary sha256 or the
  "regenerate from sim/+pipeline/" recovery path breaks); the split supercell discharges the
  T9 **cref orientation test** (NOT the Y-flip, which stays UE-deferred). Real T1 work is the
  asymmetric/splitting export box (measured not matched). Tasks T1 supercell → T2 run/bbox
  gate → T3 cref orientation discharge → T4 seed → T5–T6 multicell → T7 close-out.
  **T1 DONE — supercell config + run + measured box (2026-07-21).** The near-empty override
  set landed as framed (keep template `iwnd=2`/`imove=1`; first POSITIVE exercise of the
  deck generator's imove/Bunkers branch, previously negative-controls-only). **Domain sizing
  was the real work and cost a re-run:** the plan's watch-item 1 — that Phase 0's 120 km
  flat/imove containment holds — was FALSIFIED at 333 m/NSSL. Phase 0's 26 km clearance was
  measured at 1 km/Morrison (ptype=5); the finer grid + true-hail NSSL grows a more
  expansive storm, and on the first 360² run real low-level convection (|w| to 17 m/s, a
  47 dBZ core) reached the open boundary in the last ~12 min. Owner call: re-run larger. The
  **540² @ 333 m = 179.82 km** re-run PASSED the acceptance gate (`probe_edge.py`, the
  criterion is the probe not "it finished"): dbz≥40 core never touches the wall (~40 km
  clearance), the main |w|≥10 body holds ~40–45 km clearance steady through t=108–117 min;
  the one marginal number, +65.8 km |w|≥10 (23.5 km clearance), is a 23-voxel/11.9 m/s
  flanking cell at the TERMINAL frame (t=120=timax), 21 km downshear — real (100% low-level
  per probe_wsurge.py) but a footnote with no un-simulated future to breach; advisor: PASS,
  not marginal. **Measured box = FULL domain horizontally**: the anvil fills the domain
  (union half-width 89.744 km == outermost cell; benign open-BC cirrus, first wall touch
  frame 436), so the honest box is **540×540×54 @ 333 m** (crop_half_width_m=89910 → nx=540
  native 1:1 pass-through; crop_z_top_m=17982 → nz=54, z-top set from the CONDENSATE top
  17.750 km, NOT the |w| top which sits in the zd=15 km Rayleigh sponge); `_provisional`
  dropped. Two side-dividends: **deck.py `OPTIONAL_KEYS` (Category 5) is validated end-to-end
  on a real run** — the scenario's `rstfrq=3600` reached the deck AND fired hourly restarts
  (Phase 3T's 15–30 h confidence; note CM1 restarts are `cm1rst_*.dat` multi-file binary,
  NOT `.nc` — a glob that looks for `*rst*.nc` falsely reports "0 restarts"); and the
  clean asymmetric split (L→(−11.3,+21.9), R→(+7.2,+13.4)) is the asset T3 needs to discharge
  the cref orientation test. test_deck 15/15. **The measured box has not been re-run through
  a full `export` yet** — that ships the package (T2/T3 territory); T1's deliverable is the
  measured, validated box, and it is in `sim/scenarios/supercell_333m.json`.
  **T3 DONE — cref orientation test DISCHARGED (2026-07-28, docs/phase3-t3-orientation.md).**
  The Phase 2 T9 carried note is paid: the plan view is verified un-transposed **end to end**.
  The design decision came first and killed the obvious test — cref's shader `fuv` IS the
  volume's own `(p-boxMin)/(boxMax-boxMin)` expression, so *any* viewer-vs-viewer check
  ("echo sits under the core", "agrees with the dbz MIP") is transpose-consistent by
  construction and **cannot fail**; the reference must be EXTERNAL. Two links, both measured.
  **(A) CM1 netCDF → brick:** truth read from CM1's own `cref` + `xh`/`yh`, cores matched to
  **13–47 m**, and the discriminator is the core-to-core SEPARATION VECTOR — error **0.032–0.043
  km** vs **42.9–59.1 km** under transpose. **A core near the origin cannot discriminate** (it
  sits on the mirror line; it moves only 2.5–3.1 km under transpose), which is why the first
  criterion — "both cores must move" — reported FAIL on correct data. The netCDF axis check is
  on **dimension NAMES, not lengths**: the domain is 540×540, so a shape check would pass a
  transposed file silently — the symmetric-storm blindness one level up. **(B) brick → real-GPU
  pixels:** predicted through the viewer's OWN `mat.ts`/`camera.ts`/`scene.ts` (the 5c scale-bar
  trick), measured as magenta/white ≥65 dBZ blobs in **two** headless-Chrome captures —
  f600@az=45 and f525@az=20 (az=45 makes a transpose exactly a horizontal mirror, so az=20 is
  the general case), with the screen basis pinned by **chirality** (three projected world points — two points
  give one vector and cannot separate a reflection from a 90° rotation). Residual **0.6–2.7 px
  (≤0.63 km on a 179.8 km domain)** where a transpose lands **284–331 px** away. Both sides are
  clustered before matching: two truth cores 5 km apart merge into one rendered blob, and the
  naive match reported an 18.5 px "error" that was a **matching artifact, not a placement error**.
  **The committed half** is `pipeline/tests/test_orientation_t3.py` **11/11** — links A and B are
  one-shots (218 GB run dir, 1.5 GB package, neither in git), so what is gated permanently is the
  *write convention*: a hot cell at CM1 (x_i,y_j) must write flat byte `j*nx+i` through the
  PRODUCTION query builder → resample → encode → `write_frame` → gunzip (the assertion is the
  FLAT BYTE INDEX, since the viewer uploads bytes into a width-`nx` texture — an array that reads
  right in numpy but ravels the other way still renders transposed), plus plan-and-volume
  recovering the same `(i,j)`, which is what licenses the shared `fuv`. **The fixture is 7×5
  off-diagonal and a control PROVES that matters**: on a square fixture with a diagonal feature
  the transposed array is byte-identical and the transpose control stops firing — T9's own trap
  reproduced at test scale, so a future tidy-up cannot silently defang the file. **The manifest
  gate acts on the machine-readable `dims` key, NOT the layout prose** (advisor, post-commit): an
  `"x fastest" in layout` substring test fires only if the phrase goes MISSING, so it passes on a
  contract that drifted from the code — T2 carried item (b)'s exact hazard. And the prose it
  checked is itself ambiguous: cref's `(NX, NY)` is texture (width, height) but reads as the
  transpose of the `reshape(ny, nx)` every consumer does, silent on a 540×540 package. A fifth
  gate pins the shipped orientation fields to `build_manifest`'s output (carried item (b)'s
  reproduction gate in miniature — **narrowed, not closed**); rewording the tuple would stale all
  three tracked web manifests, so it rides to T7 with (b). The Y-flip
  (Phase 1 #1) is **NOT** discharged and stays deferred with the UE app. The node-side prediction
  probe was deleted on purpose: its measured-pixel inputs are constants, so committing it would
  add a test that passes no matter what the viewer later does.
- **Phase 3T (terrain — its own phase, not started):** terrain-following→Cartesian
  regridding (Python, proper — CM1's is quick-and-dirty), diorama heightfield render path,
  static full-size domain, VHDX resize before the first 250 m terrain hero run.
- **Phase 4:** lightning, hail swaths, rain/hail particles, polish.

Full advisor pressure-test of this plan: docs/advisor-review-2026-07-09.md
