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
- **Data/git policy:** raw netCDF is regenerable and never committed. Scenario
  packages are multi-GB and live outside plain git history (LFS or out-of-repo —
  decide before the first package ships). Nothing >10 MB in plain git.

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
  below M:'s safe headroom (owner's call on the exact number).
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
  −23125) — lossless, but the UE app must take placement from the **asset's transform**
  and apply only the units conversion; adding the manifest's `origin_m` on top lands the
  volume 2750 m off (guardrail: `volume.ue_placement_rule` in the manifest).
  **Still open:** where multi-GB packages live (LFS vs out-of-repo — charter says decide
  before the first ships; this one is 0.46 GB and regenerable in 7.5 min), and the Python
  env lockfile.
- **Phase 2:** scenario system + selectable UI layers + radar view.
- **Phase 3:** multicell/supercell scenarios + seed-driven outcome variation + terrain.
- **Phase 4:** lightning, hail swaths, rain/hail particles, polish.

Full advisor pressure-test of this plan: docs/advisor-review-2026-07-09.md
