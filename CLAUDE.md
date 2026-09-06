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
| **3** flat convective regimes | **IN PROGRESS** — T1 supercell, T3 cref orientation, T4 seed (CM1 forked) DONE; **T5 CLOSED as measured** (no multicell reachable from the namelist); **T5s 2026-09-02: the external-sounding path WORKS — `base.F` read confirms all three assumptions, both neutrality gates PASS 11/11, three-member shear sweep run and contained.** The environment now reaches the gap with the pinned binary unchanged, and the structural transition lands between U_s 15 and 20 m/s exactly where BRN crosses 50. **No label though:** criterion 1′ sits at its ceiling for every sheared storm and the new criterion 2 failed its own control — H3 confirmed twice over. **500 m re-run of `us15` DONE 2026-09-06 — branch (iii): the ceiling is structural, no multicell label, and `us15`'s one piece of multicell-side evidence (`E`) did not survive refinement.** **Second 500 m run (`us20`) DONE 2026-09-06 — branch (B): the 15→20 elongation gap keeps its sign but loses more than half its 1 km size, so that trend is not resolution-robust; and `R`'s "separation strengthens" is RETRACTED as a one-sided-refinement artifact, leaving the transition-location claim on the split test alone.** **The split test itself
READ AT 500 m 2026-09-06 — branch (I) INDETERMINATE: no new run needed, and `us20` scores
SPLITS on NO basis (six mirrored frames diverging at +3.16 m/s at 1 km become 0 / 1 / 1 at
500 m). The reductions disagree, so the claim is UNVERIFIED at 500 m — not confirmed, not
withdrawn — and the ONLY thing that stopped a withdrawal is the late-window guard written
before any field was opened. The pre-registered primary basis was measured STRUCTURALLY
BLIND for this statistic: block reduction MERGES a 1 km gap it cannot represent (area
conserved 100.8 %, gap sub-40 dBZ cells 2 → 0), so it is faithful for field statistics and
wrong for component counts.** T6–T7 pending | docs/phase3-plan-2026-07-20.md · docs/phase3-t5-multicell.md · **docs/plan-science-hurdles-2026-09-02.md** · sim/probes/README.md |
| **3T** terrain | not started — Cartesian regridding module, heightfield render path, static full domain, VHDX resize first | Phase 3 plan §8 |
| **4** lightning · hail swaths · particles · polish | not started — prerequisites listed in the 2026-09-02 plan §7 | — |

**Open owner calls (2026-09-02, after T5s — four ANSWERED, see below):**

*Answered 2026-09-02:*
- **Option (i), the `0002-` shear patch: DROPPED.** Its premise — "only a source edit
  can reach the 10–31.8 m/s shear gap" — was measured false, and the sweep then ran
  *inside* that gap on the unchanged T4 binary. **No third binary hash, no
  `sim/cm1-patches/` row, and the CM1 pin above does not move. The project's fork count
  stays at one.** Not "kept priced" — retired.
- **500 m re-run of `t5s_us15`: CLOSED 2026-09-06 — RAN, and returned BRANCH (iii).**
  The branches were not renegotiated. Containment read first and measured on the run (67.9 /
  63.4 km clearance vs a 15 km floor). Raw `P1` = **80** at 500 m — the ceiling held, doubling
  the resolution produced no multicell, and **the last open route to a multicell *label* is
  spent**. The pre-registered fragmentation confound never arose (`P1` never broke), and the
  coarsened runs read 80 too, so the ceiling is not a grid artifact either way. Two things
  did move, both recorded as negatives: §4.2's "decisive on **both** statistics" is **corrected**
  — `organised = (R ≥ 0.60) or (E ≥ 2.40)` gates MULTICELL, so `R` = 0.364, being *below* its
  floor, contributed nothing and `us15`'s multicell-side evidence was **`E` alone**; and that
  one statistic **does not survive refinement** (`E` 2.721 → 1.813, inside the INDETERMINATE
  band). The drop is in the **flow, not the ruler**: block-reduced back onto the exact 1 km
  grid and read by the unchanged classifier, `E` = 1.730 / 1.770 and `R` = 0.197 / 0.257 —
  coarsening does not restore the 1 km values, and both reductions agree. `R` and `E` move in
  **opposite** directions under refinement, so the descriptor family is not one signal. The
  transition-location claim stands, but **on the split test ALONE after the escalation below**
  (classifier-free and untouched by both 500 m runs) — §4.2a's second support, "`R`'s
  separation strengthens", is **RETRACTED**.
- **Escalation CLOSED 2026-09-06 — RAN, and BRANCH (B) FIRED: the 15→20 elongation gap is
  SUBSTANTIALLY RESOLUTION.** The second 500 m run (`t5s_us20_500m`, `np=8`, 25 frames) is the
  only thing that could measure, rather than bound, the resolution confound, and its bar was
  committed (`ddff22d`) while it stepped, before any field was read — the bar declared **NEW**
  rather than dressed as pre-existing. Containment read first and measured on the run (60.94 /
  32.47 km against a 15 km floor; the 2:1 is coincidence, not a units bug — `us15`'s pair ran
  0.97 / 0.89). All three instrument gates PASS. Branch (A) needed `E`(`us20_500m`) ≤ **1.343**
  (block-mean) or ≤ **1.383** (block-extremum); it read **1.405** and **1.426**, so the matched-
  resolution gap `G_ref` = **0.325 / 0.344** against the 1 km **0.773** — 42–45 % retained, under
  the 0.387 bar. The raw 500 m gap (0.371) lands in (B) too, so **all three bases agree** and the
  test is not indeterminate. The gap keeps its sign but loses more than half its size: **the 1 km
  `E` trend across this step is not resolution-robust**, and refinement is NOT a common offset
  (`us15` loses ~1.8× as much as `us20` on every basis). **The retraction is the finding with the
  most teeth:** with BOTH members refined, `R`'s separation **narrows** on every basis (0.162 →
  0.089 / 0.038 / 0.026), so §4.2a's "`R` strengthens" was a **one-sided-refinement artifact —
  the same error class this run was built to correct, in the statistic §4.2a used as its
  independent check**. Two supports for the transition claim, one withdrawn; the split test
  survives and **has never been read at 500 m**, which is the next escalation, named and NOT run.
  The `P1` fragmentation confound the instrument exists for failed to fire a **second** time
  (`P1` = 80 everywhere, near-floor frames none). **NOT settled: the 15→20 step only — `us25`
  stays at 1 km, so no claim about the three-member `E` trend is licensed.** Record: plan
  §§4.2a–4.2b, docs/STATUS.md, sim/probes/README.md §§4.2a–4.2b.
- **Capped single-cell control: CLOSED 2026-09-06 — DELIVERED, as a negative.** Both
  members ran (25 frames each) and initiation **PASSED** for both, but the singleness
  criterion was **void as first written**: the configuration is exactly symmetric
  (`irandp=0`, centred bubble, square domain), so CM1 evolves it under four-fold symmetry
  and `n_updrafts` counts copies (4 or 8 **per feature** — not even a common factor).
  §5.4 gated a third member behind "break the symmetry **or** build an instrument that
  does not count copies". **The instrument was built** (`sim/probes/integral_test.py`,
  pre-registered in the plan before it existed): counts break under the symmetry but a
  whole-domain **integral** is exactly 4× a quadrant integral regardless, so a
  direction-only comparison of integrated updraft area works **on the data already on
  disk, with no new compute**. Three gates, all exact zeros — the field is *bitwise*
  four-fold symmetric, whole-domain = 4× quadrant to the bit, and the object set matches
  `ring_test.py` exactly. **Result: both capped members produced MORE secondary
  convection than the uncapped reference** (area ratios 1.42 at CIN −60 and 3.06 at −82;
  intensity-weighted 1.60 and 3.24), monotone in cap strength. **The capped mixed layer
  fails as a single-cell control at this CAPE with zero shear** — a result about the
  *design*, not the code and not the CIN generator, whose mechanism §5.2 had predicted in
  advance (the cap acts on surface-based parcels only; the bubble parcel above it gains
  CAPE 2545 → 3226 J/kg, so a stronger storm makes a stronger cold pool). A **third
  capped member is therefore not worth running at any Δθ**, and the clean single-cell
  control `classify_t5.py` wants must come from a different design. A ring-vs-cells
  classifier was deliberately **not** built: an axisymmetric run cannot produce distinct
  cells, so no frame on disk could ever fail it. §5.4's "the cap bit early then was
  overrun" is **withdrawn** — at t = 75 min the capped run has 4× the updraft area and ¼
  the component count. Bitwise reproducibility re-confirmed on the way (24/25 frames per
  member; the one exclusion was predicted in advance). Record: plan §§5.2–5.6,
  docs/STATUS.md.

- **The split test at 500 m: CLOSED 2026-09-06 — RAN (analysis only, no new simulation),
  branch (I) INDETERMINATE.** The transition-location claim's last leg is **unverified at
  500 m**. Two escalations are NAMED and NOT RUN, each needing its own go: (1) a
  connectivity reach in **kilometres** applied identically at both resolutions, with its own
  bar and neutrality gate — §4.2c's objection to re-tuning was right while the confound was
  hypothetical, and a fixed physical radius hides nothing now that it is measured; (2)
  **longer runs**, since the split signature lands at t ≥ 90–105 min in a 120-minute window
  and the late-window rule will absorb most evidence at any resolution until then. Record:
  plan §4.2c, docs/STATUS.md, sim/probes/README.md §4.2c.

- **Squall line (C2): KEEP — and the export contract is DONE 2026-09-06.** T5 §11.7's
  crop-box hazard is discharged, offline, with no CM1 run. `Scenario` gains an
  **optional** `crop_half_depth_m` (absent ⇒ square, so nothing shipped moves) and
  `ny`/`origin_m`/`manifest.extent_m.y` follow it; `check_periodic_extents` requires a
  periodic axis's extent to be the **full domain** — a gate, not a waiver, refused in
  both directions and keyed off the **namelist** (`sbc`/`nbc`), never a flag in the
  `export` block, so the claim cannot be asserted by editing the thing it licenses.
  **`FORMAT_VERSION` does not move** and the byte-identity rebuild proves it
  (`test_manifest` 17/17): the manifest always wrote `dimensions` and `extent_m.x`/`.y`
  as separate keys, so only the values become unequal. The diorama needed **no change** —
  it already reads nx and ny independently. **The finding: §4.4's scope list was one item
  short, and the missing item was sharper.** The bbox sweep collapsed both horizontal axes
  into one scalar, so on a periodic-y line it reported the full-domain y extent as "the"
  half-width and demanded a square box that large — **the mostly-empty package was
  reachable through the measurement even after the schema stopped forcing it.** Now
  per-axis (`scenario.box_verdict`). **A fourth problem, found on review:** forcing a
  periodic axis to the full domain pushes the outermost export voxel centre PAST the
  outermost CM1 cell centre unless the export voxel equals the sim spacing, and `regrid`
  fills outside-the-grid samples with **zero without raising** — a dead rim along exactly
  the boundary a wrapping line crosses. Refused by name (`check_periodic_resampling`);
  the repair is an **OWNER CALL, not taken**: export the periodic axis at the simulation
  spacing, or give `regrid` real periodic wrapping (clamping is excluded — it smears the
  wrap). Until it is taken, a line ships at its sim spacing or not at all. Gate
  `pipeline/tests/test_squall_box.py` **27/27**, every fixture nx ≠ ny ≠ nz, three of them
  the transpose test no square grid in this repo could have failed (`densevol` shape plus
  a marker through `regrid.resample` and the 2D plan path). **NOT delivered:** a
  squall-line scenario. Shipping C2 as a package
  still needs a run, a measured x half-width, and a `sim/scenarios/` config — each its own
  go; `t5probe_c2` stays a probe and is still refused for `_provisional` first. Record:
  plan §§4.4–4.4a, docs/STATUS.md.

*Still open:*
1. UE SVT visual streaming sign-off.
2. Diorama 5c pan gestures.
3. VHDX resize number before the first terrain hero run.
4. Manifest inline provenance — now with `input_sounding` as a second input to record.

Full advisor pressure-test of this plan: docs/advisor-review-2026-07-09.md
