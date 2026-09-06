# Status log — the per-task record

**Moved verbatim out of `CLAUDE.md` on 2026-09-02.** The charter's *Status / phasing*
section had grown to 686 lines / 60 KB — 78 % of the file — so the charter (principles,
architecture, constraints, pins, conventions) was buried under its own history. Nothing
was edited in the move: the section below is the charter's status text as of commit
`a1594d2`, and **new task records are appended here**, under *Additions after the move*.
`CLAUDE.md` keeps a one-line-per-phase table plus the list of open owner calls, and
points here.

Conventions for entries (unchanged): each task entry records what was DONE, the gate
that proves it (with counts), the numbers that were MEASURED rather than assumed, and
any owner call it needs. Retractions stay in the text — a corrected claim is written as
a correction, never silently edited.

---

## Status / phasing (verbatim, as of 2026-09-02)

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
  **T4 DONE — seed-driven variation; CM1 IS NOW FORKED (2026-07-28,
  docs/phase3-t4-seed.md).** The plan's §4.3 premise was **falsified by reading the source
  before writing code**: stock cm1r21.1 has **no seed knob at all**. `use_truly_random_pert`
  is a `logical, parameter = .false.` (`init3d.F:168`) — a *compile-time constant* — so
  `irandp=1` draws the **identical** perturbation field every run; no `namelist /paramN/`
  holds a seed or amplitude key; amplitude (0.25 K) and bubble geometry are hardcoded, and
  `centerx`/`centery` are module variables from domain geometry, not namelist keys. Stock CM1
  offers only *reproducible-with-zero-variation* or *wall-clock-seeded-and-irreproducible*,
  and **nothing in a namelist moves between them** — so §2.3's modified-binary consequence
  arrived at T4 instead of T5. That is an argument for doing it FIRST: the fork-provenance
  mechanics get built exactly once, better on a **nine-line uncomment of CM1's own
  commented-out hook** than alongside novel multi-bubble physics; T5 inherits them.
  **The fork costs less than §2.3 feared, and the two halves are separable:** `var7` is an
  **existing** `&param8` key, so *"the namelist is CM1's sole scenario input"* **survives**
  — only *"the binary is the Phase 0 binary"* moved (`sim/cm1-patches/`, upstream tarball
  `dc49fe84…`, stock `5da2c2aa…` **verified against docs/phase0-cm1-build.md BEFORE
  patching**, fork `5fc93016…`). It is a **stream OFFSET, not a re-seed** — different seeds
  get a shifted reuse of one stream, decorrelated per grid point but not independently drawn;
  sufficient for "same environment, divergent trajectory", upgradeable to `random_seed(put=)`
  on the already-forked binary. **Banked: the perturbation field is
  decomposition-independent** (the loop walks the global domain on every rank, each applying
  only its own points), which is what licensed verifying at 500 m/np=4 instead of 333 m/np=8;
  it does NOT make a run rank-independent, so "same seed ⇒ bitwise" holds at fixed rank count.
  **Four run gates on real CM1, both binaries, decks through the production generator:**
  neutrality IDENTICAL at `irandp=0` **and at `irandp=1`/seed 0** (the latter is the real
  claim — `irandp=0` never enters the patched block), positive DIFFERENT, same-seed repro
  IDENTICAL. **Gate 2 is load-bearing beyond the science:** `init3d.f90` is the cpp artifact
  of `init3d.F`, so an unregenerated `.f90` leaves the binary silently unchanged — which
  **passes neutrality trivially**; only the positive gate catches it (Makefile's `.F.o` rule
  covers it structurally too — never edit the `.f90`). `seed` is a **REQUIRED semantic key**
  emitted as `var7` (a raw `"var7": 3.0` would tell a future reader nothing and carries no
  name into provenance); making it REQUIRED looked like churn for three scenarios and was
  none — `seed=0` substitutes `0.0` over a template line already reading `0.0`, so all three
  decks are **byte-identical** (refs via `git archive`) and T1c/T6 don't move; only T6's
  override count changed 28→29. **Three silent-aliasing guards, each of which would otherwise
  run for hours and return the wrong ensemble member:** negative seed (`do n=1,nint(-5.0)` is
  **zero-trip** → silently aliases to seed 0), non-integer (`nint` rounds 1.4 and 0.6 to 1),
  and `seed>0` with `irandp=0` (advance is inside `IF(irandp.eq.1)` — the trap of building an
  ensemble by copying an unseeded scenario); `seed=0`/`irandp=0` stays legal as the honest
  "unseeded" declaration. `test_seed_t4.py` **15/15**, and **all four mutations of
  `_seed_to_var7` were CAUGHT** — the guards are known to fire, not merely to pass.
  **Spread MEASURED on a sheared/splitting storm** (1 km proxy, seed 0 vs 1, docs §5.2), and
  the two answers point opposite ways: **intensity is seed-ROBUST** (peak w within 3.6 %, both
  unmistakably supercells — the shear sets the class and 0.25 K of noise cannot move it) while
  **structure and placement diverge steadily** (t=120: cref pattern corr **0.397**, IoU@40 dBZ
  **0.417**, ≥40 dBZ centroid **18.7 km** apart, storm area **−29 %**; initial-intensification
  *timing* swings +60 %). Same environment, same storm class, genuinely different individual
  storm — the honest forecast→outcome lesson. Metrics are deliberately identification-free
  (pattern correlation / IoU / centroid), because the per-mover tracker jumps between cells and
  its separation column is not trustworthy. **Owner call 2026-07-28: SHIP NOTHING** — T4 stands
  as mechanism + measured spread; a seeded package stays cheap to produce later (§7).
  **T5 — SCORED; no candidate is a multicell. Option (ii) SPENT and it delivered;
  the blocker is now isolated to criterion 1 and the pre-committed next step is
  §9.8's (iii) — NOT STARTED, needs an owner go (2026-08-10,
  docs/phase3-t5-multicell.md §§7–11).** The earlier
  "candidates deliberately unscored" instruction is **DISCHARGED**: the abort fired (§7),
  the owner chose §7.6 option (A), criterion 2 was re-pre-registered as an **organisation**
  test and committed before scoring (§8, commit 797b78b), the re-armed abort **passed**
  (PC → SINGLE CELL, decisively: median `R` 0.006, `E` 1.000 in every frame), and only then
  were A/B/C read (§9, commit 002b395). **All three classify SUPERCELL**, so §6's row 3
  fires. Plan §2.3's premise was falsified in the **cheap** direction (again by
  reading the source first): CM1 reaches multicell candidates through **namelist
  integers** (`iwnd`/`iinit`), no `init3d.F` edit and so no second fork patch — though
  only the *option selection* is namelist; every parameter *inside* an option is a
  hardcoded Fortran local, making the reachable space a few fixed profiles (0–6 km bulk
  shear **10 / 31.8 / 33.5 m/s**), not a sweep. §2.2's **shear gap** — the
  multicell↔supercell transition sits *between* 10 and 31.8 and nothing in the namelist
  reaches it — is pre-committed as the `0002-`-patch branch, priced (third binary hash,
  moving the CM1 pin d427ff2 just consolidated) and NOT undertaken without a go. Five
  1 km probes (A/B/C + SC/PC controls) ran and are on disk (`~/thunderstorm/runs/t5probe_*`,
  `irandp=0` verified in all five, fork binary `5fc93016…`); the classifier and its 20
  wiring gates were **committed before scoring anything** (`sim/probes/classify_t5.py`,
  `pipeline/tests/test_classifier_t5.py`, commit 3692e9a). Then **the PC control — the
  known single cell — classified MULTICELL**, and §4 pre-committed that as an abort.
  **Why: component counting cannot separate "N cells" from "one ring in N lobes."** PC's
  four ≥40 dBZ components carry *identical* areas and *identical* peaks to the digit at
  (±5,±5) — the axisymmetric gust-front ring of a zero-shear pulse cell, quantised by a
  square grid (4 lobes → 12). `ndimage.label` was chosen in §3.1 precisely to dodge T4's
  failed argmax tracker and walked into a different failure mode. Both obvious repairs are
  **refuted with numbers, not argued away**: morphological closing collapses the late
  frames (12→1 at 2–3 km) but leaves **4 components at t=75/80 at every radius 1–5 km**,
  and arm A needs only 3 in one frame; threshold-lowering fails likewise. The trap is
  named too — PC's lobes top out at 26 km², so raising the 4 km² minimum to ~30 rescues
  the control instantly, i.e. *picking the number just above what the control did*, while
  suppressing the genuine small cells at 1 km in candidate B that the probe exists to
  test. Two findings stand on their own: **a self-referential control cannot fail** —
  criterion 1's threshold is `0.25 × median(SC's own max|uh|)` *and SC is scored against
  it*, so SC classifies SUPERCELL by arithmetic on any data (`frac_rot` came back exactly
  1.000); SC sets the scale and **PC was the whole test**. And **"one bubble ⇒ one cell"
  is false over 2 h** at 1 km with no CIN (the charter's open CIN design task, one level
  up): the pulse cell peaks 61.6 m/s, decays by t=70, then rings up daughter convection at
  15–32 m/s / 49–56 dBZ — the control's *expectation* was untested, not just the code.
  Three vindicated pre-registrations localise the failure: M1 separates the controls
  **30.8×**, §6.2's boundary descriptor read **0 in all 50 control frames** as predicted at
  `irandp=0`, and §5's containment/drift check voided neither run (SC's measured drift
  implies `vmove` 5.1 vs the 3.0 given — a 2 m/s Bunkers error over 2 h, inside 45 km of
  clearance).
  **The §8 replacement, and what it found.** Criterion 2′ = **organised** multiplicity:
  `R`, the area-weighted circular resultant of updraft components about the *echo* centroid
  (an independent anchor — the components' own mean would force `R ≡ 0`), plus `E`, the
  elongation of the updraft **mask's voxels**. `E` is deliberately NOT the covariance of
  component centroids: under an isotropic null a 3-point ellipse has median `E` **3.72**
  with **79.7 %** of triples clearing 2.0, and PC could never have caught that bias since
  its ring gives `E ≈ 1` either way. `E` exists at all because of candidate C — a squall
  line's cells sit symmetrically about the centroid, so `R ≈ 0`, the same answer as the
  ring; without a second moment the canonical multicell is a false negative *by
  construction*. Floors are geometric and fixed a priori (`R` ≥ 0.5, `E` ≥ 2.0) with a
  **two-sided** §8.6 band — thresholding at PC's own p95 was rejected because a median can
  never exceed its own p95, which would have made **both** controls tautologies and left
  the abort with nothing live. **Results:** A (`iwnd=4`, CM1's own "multicell" label)
  **out-rotates the control** (median `max|uh|` 1132 vs 679) — §2.1's pre-registered
  prediction CONFIRMED, the README label is a name on a wind profile, not a claim about the
  storm; B (`iwnd=1`, 10 m/s) is a single **rotating** cell (1 cell in 16 of 17 mature
  frames, `R` 0.192), not the cold-pool cluster the weak-shear regime was supposed to give;
  C (`iinit=8`) is **VOID structurally** — its echo spans **all 180 y rows wall-to-wall in
  every frame**, because §2 picked `iinit=8` precisely for being domain-agnostic, so it
  *cannot* satisfy a containment criterion written for a compact storm (§6.2's 17
  boundary frames are that same geometry, not `irandp` noise). C is nonetheless the
  strongest signal on the page (`E` **20.8**, 15 simultaneous updrafts) — a squall line
  denied MULTICELL by criterion **1**, not by 2′ and not by its void.
  ⚠ **The open question is criterion 1's 0.25 factor, and it is NOT to be moved
  post-hoc.** It decides B and C: at k=0.5 C stops being a supercell (0.18) and B is on the
  knife edge (0.53); at k=0.75 both would be MULTICELL on their `E`. An earlier draft
  claimed the SC control caps k at 0.75 — **wrong twice**: 0.47 was a rounding artifact (the
  script hardcoded the printed median 678.7 vs the exact 678.6939, dropping the median frame
  from its own comparison; the true value is 0.529), and for odd *n* the fraction at or
  above the median is (n+1)/2n > 0.5 *by definition*, so SC cannot fail at any k ≤ 1.0 —
  §7.2's self-reference recurring one section later. The controls therefore place **no**
  ceiling; the unresolved range is k ∈ [0.4, 1.0], PC flat at 0.00 throughout. **§11.4
  supersedes the framing** — the question is not *which k* but that k parameterises a median
  test; the defect is in kind, not in the number.
  **§9.8 priced three options; the owner chose (ii) and §10 pre-registered it before the
  run.** **§11 — C2 IS SCORED, and §10.4's prediction is CONFIRMED: SUPERCELL**, so the
  pre-committed branch fires — **the answer is (iii), the criterion-1 discriminator, NOT
  (i)**. Buying a second fork to widen the shear range would be paying for the wrong thing.
  **The containment fix worked exactly as the source read predicted** (§10.1: `iinit=8`'s
  `beta` has *no y term*, so the line is infinite in y by construction and the fix is the
  BOUNDARY, not the line): 17 boundary-cell frames → **0**, clearance **0.00 → 69.93 km**,
  namelist-only, no patch, no third hash, the CM1 pin did not move; C2's deck differs from
  C's in exactly **2 of 413 lines**, both boundary keys. **What (ii) bought is a clean
  isolation: C2 is the FIRST NON-VOID run with crit2′ ∧ crit3 ∧ ¬crit1** (median `E` 19.04 =
  7.9× the banded floor; C had the signature but was voided; SC/PC/B fail crit2′; A fails
  crit1 at every k). **THE FINDING (§11.4), earned from data already collected: criterion 1
  is a MEDIAN COMPARISON.** Every run's k-flip point equals its own `median(mature max|uh|) ÷
  SC's median` to 1e-12, all six — because with `UH_FRAC_FRAMES=0.5` and an odd frame count,
  "rotating for less than half its mature life" **is** the median. So criterion 1 is a scalar
  magnitude ratio supplying **no temporal robustness at all**: 8 frames at 2000 is not a
  supercell and 9 is; one frame at 10⁶ is not, while 17 flat frames at 200 is. That is the
  **same root cause as §7.2 and §9.6, stated once instead of twice**. Tested not argued —
  12 000 comparisons over six real runs × a dense k grid, 0 disagreements, plus five
  adversarial synthetic series; the run-data-free half is now a **permanent gate**
  (`test_classifier_t5.py` **57/57**) carrying its own vacuity control (at
  `UH_FRAC_FRAMES=0.25` the two rules *do* come apart) and holding at every k, so the
  property belongs to the fraction, not to 0.25. **k is NOT moved:** C2's margin is reported
  as a ratio (**1.16×** the threshold) not as "0.04 in k" — the same fact dressed as a reason
  to move it — and the real argument is **stability, not margin**: a boundary-condition-only
  edit moved this candidate's flip point **0.11 in k, 2.7× the distance from 0.25 to the flip
  point**. §7.4's tuning trap with a candidate as victim instead of a control. **§11.6 fixes
  (iii)'s constraints and deliberately does NOT state its conclusion** — nothing about
  rotation *position or persistence* has been measured: a different discriminator not a
  different k; **scale-free with no control normalisation** (any candidate÷control statistic
  reinstates §7.2's self-reference, which has bitten twice); thresholds fixed a priori from
  geometry/duration, validated on SC+PC only, committed, *then* re-scored. Criterion 2′ is
  validated in the field: it fired on neither control, annihilated the ring, and separated
  ring from line by **20×**. Re-scoring the six existing runs costs minutes — **this is a
  design decision, not a compute one.** **§11.7 carried consequence, flagged not acted on:** a
  periodic-y domain has **no finite condensate extent in y**, so if C2 ever becomes the T6
  asset the crop-box measurement / `require_measured_box` inherits §9.5's error one level up,
  in the *export* path. **The six probe configs are now TRACKED** (`sim/probes/configs/`,
  ~15 KB) — the namelist is CM1's sole scenario input, so config + `pipeline/` + the pinned
  fork binary is the whole recovery path for every number in §§7/9/11; all six verified to
  regenerate **byte-identical** to the deck their run actually used.
  **T5 — OPTION (iii) IS SPENT. T5 has no multicell under TWO independent criterion-1
  designs, and the classifier's reach is now measured (2026-08-10, §§12–13).** Owner go
  for §9.8's (iii); §12 pre-registered a replacement and was **committed before any
  candidate was re-scored** (63c9f3d), §8's sequence for the third time. Criterion 1′ =
  **P1, the longest same-sign displacement-limited chain of rotation centres** — a
  **LINKER, NOT A TRACKER** (T4's argmax tracker hops to whatever is brightest and cannot
  fail to produce a track; this refuses to hop, and a broken chain IS the measurement).
  **The load-bearing design decision was the magnitude floor, and it is the one place the
  whole thing could have collapsed:** §11.4's medians were already known, so *any* floor in
  150–400 reproduces the retired median comparison with a new constant and a citation
  stapled on — including the respectable ζ≥10⁻² × w≥10 × 3 km construction, which lands at
  **~300** and would have killed C and C2 on magnitude alone. `UH_FLOOR=10` is set **19.7×
  below the lowest candidate median** so it *cannot* discriminate, and the control run
  proved the property rather than asserting it: **PC clears the floor and is rejected by
  PERSISTENCE** (5 min vs a 25-min band edge), where at floor 25+ it forms no components at
  all. **BOTH HALVES OF THE ABORT WERE LIVE FOR THE FIRST TIME SINCE §3** — removing control
  normalisation (gated *structurally*: `classify_v3` takes no `sc_uh_median`) removed §7.2's
  arithmetic forcing, and SC returned SUPERCELL on a measurement (80 min, 17/17 frames,
  largest component 0.42 % of domain — nothing chained by covering the map). **RESULT: all
  four candidates SUPERCELL again, P1 = 80 min each — identical to SC.** §12.8's
  non-discrimination bullet fires: P1 separates single-cell from storm **16×** and separates
  multicell from supercell **not at all**. **THE HEADLINE — the defect was real in KIND and
  null in OUTCOME:** magnitude and persistence are independent constructions and agree on all
  six runs, so "all supercells" now rests on two independent rotation criteria instead of one
  known-broken one. **THE FINDING THAT CLOSES THE FLOOR QUESTION FOREVER: the floor sweep IS
  the median test, measured** — ranking runs by the highest floor at which P1 still banks a
  supercell (PC 0, C2 25, C 50, B 100, SC 200, A 200) is **IDENTICAL, run for run, to
  ranking them by median max|uh|**, so raising the floor stops measuring persistence and
  starts measuring magnitude. The §12.3 escape hatch is retired as measured-impossible, not
  merely unused. **`P2` (net/path 0.28–0.80) and chain continuity APPEAR to separate and are
  DELIBERATELY NOT PROMOTED** — §7.4's trap with a candidate as beneficiary, in the round
  whose justification was implementing a pre-commitment — and the honest reason is also the
  data: the two descriptors **rank the candidates differently** (B is mid-pack by net/path
  and the most discontinuous run on the page by area/peak jump). §12.6's promise discharged:
  C2's `E` **19.04 → 18.06** wrap-aware (`R` 0.129 → 0.108), sign unchanged, C bit-identical
  as gated — but qualified, since C2's mask fills a **median 0.778** of the periodic y axis,
  so an elongation measured along an axis the feature nearly wraps is not comparable with
  C's open-axis 20.76. Also measured, and it falsifies a §3.1 rationale: **CM1's `uh` is
  NON-NEGATIVE** (`min == 0.0` in all 50 control frames), so `max|·|` was always identity —
  no number moves, but a **left-moving supercell carries no signal in this field at all**.
  `test_classifier_t5.py` **57 → 111**, incl. §12.9's anti-collapse gate (series where chain
  duration and every magnitude-only statistic disagree, both directions) with a vacuity
  control. **Three fixtures had to be repaired before they could fail** — a couplet with a
  one-cell gap, a seam line whose blobs merged early, and *symmetric* no-op fixtures that
  passed a change which silently moved published `R` on five runs (reverted; the grid-snap
  imprecision is left as a known defect rather than fixed post-scoring). **§11.8's case
  against option (i) NO LONGER HOLDS** — it rested on "C2 is denied only by a rotation test
  whose defect is now measured", and the defect is now *fixed* while C2 is *still* denied.
  Price restated, not taken: third binary hash, patches-README row, charter CM1 pin moves.
  **Owner call needed; nothing here takes it.** NOT recommended: moving the floor, promoting
  `P2`, or a fifth criterion-1 round.
- **Phase 3T (terrain — its own phase, not started):** terrain-following→Cartesian
  regridding (Python, proper — CM1's is quick-and-dirty), diorama heightfield render path,
  static full-size domain, VHDX resize before the first 250 m terrain hero run.
- **Phase 4:** lightning, hail swaths, rain/hail particles, polish.

Full advisor pressure-test of the original plan: docs/advisor-review-2026-07-09.md

---

## Additions after the move

- **Phase 3 T5s — PROPOSED 2026-09-02, NOT STARTED, needs an owner go
  (docs/plan-science-hurdles-2026-09-02.md).** T5's blocker is dissolved by a stock
  CM1 feature the record never considered: **`isnd=7` reads the base state — θ, qv,
  u AND v — from an external `input_sounding` text file.** Every parameter T5 called
  "a hardcoded Fortran local" (shear magnitude, shear depth, hodograph shape, and the
  charter's missing CIN knob) becomes a value in a generated text file, with **no
  change to the binary** — so option (i), the `0002-` shear patch and its third
  binary hash, is unnecessary. Landed in this commit, gated where it can be gated
  without the box: `pipeline/cm1post/sounding.py` (WK82 eqs. 1–2 thermodynamics;
  capped-mixed-layer CIN knob with CAPE held by solving qv_pbl; tanh/linear wind
  profiles; parcel CAPE/CIN with the Doswell–Rasmussen virtual correction; BRN and
  the WK82 regime **prediction**), `pipeline/gen_sounding.py`, deck **Category 6**
  coupling (isnd=7 ⇔ `sim.sounding`, iwnd forced 0), the runner staging
  `input_sounding` and recording its sha256, and `pipeline/tests/test_sounding_t5s.py`
  **29/29** (the three shipped scenarios untouched; profile checked at WK82's fixed
  points and against T5 §2.1's hand-derived shear numbers). **Measured with the
  generator, before any run:** WK82 at 14 g/kg gives SB CAPE 1859 J/kg, CIN −48 J/kg;
  BRN falls 132 → 59 → 33 → 21 → 15 → 11 for U_s = 10…35 m/s, so **the WK82
  multicell/supercell boundary (BRN 50) sits between U_s 15 and 20 m/s — inside the
  10–31.8 m/s gap.** Five probe configs are pre-registered in
  `sim/probes/configs/t5s_*.json`: two neutrality controls (the PC and A probes
  re-run through the file path — the on-box gate that decides whether `isnd=7` is
  what this project believes) and a three-member sweep U_s = 15 / 20 / 25 with the
  BRN prediction recorded in each config. **What is NOT verified:** the `isnd=7`
  format, that `iwnd` is ignored at `isnd=7`, and the file-level cap are from memory
  of CM1's README.namelist — the CM1 source is not in this repo and its website is
  egress-blocked from the session — so the plan's step 1 is a `base.F` read on the
  WSL box, and the neutrality gates are the empirical check either way.
  **Structural changes in the same commit:** this file created (status log moved out
  of the charter), `docs/README.md` index added, `README.md` brought current (it
  still said "pre-implementation"), deck/template/probe READMEs updated.

---

## Phase 3 T5s — external sounding (`isnd=7`) — 2026-09-02

Owner go given. Full record and every number: `sim/probes/README.md` (sections 4.0,
4.1, 4.2) and `docs/plan-science-hurdles-2026-09-02.md`. Commits `5d4ff57`, `1b53270`,
`68e8aee`, `3cfce47`, `dddf3f3`.

**§4.0 source read (step 1, no run).** All three of the plan's unverified assumptions
confirmed in `base.F`: the file format; that `iwnd` is ignored at `isnd=7` (settled
three ways — `param.F` even forces it to 0 with a *non-fatal* warning, so this
project's refusal is stricter than CM1's); and that the level cap is 1 000 000, the
binding constraint being instead that the file's last `z` exceed the top **scalar**
level (19 750 m). **The read paid for itself three times:** the template ran
`output_basestate=0` so the gates would have been unevaluable *after* their runs;
`run_probe.sh` never generated `input_sounding` at all despite the README claiming it
did; and the writer's 100 m spacing put the moisture residual at 92 % of the gate
budget because CM1 interpolates **RH** across the mixed-layer kink — 50 m fixes it,
25 m adds nothing. Also recorded: `iwnd=3` measured at 52.4 m/s (above the gap, so T5's
"ruled out" now rests on arithmetic); `isnd=17` exists and is refused by name.

**§4.1 neutrality — PASSED 11/11.** Plumbing at floating-point noise (theta 2.2e-05 K,
qv 8.5e-07 g/kg); this project's WK82 vs CM1's at 0.0048 g/kg, the value predicted
offline before the runs; CM1's own t=0 CAPE within 0.03 %; wind not zeroed by `iwnd=0`;
pulse cell reproduced to 0.07 % and supercell to 2.45 %, both at identical peak times.
**The environment now reaches CM1 through a generated text file with the binary
unchanged — option (i) is measured to be unnecessary.** The isnd=5 references needed no
re-run: their base state is recoverable exactly at t=0 (`th-thpert`, `qv`, `prs`,
`uinterp`), verified to 0.000e+00 against CM1's own arrays on the new runs first.

**§4.2 criterion 2 (births) — RETIRED for cause, before it scored anything.** The
plan's trigger could not fire (1 of 6 runs, not the supercell control). Re-registered;
then two threshold-free defects in the re-registration itself (right censoring, and a
greedy tracker this project retired in T4) were fixed. The corrected control result
still fails: SC 2 births against a bar of ≤1, and PC's 0 is a *non-exercise* — its
censored tail holds **four entries identical to the decimal**, T5 §7.3's axisymmetric
gust-front ring arriving through a completely independent construction, which fifteen
minutes earlier would have labelled the single-cell control MULTICELL. **H3 confirmed
by an independent construction**; the entity definition was NOT iterated a third time.

**§4.2 sweep — RUN, CONTAINED, SCORED.** All three label SUPERCELL on `P1 = 80`, the
ceiling; the unsheared control reads 5, so `P1` separates *sheared from unsheared*.
Descriptors are monotone in shear (`R` 0.364→0.526→0.560, `E` 2.721→1.948→1.546), and
criterion 2′ read alone on unchanged thresholds puts **`us15` decisively on the
multicell side on both statistics** while `us20`, `us25` and the supercell control are
INDETERMINATE. **[CORRECTED 2026-09-06 (500 m re-run, below): only `E` carried multicell-side weight through the rule — `organised` is an OR of `R ≥ 0.60` and `E ≥ 2.40`, and `R` = 0.364 sits *below* its floor, contributing nothing. Both statistics are outside their bands; one of them is evidence.]** **The structural transition lands between U_s 15 and 20 — exactly where
BRN crosses 50, predicted from the sounding before any run.** Not claimed: that `us15`
is a multicell. Complication recorded: `us15` has the *fewest* updrafts and *zero*
births, so its signature is line-like (elongated, incoherent) rather than discrete-cell
multiplicity — different objects, and now the open question.

**Lessons.** (i) A statistic that never moves makes a criterion vacuous rather than
wrong, and only a control can show it — the domain-wide peak updraft never halves.
(ii) Right censoring turns "persisted exactly the minimum" into an artifact of the run
length. (iii) A criterion whose *negative* side is INDETERMINATE for the known positive
control separates one member without establishing anything about the others.

### T5s owner decisions — answered 2026-09-02

- **Option (i), the `0002-` shear patch — DROPPED.** Retired outright rather than kept
  priced: no third binary hash, no `sim/cm1-patches/README.md` row, no charter pin
  move. **The fork count stays at one.** T5 §13's carried "owner call" is thereby
  closed, and `docs/phase3-t5-multicell.md` carries a pointer to this resolution rather
  than being rewritten.
- **500 m re-run of `t5s_us15` — CLOSED 2026-09-06: RAN, and returned BRANCH (iii).**
  Its three outcome branches were fixed in the plan *before* the 1 km sweep was read and
  were not renegotiated at run time. Raw `P1` = 80 at 500 m — the ceiling is structural,
  doubling the resolution produced no multicell, and the last open route to a multicell
  *label* is spent. Full record in this file below.
- **Capped single-cell control — APPROVED, deferred (not today).** 13 min. Feasibility
  measured offline first, and it **corrected the plan's own §5.1 numbers**: a 1 km mixed
  layer is refused at 14 g/kg (RH 1.002), and the intuitive workaround is backwards —
  holding CAPE against a cooling cap makes the solver *raise* `qv_pbl`, saturating
  harder (RH 1.091), so a 1 km layer would need a lower CAPE target rather than lower
  moisture. Runnable envelope: `z_cap_m` 600–900 m, Δθ 2–6 K, CAPE holding itself to
  within 2 J/kg of the 1860 J/kg reference with no solver. CIN **strengthens with Δθ and
  weakens with depth** (600 m/6 K → −82 J/kg; 900 m/2 K → −39; uncapped −48), so the
  strongest suppression at fixed CAPE is the *shallowest* cap with the *largest* Δθ —
  the opposite of the "deeper mixed layer" intuition.
- **Squall line (C2) — KEPT.** It does not retire with T5s, so T5 §11.7's crop-box
  hazard is live. Scoping it found the note **understated** the problem: the export
  contract carries a single `crop_half_width_m` and derives `ny = nx`
  (`pipeline/cm1post/scenario.py`), so the box is **square by construction** and cannot
  describe a line — the only legal box for one today is the full square domain, the
  largest possible package and mostly empty. Keeping C2 therefore needs (a) a separate
  along-line extent in the scenario contract, with `nx`/`ny`/`origin_m` and
  `manifest.bbox_center_m` following; (b) `require_measured_box` to accept "a periodic
  axis's extent is the full domain by construction" as a *valid measured route* rather
  than an unmeasured placeholder. The SVT static-centre rule is easier on a periodic
  axis, not harder. Owed before C2 ships as a package, not before T6. Not started.

## Diorama performance pass — 2026-09-05

Scope: "improve project visuals/performance, especially the diorama". Record +
remaining plan: `docs/plan-diorama-perf-2026-09-05.md`. Commits 6191717, ff0f64f
and the follow-up (dither / `?rs=auto` / step floor / docs).

**Instrument first.** Per-pass GPU timers (`EXT_disjoint_timer_query_webgl2`,
`diorama/src/gputimer.ts`, `?stats`) replaced rAF spacing as the cost signal — the
rAF numbers were vsync-quantized and had a 7–111 ms spread on one config.

**Finding 1 (2.5×): a flattened branch.** The composite march cost 36 ms at
3200×1800 on the hero frame — and the same 36 ms on a *completely empty* frame with
the haze off, linear in the sun-step count (2 → 6.5 ms, 64 → 81 ms) while a new
`?debug=cost` heat map showed zero sun marches executing. `texture()` (implicit
LOD) inside a per-pixel `if` makes ANGLE's D3D11 backend flatten the branch, so the
28-step sun march ran for every sample of every in-box pixel regardless of content.
Every fragment fetch is now `textureLod(…, 0.0)` (one mip level → identical filter):
36 → 14.5 ms, bit-identical on 2 of 3 views (71 px within 2/255 on the third). The
July "light cache is marginally slower" measurement was the same flattening.

**Finding 2 (2.3×): the haze deck.** `rays=0` → 5.5 ms: the sunlit haze's samples
(bottom ~30 % of the box) each ran the sun march; the cloud was cheap. Haze-only
samples now read the always-baked half-res cache (one fetch): 14.5 → 6.2 ms, A/B
0.12 % of pixels, mean 1/255, confined to the shadowed haze.

**Finding 3 (1.6×): short rays.** A step-length floor at the longest ray's step
(`?step=auto`, default): 6.2 → 3.4 ms; A/B 1–8 % of pixels, mean 1/255, diffuse.

**Streaming/pacing.** GPU byte budget for the ring (`budget.ts`; supercell bricks
10 slots ≈ 630 MB instead of 1.5 GB), z-slab uploads (worst rAF gap 222 → 28 ms),
gunzip worker pool, fps-cap fix (rendered every third tick on the 144 Hz panel:
48 fps at a 60 cap; now 16.65 ms mean). `?rs=auto` dynamic render scale (settles at
0.5 under a 4× artificial load; 1.0 on normal content) — **off by default, owner
call**. `?dither=ign` (7 % less low-frequency residue than the hash). `?anim=0` for
bit-comparable captures. 150/150 tests.

**End state:** hero frame 1600×900 whole GPU frame ~2.5 ms (was ~10); zoomed
65 → 6.7 ms at 2×. **Owner calls:** accept/revert the three measured-near-identity
defaults (`hazelc`, `step`, `dither`); `?rs=auto` as the shipped default; a coarser
supercell web tier (pipeline task, own go).

**Owner review (C.1) — ANSWERED 2026-09-05.** The A/B pairs were put in front of the
owner as a decision page (crops at the measured diff centroids, the numbers beside
each; the dither pair shown as each variant's error against the *converged* still,
because A-vs-B there only demonstrates that the noise moved):
https://claude.ai/code/artifact/96f08cea-0e5e-450f-b0b1-e640fef9b4f0

Ruling — *"they seem almost if not completely identical, so go with the better
performance."* So: **the three changed defaults stay** (`?hazelc=1`, `?step=auto`,
`?dither=ign`; revert params unchanged and documented), and **`?rs=auto` is now the
shipped default** (`main.ts` `rsParam`, README param table + intro). Verified on the
real GPU that the new default is a no-op here: default and `?rs=1` both report
`rs=1`, identical pacing (raf median 6.90 ms both), march 1.42 vs 1.27 ms — i.e.
noise, both far under the vsync floor. `?rs=1` is now the thing to pin for
bit-comparable captures. 150/150 tests, tsc clean. README's stale "78 fps @
1600×1000" status line is replaced by the measured A.6 numbers, and the beauty
plan's step 0 ("light cache: no fps win") carries a superseded banner pointing at
the flattened-branch finding. **Still open from that pass:** C.2 supercell
streaming (decode-bound; diagnose before guessing) and the coarser web tier, which
is a pipeline task with its own go.

**Lesson.** A cost that does not move with content is not a content cost. The
empty-frame control (frame 0) exposed it in one probe; without a control the July
pass concluded "the shadow march is not the bottleneck" from a true measurement
of a flattened shader.

## Capped single-cell control — RAN 2026-09-05/06, NOT DELIVERED

Owner had approved it deferred on 2026-09-02 (13 min priced). Full record:
`docs/plan-science-hurdles-2026-09-02.md` §§5.2–5.4. Commits 01e2c11, 2b1f11b and
the result commit.

**It had already been run twice, and neither attempt survived.** §5.2.1's clean
re-run (2026-09-04) integrated normally and stopped at **frame 4 of 25** when the
WSL VM went away — no CM1 error. A relaunch on 2026-09-05 never reached `mpirun`:
`gen_deck.py`'s `mktemp` deck vanished from `/tmp` ~10 s after being written, on
both members (`cp: cannot stat`). **`/tmp` is not durable on this box**; the fix is
`TMPDIR` on ext4 under `$HOME`, set in the launcher, with `run_probe.sh` left
untouched so no earlier probe's provenance moves. Both recorded in §5.2.2 *before*
any capped number existed — as was the correction that the members share **25**
frames, not the 26 §5.2 claimed (`timax` 7200 / `tapfrq` 300 = 24 intervals + the
initial write).

**Scored once, on the completed set** (both `PROBE_OK`, 25 frames): `dt3` initiation
PASS, primary singleness PASS (4 births vs the uncapped 8), secondary FAIL; `dt6`
initiation PASS, primary FAIL (28 vs 8), secondary FAIL.

**Then the counts were read before they were interpreted, and that is the finding.**
Thirty of the thirty per-frame component counts are divisible by 4. §5.3 pre-registered
a ring-or-cells test with both readings fixed in writing first — and **the test failed
its own positive control**: by its letter the *reference*, already established as one
gust-front ring in eight lobes, reads `CELLS`. The rule assumed a **circular** annulus;
the ring is square-ish (axis lobes 6.83 km, diagonal lobes 8.95 km, ratio 1.31). The
test therefore returns nothing.

**What does decide it is the configuration, not a rule.** `irandp=0`, a centred bubble,
a square domain ⇒ exact four-fold symmetry ⇒ every feature appears as 4 or 8 copies,
and the output confirms it **to the decimal** (dt6 has eight components at r=25.14 km,
all 5.99 km² and all peak 16.90 m/s). Eight independent cells cannot agree to two
decimals on area *and* peak. `n_updrafts` counts copies, the inflation factor is per
feature (4 or 8), so §5.2's per-frame comparison is **void** — a judgement made after
seeing the data and flagged as one. Orbit-counting is **not** promoted as the fix: the
reference's one ring gives two orbits, so it over-counts the same way. Bounded
statement only: distinct features ≤ count / 4, an upper bound.

**Verdict: the control is NOT delivered, and the blocker is the instrument plus the
symmetry, not the cap.** Nothing measured says the CIN knob failed — it says this
experiment cannot see whether it worked. **Owed before any third capped member**
(pre-registered): break the symmetry (the T4 `var7` seed hook, or shear) **or** build
an instrument that does not count copies. No third member until one exists.

**§5.2.1's reproducibility check PASSES exactly as predicted:** 24 of 25 frames per
member bitwise identical on every shared variable, the single exclusion being the raced
copy of `cm1out_000001.nc` — unreadable, the contended file, named in advance.
`compare_raced.py` now reports an unreadable frame and keeps it in the denominator
instead of crashing. That closes the race's one physics hazard (a truncated
`input_sounding` read would have shown up as differing fields).

**Logged closed:** peak `w` sits at the undiluted parcel ceiling in all three runs
(61.55 / 63.14 / 59.92 vs √(2·1858) = 61.0) at z = 11.25–12.75 km, well below the
`zd` = 15 km damping layer — not a damping artifact, and non-blocking either way.

**Lessons.** (i) A control that fails when it should pass invalidates the *test*, not
the subject — the fourth control-design failure in this project's record, and the first
where the flawed control caught itself. (ii) An exactly symmetric configuration makes
every count a count of copies; no threshold on such a count means what it says. (iii)
`/tmp` durability is now a documented property of this box, not a discovery to make
twice.


## Capped control — the copy-blind instrument, and the control DELIVERED as a negative

2026-09-06. Full record: `docs/plan-science-hurdles-2026-09-02.md` §§5.5–5.6.
Pre-registration commit f913be4, result commit follows it.

**§5.4 left a gate**: no third capped member until either the symmetry is broken or an
instrument exists that does not count copies. Two routes were considered and one was
**rejected for a stated reason**: a shape-agnostic ring-vs-cells classifier has **no
negative control available on disk** — an axisymmetric configuration cannot produce
genuinely distinct cells, so nothing must read `CELLS` and the classifier could only
ever be exercised on the side it is guaranteed to pass. That is the project's *control
that cannot fail* mode, and it is why it was not built. Breaking the symmetry
(`irandp=1` + `var7`) was priced at **three** members, not one — it destroys §5.2's
one-variable design, so a new uncapped reference at the same seed is owed too — and it
does not fix the instrument anyway, because a lumpy ring is still a ring.

**What was built instead** turns on the exact wording of §5.4(b)'s defect: the copy
factor is 4 or 8 **per feature**, which breaks *counts*, while a whole-domain
**integral** is exactly 4× a one-quadrant integral regardless of how many features
there are or where they sit. So a direction-only comparison of integrated quantities is
valid under the symmetry, **on the data already on disk, with no new compute**.
Precondition measured first: with `nx = ny = 180` the centre must fall *between* cells,
and it does — 0.5000 cells from the nearest cell centre, coordinate mirror residual
0.000e+00 on both axes.

**Three instrument gates, all exact zeros.** `max |w − mirror(w)|` = 0.000e+00 under
x-flip, y-flip and transpose on every frame of every run (so the four-fold symmetry is
*bitwise*, not coincidental); whole-domain minus 4× quadrant = 0.000e+00 for area and
flux; and the instrument's totals equal `ring_test.py`'s component-area sums exactly at
§5.3's three named frames.

**RESULT — §5.5's first-written outcome, the uncomfortable one.** Over §5.2's own
window (t = 75…120 min): `t5s_capped_dt3` **R_A 1.424, R_F 1.597**; `t5s_capped_dt6`
**R_A 3.062, R_F 3.236**. Both capped members produced **more** secondary convection
than the uncapped reference, monotonically in cap strength. **The capped mixed layer
fails as a single-cell control at this CAPE with zero shear** — a result about the
*design*, not the code and not the CIN generator, and the mechanism is the one §5.2
predicted in advance (the cap acts on surface-based parcels only; the bubble parcel
above it gains CAPE 2545 → 3226 J/kg, so a stronger storm makes a stronger cold pool
and triggers more along its gust front). The monotone dose–response is itself the
evidence that the cap *bit*.

Two supporting readings: the **centre-connected component** is absent in every frame of
the window in all three runs, so the split and split-free numbers are *identical* and no
part of the verdict rests on the primary/secondary split — measured, not assumed. Stated
narrowly on purpose: what the code measures is "no updraft column ≥ 10 m/s within ~1 km
of the domain centre", **not** "the pulse cell died" — a mature cell whose downdraft has
opened underneath it leaves that category while still alive (`dt6` loses its centre
component at t = 60 with `A_tot` still 495 km²). Nothing here dates the cell's death. And
a post-hoc interior restriction
(r ≤ the inscribed 89.41 km, flagged as post-hoc) leaves `dt3` unchanged and moves
`dt6` to 2.43 / 2.56 — direction unchanged.

**A retraction.** §5.4's "weak evidence that the cap bit early and was then overrun" is
**withdrawn**. It rested on `dt3`'s component counts of 1, 1, 1 where the reference had
4, 8, 8. The areas at those frames are 111.8, 119.8, 51.9 km² against 27.9, 87.8, 87.8:
**at t = 75 the capped run has four times the updraft area and one quarter the component
count.** A fully connected annulus counts as 1; a fragmented one counts as 4 or 8.

**The gate is discharged, and the result removes the reason to spend it.** A third
capped member at any Δθ is not worth running — the design fails, not the setting. The
clean single-cell control `classify_t5.py` was written against has to come from
somewhere other than a capping inversion at this CAPE with no shear. Nothing is
proposed and no go is asked for.

**Artefacts.** `runs/t5s_capped_clean/INTEGRAL_TEST.txt`; instrument
`sim/probes/integral_test.py` (tracked).

**Lesson.** A count of connected components measures **fragmentation, not quantity**,
and under a symmetry it measures neither. The project already had the first half of
this ("component counting cannot tell N cells from one ring in N lobes"); this is the
frame where it inverted — fewer components, four times the convection. The fix was not
a better classifier but a different *reduction*, and the reduction that survives a
symmetry is the integral.

## 500 m re-run of `t5s_us15` — RAN 2026-09-06, BRANCH (iii): no multicell label

The last open route to labelling a storm MULTICELL in this project. It returned a
negative, and it returned it against a decision table written while the run was still
stepping and before any of its fields had been opened (plan §4.2a, `sim/probes/README.md`
§4.2a, `sim/probes/coarsen_test.py`, config `sim/probes/configs/t5s_us15_500m.json` —
all committed as `21ff9a8` before the first frame was read).

**Only resolution moved, measured before launch.** The generated deck differs from the
1 km member's in **six lines** (`nx`, `ny`, `dx`, `dy`, and the two geometry-derived
`dx_inner`/`dy_inner`); `tot_x_len`/`tot_y_len` are identical because
360 × 499.5 m = 180 × 999 m **exactly** — an exact 2× refinement of the same physical
domain on aligned cell edges. The generated `input_sounding` sha256 is byte-for-byte the
value already in `t5s_us15`'s `run_meta.txt`. `dtl` stayed 6.0 deliberately: `adapt_dt=1`
raised dt to 6.6 then 7.26 at the first two adaptations at 1 km, so `dtl` is a seed the
solver leaves behind and halving it would have moved a second variable for no effect.

**Read in the fixed order.** Containment first, measured on this run and not inherited:
**67.93 km** (echo cells) / **63.44 km** (updraft) clearance against the 15 km floor —
contained, therefore scorable. Then the three instrument gates: **G2** (block size 1 on
the 1 km reference is the identity) PASS, 25 frames, **0 metric differences**, run while
the 500 m job was still stepping so the instrument was validated on data whose answer was
already known; **G1** (reduced grid equals the 1 km grid) PASS, max |dx|, |dy|
**7.629e-06 km**; **G3** (block² × reduced sum equals the 500 m sum) PASS, worst relative
residual **9.367e-15**.

| run | label | `P1` | `R` | `E` | span |
|---|---|---|---|---|---|
| `t5s_us15` (1 km reference) | SUPERCELL | 80 | 0.364 | 2.721 | 80.0 |
| `t5s_us15_500m` | SUPERCELL | **80** | 0.247 | **1.813** | 80.0 |
| `t5s_us15_500m_coarse_mean` | SUPERCELL | 80 | 0.197 | 1.730 | 80.0 |
| `t5s_us15_500m_coarse_extremum` | SUPERCELL | 80 | 0.257 | 1.770 | 80.0 |

**Branch (iii) as §4.2 wrote it: `P1` still reads 80, the ceiling is structural, and H3
needs a criterion this project does not have.** Doubling the resolution neither broke the
ceiling nor produced a multicell. **The confound `coarsen_test.py` was built for never
arose** — `P1` did not break at 500 m at all, so there was no chain break to attribute to
fragmentation — and the coarsened runs read 80 as well, closing the other direction: the
ceiling is not an artifact of the measurement grid either way.

**A correction to the sweep's own wording.** §4.2 recorded criterion 2′ as putting `us15`
"decisively on the multicell side **on both statistics**". The code is the authority:
`organised = (R ≥ 0.60) or (E ≥ 2.40)`, and `organised` is what gates MULTICELL
(`classify_v2` ~line 844, `classify_v3` ~line 923 — identical). `R = 0.364` is *below* its
floor and contributes **nothing** to `organised`. Both statistics sit outside their §8.6
bands, but **only `E` carried multicell-side weight through the rule**: `us15`'s
multicell-side evidence at 1 km was one statistic, not two.

**The code was already precise; the prose generalised it.** `score_t5s.py`'s own printed annotation reads `[E=2.721 past the decisive edge 2.40; R=0.364 below the decisive edge 0.40]` — exactly the distinction above. The scorer was **re-run 2026-09-06** after the three new run directories appeared alongside the sweep (`t5s_us15_500m` and the two derived `_coarse_*`): output unchanged, no regression. It addresses runs by explicit name and globs nothing, so derived siblings in the runs root cannot be picked up by it.

**So "E stays high" — given its number in §4.2a before the run was read, `E ≥ 2.40` with
`R ≤ 0.40` — is FALSE.** `E = 1.813` is below 2.40 and inside the 1.667–2.40 band, which
is §8.6's INDETERMINATE zone. The single statistic that put `us15` on the multicell side
at 1 km does not clear its floor at 500 m.

**And the drop is in the flow, not the measurement.** Said plainly because it is *not*
what the instrument was pre-registered for: block-reduced onto the **exact** 1 km grid and
read by the **unchanged** classifier, the 500 m storm gives `E` 1.730 (mean) / 1.770
(extremum) and `R` 0.197 / 0.257 — beside the raw 500 m values, nowhere near the 1 km run's
2.721 / 0.364. **Coarsening does not restore the 1 km numbers**, and the two reductions
agree, so the test is not indeterminate. A better-resolved storm in this environment is
genuinely less elongated and less coherent; the 1 km elongation was a property of the 1 km
*simulation*, not of the 1 km *measurement*.

**The descriptors do not move together under refinement.** The 1 km trends were `R`
0.364 → 0.526 → 0.560 (rising with shear) and `E` 2.721 → 1.948 → 1.546 (falling).
Refining `us15` moves `R` *further* from `us20`/`us25` — that separation **strengthens** —
and moves `E` into the *middle* of the 1 km trend, between `us20`'s 1.948 and `us25`'s
1.546 — that separation **weakens**. **— THE `R` HALF IS RETRACTED 2026-09-06** (see the `t5s_us20` 500 m record below): refining `us20` as well NARROWS the `R` separation on every basis (0.162 → 0.089 / 0.038 / 0.026), so "strengthens" was a one-sided-refinement artifact. No reading that treats the descriptor family as one
coherent signal is supported.

**A bound on the resolution confound, not a measurement of it.** Refining one member moved
`E` by **0.908** raw — and by **0.991** (mean) / **0.951** (extremum) measured *on the reference grid itself*, the apples-to-apples pair, since the raw figure still compares across grids in the very claim about grid confounding. All three exceed the `us15` → `us20` shear step of **0.773**. That bounds the
confound on the `E` trend; it is **not** a finding that the trend is an artifact, because
**only one member was refined**. The measurement that would settle it is a 500 m
`t5s_us20` — named in §4.2a as the escalation and **NOT RUN**: the owner's go covered one
run, and no go is asked for.

**What survives and what does not.** §4.2's structural-transition-between-`U_s` 15-and-20
claim does not rest on `E` alone — the split test is a classifier-free measurement and is
untouched by this run, and `R`'s separation gets *stronger* under refinement. That claim
stands. **— AMENDED 2026-09-06: the claim stands, but on the split test ALONE. The `R` support is withdrawn** (see below), and the split test has never been read at 500 m. What does not survive is any reading in which `us15`'s `E ≥ 2.40` at 1 km is
resolution-robust evidence of a line-like regime.

**Artefacts.** `runs/t5s_us15_500m/` (25 frames), derived
`runs/t5s_us15_500m_coarse_{mean,extremum}/`; instruments `sim/probes/coarsen_test.py` and
config `sim/probes/configs/t5s_us15_500m.json`, both tracked and both committed before the
result existed.

**Lesson.** The instrument built for one confound answered a different one. `coarsen_test`
exists to ask whether a broken `P1` is physics or fragmentation; `P1` never broke, so on
its own question it returned nothing. Putting the refined run back on the coarse grid,
though, separated *the storm changed* from *the ruler changed* for `E` and `R` — a
question nobody had posed. Building the instrument as "a different reduction, read by the
unchanged classifier" rather than as a bespoke test is what made it reusable for a
question it was not designed for.

## Second 500 m run — `t5s_us20` — RAN 2026-09-06, BRANCH (B): the 15 → 20 elongation gap is substantially resolution

**The owner's go.** "the second 500 m run that would settle how much of the trend is
resolution rather than environment — run it". §4.2a had named a 500 m `t5s_us20` as the
escalation and left it unrun because the previous go covered one run. This is that run.

**Why one refined member could not settle it.** §4.2a measured that refining `us15` moved
`E` by 0.908 raw / 0.991 mean / 0.951 extremum, all larger than the `us15` → `us20` shear
step of 0.773 at 1 km. From a single refined point, a common offset applied to every
member and a collapse specific to `us15` are indistinguishable. Two refined members
separate them, because the gap between them can then be read **at matched resolution**.

**The trap that was avoided, and proved rather than asserted.** `t5s_us20_500m.json` was
built from `t5s_us20.json`, **not** by cloning `t5s_us15_500m.json` — the clone would have
carried `umove` 9.9 and `U_s` 15 and silently answered a different question. Four keys
move (`nx`, `ny` 180 → 360; `dx`, `dy` 999.0 → 499.5). Gated before launch: the generated
deck differs in **exactly six lines** with `tot_x_len`/`tot_y_len` identical at 179 820.0 m
(360 × 499.5 = 180 × 999 exactly); `umove` reads **13.3** in both; the generated
`input_sounding` sha256 `7538c7ae…` matches **four ways** — generated from this config,
generated from `t5s_us20.json`, recorded in `t5s_us20`'s `run_meta.txt`, and on disk in
that run directory. `np=8`, pinned fork binary `5fc93016…`.

**Pre-registered in flight.** Plan §4.2b — the comparison, the bar and the three branches —
was written and committed (`ddff22d`) while the run was stepping and **before any of its
fields were opened**. The bar was **NEW**, was declared new rather than dressed as
pre-existing, and is still labelled new in the result.

**Containment first, measured on this run and not inherited** (`us20` translates at
13.3 m/s against 9.9 m/s in the same 180 km box): **60.94 km** echo-cell and **32.47 km**
updraft clearance against the 15 km floor — contained, therefore scorable. The 1 km member
re-measured at 65.93 / 64.94 km. *Coincidence, recorded so nobody chases it:* 32.47 is
exactly half of 64.94 and looks like a units bug; it is not — `us15`'s pair ran ratios 0.97
and 0.89, so the code does not systematically halve `w`-clearance at 500 m.

**Instrument gates, all three PASS.** G2 against `t5s_us20` as its own reference (a
per-reference claim; `us15`'s pass does not transfer) — 25 frames, **0 metric
differences**, run *before the 500 m data existed*. G1 — max |dx|, |dy| **7.629e-06 km**,
both reductions. G3 — worst relative residual **2.806e-15** on `thpert`.

| run | label | `P1` | `R` | `E` | span |
|---|---|---|---|---|---|
| `t5s_us20` (1 km reference) | SUPERCELL | 80 | 0.526 | **1.948** | 80.0 |
| `t5s_us20_500m` (raw) | SUPERCELL | 80 | 0.273 | 1.442 | 80.0 |
| `t5s_us20_500m_coarse_mean` | SUPERCELL | 80 | 0.286 | **1.405** | 80.0 |
| `t5s_us20_500m_coarse_extremum` | SUPERCELL | 80 | 0.295 | **1.426** | 80.0 |

The 1 km reference re-read **1.948** through this run's own code path, so the gap's
denominator is not drifting.

**The verdict against the committed table.** Branch (A) needed `E`(`us20_500m`) ≤ 1.343
(mean) or ≤ 1.383 (extremum); it is 1.405 and 1.426. Branch (C) needed > 1.730 / 1.770; it
is not.

| basis | `G_ref` | vs `G_1km` = 0.773 | branch |
|---|---|---|---|
| coarsened block-mean **(headline)** | **0.325** | 42.0 % retained | **(B)** |
| coarsened block-extremum **(headline)** | **0.344** | 44.5 % | **(B)** |
| raw 500 m (not decisive) | 0.371 | 48.0 % | (B) |

**All three bases agree, including the raw one** — the number a sceptic reaches for, which
misses the bar by only 4 % and still lands in (B). The two headline reductions agree, so
the test is not INDETERMINATE. **Branch (B): the 15 → 20 separation in `E` keeps its sign
and loses more than half its 1 km size. Resolution contributed at least as much as the
shear step did; the 1 km `E` trend across this step is not resolution-robust.**

**Mechanism (descriptive, not the decision).** Refinement moved `E` by 0.543 / 0.522 /
0.506 on `us20` against 0.991 / 0.951 / 0.908 on `us15` — `us15` loses about **1.8×** as
much on every basis. Both fall; one falls harder. That is not the common offset branch (A)
required. **Not extended to "the refinement effect scales with shear"** — `us25` is
unrefined and §4.2b forbade the wider claim in advance.

**RETRACTION — `R`'s separation, the statistic §4.2a used as its independent check.**
§4.2a wrote that refining `us15` moved `R` *further* from `us20`/`us25`, "so that
separation **strengthens**", and leaned on it. With **both** members refined the `R`
separation **narrows on every basis**, sign preserved: 0.162 at 1 km → 0.089 (mean, 55 %
retained) / 0.038 (extremum, 23 %) / 0.026 (raw, 16 %). Stated as a **direction, not a
magnitude** — the bases spread 16–55 %, unlike `E`'s tight 42–48 %, so no single number is
quoted as *the* `R` gap. §4.2a's "`R` strengthens" was itself a **one-sided-refinement
artifact — the same error class this run was built to correct, found in the very statistic
§4.2a used as its independent check.** §4.2a listed two supports for the
structural-transition-between-15-and-20 claim; **one is withdrawn.** The claim **survives
on one leg, not two**: the split test (classifier-free) is untouched by both 500 m runs.
The §4.2a paragraphs in the plan and in `sim/probes/README.md` are corrected in place, not
only here.

**Newly open, named without being run:** the split test has never been read at 500 m. That
is the honest next escalation for the transition claim, and it is not this run's job.

**The confound the instrument was built for failed to fire a second time.**
`coarsen_test.py` exists for the `P1` fragmentation confound. `P1` reads 80 on the 1 km
run, the raw 500 m run and both reductions; near-floor frames read **none** for both
members; there is no chain break to attribute to anything. The instrument earned its keep
on `E` and `R` instead — twice now, by accident rather than design. `P1` = 80 and a
SUPERCELL label were pre-registered as expected and uninformative, and they were.

**What this does NOT settle, in §4.2b's own words.** The **15 → 20 step only**. `us25`
stays at 1 km, so **the three-member `E` trend is not settled**, and no statement of the
form "the sweep's `E` trend is / is not a resolution artifact" is licensed.

**No regression.** `score_t5s.py` re-run after the two new derived directories appeared:
output unchanged (`us15` 80 / 0.364 / 2.721, `us20` 80 / 0.526 / 1.948, `us25` 80 / 0.560 /
1.546; `P1` at ceiling 3/3; verdict still NO DISCRIMINATOR).

**Artefacts.** `runs/t5s_us20_500m/` (25 frames, 3.6 GB), derived
`runs/t5s_us20_500m_coarse_{mean,extremum}/`; config
`sim/probes/configs/t5s_us20_500m.json`, tracked and committed before the result existed;
instrument `sim/probes/coarsen_test.py` **unchanged** — it already took `--run`/`--ref`, so
no constant was edited in place and the `us15` invocation stays reproducible from the same
file.

**Lesson.** *A one-sided refinement can flip the sign of a comparison's conclusion.*
Refining one member of a pair moves both the member and its distance from every unrefined
member, and those two effects are not separable from one point. §4.2a's `E` finding
survived the second member; its `R` finding did not, and the `R` claim had been used as the
independent corroboration precisely because it looked untouched. The rule this leaves: **a
resolution claim about a *difference* needs both sides refined — refining one side bounds
the confound and can invent a trend that is not there.**
