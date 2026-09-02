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
  buoyancy redistribution) is required to dial CIN while holding CAPE. **Built
  2026-09-02 as `pipeline/cm1post/sounding.py`** (capped mixed layer, CAPE held by
  solving qv_pbl; gated offline, on-box validation pending — docs/plan-science-hurdles-2026-09-02.md).
- **The environment enters CM1 through `input_sounding` (`isnd=7`) from Phase 3 T5s
  on, not through `isnd=5`/`iwnd=N`:** CM1's analytic options are a few fixed
  profiles with every parameter a hardcoded Fortran local (T5 §1), so CAPE, CIN,
  shear magnitude/depth and hodograph shape are only reachable as a generated text
  file. The file is CM1's second scenario input; it is generated from the same
  `sim/scenarios/<name>.json` as the deck, deck.py refuses any isnd/sounding-block
  mismatch (Category 6), and `run_meta.txt` records its sha256 beside the binary's.
  The three shipped scenarios stay `isnd=5`; the recovery path is unchanged in kind.
- **Multicell initiation is a scenario-design decision:** one bubble = one cell;
  multicell needs multiple bubbles, line forcing, or low-level noise — **and an
  environment in the multicell regime**, which T5 showed the namelist cannot supply
  (its three profiles give 10 / 31.8 / 33.5 m/s of 0–6 km shear; WK82's BRN=50
  boundary falls between U_s 15 and 20 m/s of tanh shear). "One bubble = one cell" is
  also false over 2 h without CIN: the T5 pulse-cell control rang up daughter
  convection (T5 §7.5) — the CIN knob above is what suppresses that.
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
  decision records. **Index: docs/README.md. Per-task status log: docs/STATUS.md.**

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
- **CM1:** cm1r21.1 **+ project fork, as of Phase 3 T4** (`sim/cm1-patches/`).
  Upstream tarball sha256 `dc49fe84…`; stock Phase 0 binary `5da2c2aa…`
  (docs/phase0-cm1-build.md); **forked binary `5fc93016…`**. The fork is a nine-line
  uncomment of CM1's **own** commented-out seed hook, because stock cm1r21.1 has **no
  seed knob at all**: `use_truly_random_pert` is a `logical, parameter` (init3d.F:168),
  so `irandp=1` draws the *identical* perturbation field every run, and the amplitude
  (0.25 K) and bubble geometry are hardcoded. `var7` (an **existing** `&param8` key)
  now advances the PRNG stream, so **"the namelist is CM1's sole scenario input" still
  holds** — only "the binary is the Phase 0 binary" moved, which is what
  `sim/cm1-patches/README.md` and each run's `run_meta.txt` `cm1_binary_sha256` record.
  Verified bitwise-neutral vs stock at seed 0 **with `irandp=1`** (not just `irandp=0`,
  which would not exercise the patched block). Rebuild recipe in the patches README;
  never edit `init3d.f90` — it is a cpp build product.
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

Do not start a phase without explicit go from the owner. **The full per-task record
(every gate, measured number, retraction and lesson) is `docs/STATUS.md`** — moved
out of this file verbatim on 2026-09-02 so the charter stays a charter. Append new
task records THERE; keep this table to one line per phase.

| Phase | State | Record |
|---|---|---|
| **0** benchmark gate | **COMPLETE** 2026-07-14 — 333 m default / 250 m flat hero / 500 m preview, `np=8`, bitwise reproducible; VHDX relocated to M: | docs/phase0-*.md |
| **1** pipeline spike | **CLOSED** 2026-07-20 — 301-frame VDB→SVT end to end on a real RHI; two owner-owed live checks carried (UE SVT visual streaming sign-off, diorama 5c pan gestures) | docs/phase1-completion-2026-07-20.md |
| **2** scenario system · layers · radar | **COMPLETE** (T1–T9) — scenario JSON drives deck AND export; linear-Z dBZ; `w`; `cref`; two packages; diorama picker/layers/plan view | docs/phase2-plan-2026-07-20.md |
| **3** flat convective regimes | **IN PROGRESS** — T1 supercell, T3 cref orientation, T4 seed (CM1 forked) DONE; **T5 CLOSED as measured** (no multicell reachable from the namelist); **T5s 2026-09-02: the external-sounding path WORKS — `base.F` read confirms all three assumptions, both neutrality gates PASS 11/11, three-member shear sweep run and contained.** The environment now reaches the gap with the pinned binary unchanged, and the structural transition lands between U_s 15 and 20 m/s exactly where BRN crosses 50. **No label though:** criterion 1′ sits at its ceiling for every sheared storm and the new criterion 2 failed its own control — H3 confirmed twice over. Next: 500 m re-run of `us15`. T6–T7 pending | docs/phase3-plan-2026-07-20.md · docs/phase3-t5-multicell.md · **docs/plan-science-hurdles-2026-09-02.md** · sim/probes/README.md |
| **3T** terrain | not started — Cartesian regridding module, heightfield render path, static full domain, VHDX resize first | Phase 3 plan §8 |
| **4** lightning · hail swaths · particles · polish | not started — prerequisites listed in the 2026-09-02 plan §7 | — |

**Open owner calls (2026-09-02, after T5s):**
1. ~~T5s go / no-go~~ — **given, and T5s ran.** Source read + 2 neutrality controls +
   3 sweep members, all recorded in `sim/probes/README.md`.
2. **Drop option (i)** (the `0002-` shear patch and its third binary hash). T5s section
   4.1 passed, so its premise — "only a source edit can reach the shear gap" — is
   **measured to be false**. Recommend dropping it. Owner's call.
3. **Re-run `t5s_us15` at 500 m (~2 h)?** T5s's own pre-registered contingency, and the
   only open route to a multicell LABEL. Hypothesis fixed in advance: does rotation
   persistence `P1` break once 5–10 km cells are resolved, while elongation `E` stays
   high? Yes ⇒ `us15` classifies MULTICELL on unchanged thresholds and T6 has its
   asset. No ⇒ the ceiling is structural and H3 needs a criterion this project does
   not have.
4. **Optional, 13 min:** the capped single-cell control (plan section 5.1). Not needed
   for T5s — but the uncapped control currently passes its gate by accident (clause (c)
   gates its daughter ring rather than rejecting it), and a capped one would make it a
   real control. Note the generator refuses a saturating base state, so the cap depth
   must sit below ~0.9 km at 14 g/kg, or hold CAPE at lower moisture.
5. Carried, unchanged: UE SVT visual streaming sign-off; diorama 5c pan gestures; VHDX
   resize number before the first terrain hero run; manifest inline provenance (now
   with `input_sounding` as a second input to record).

Full advisor pressure-test of this plan: docs/advisor-review-2026-07-09.md
