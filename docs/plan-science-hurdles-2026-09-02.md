# The open scientific hurdles, and the way through each — 2026-09-02

**What this document is.** A ranked list of the project's unsolved science problems as
the record actually shows them, a root-cause reading of the one that is blocking Phase 3,
a concrete proposal (with code landed and gated where it can be gated without the WSL
box), and the plan amendments that follow. **What it is not:** a result. Nothing here
has run on CM1. The proposal's first step is a source read, its second is two neutrality
runs, and it needs an owner go for both (charter: no phase or task starts without one).

**Ranking rule:** hurdles are ordered by how much of the remaining plan they block, not
by how hard they are. H1 blocks Phase 3 today; H2 blocks the charter's
"forecast → outcome" teaching promise; H3 is a measurement-design problem inside H1;
H4–H6 gate later phases and are listed so their prerequisites are designed in now
rather than discovered.

---

## 1. The hurdles, ranked

| # | Hurdle | Where the record shows it | What it blocks |
|---|---|---|---|
| **H1** | **The multicell regime is unreachable from the namelist.** CM1's analytic wind options give 0–6 km bulk shear of 10 / 31.8 / 33.5 m/s; the multicell↔supercell transition sits between the first two. Four candidates (A, B, C, C2) classify SUPERCELL under two independent rotation criteria. | `phase3-t5-multicell.md` §§2.2, 9, 11, 13 | Phase 3 T5 → T6 → T7. The charter's *single → multicell → supercell* progression has no multicell. |
| **H2** | **CIN is a design task with no implementation.** The WK82 sounding has "weak, incidental CIN"; the forecast panel promises CIN as a storm-development condition. The same gap made the T5 pulse-cell control ring up daughter convection ("one bubble ⇒ one cell is false over 2 h with no CIN"). | charter *Known decisions*; advisor item 7; T5 §7.5 | The forecast→outcome panel; any "capped" scenario; clean single-cell controls. |
| **H3** | **The classifier does not separate multicell from supercell** at 1 km. `P1` (rotation persistence) saturates at 80 min for every storm; the descriptors that *appear* to separate (`P2`, chain continuity) rank the candidates two different ways and were correctly not promoted post hoc. | T5 §§13.4–13.6, 13.9 | Scoring any future multicell candidate honestly. |
| **H4** | **CM1's `uh` is non-negative**, so a left-moving supercell carries no rotation signal in the field the classifier reads. | T5 §13.7 (measured: `min == 0.0` in all 50 control frames) | Classifying mirror-image splits (candidate A's kind); teaching left/right movers. |
| **H5** | **Terrain-following → Cartesian regridding** does not exist yet (CM1's own is "quick-and-dirty"). | charter; Phase 3 plan §8 | All of Phase 3T. |
| **H6** | **Lightning parameterization prerequisites** (McCaul et al. 2009 needs graupel flux at the −15 °C level and updraft volume; the −15 °C surface needs temperature in the output). | charter *Lightning*; Phase 4 | Phase 4's first task. |

---

## 2. H1 and H2 are one hurdle, and its root cause is where the environment is computed

Every T5 dead end has the same shape. `iwnd=1/2/4` and `iinit=1/8` are **option
selectors**; every parameter inside an option (`35.0`, `3000.0`, `0.25 K`, bubble radii,
line geometry) is a hardcoded Fortran local (T5 §1). The Phase 3 plan (§2.3) read this
correctly as "multicell is Fortran, not namelist"; T5 §2.2 read it as "only a source
edit can reach the gap" and priced a second fork. **Both readings assume the environment
must be computed inside CM1.** It need not be.

**Stock cm1r21.1 reads the base state from an external file at `isnd=7`.** The file is
`input_sounding` in the run directory, in the WRF idealized-case format:

```
p_sfc[hPa]  theta_sfc[K]  qv_sfc[g/kg]            <- line 1, the surface
z[m]  theta[K]  qv[g/kg]  u[m/s]  v[m/s]           <- one line per level, ascending
```

— and **the wind profile comes from the same file**. Every quantity T5 called
unreachable becomes a number in a generated text file: shear magnitude, shear depth,
hodograph shape, the CAPE knob, and the CIN knob the charter has carried since the
advisor review.

**What this changes and what it does not.**

| Claim | Before | After (isnd=7 scenarios only) |
|---|---|---|
| "The namelist is CM1's sole scenario input" | true (T1c, §10.2) | **"The namelist plus one generated text file, both rendered from the same `sim/scenarios/<name>.json`."** `run_meta.txt` records `input_sounding_sha256` beside `cm1_binary_sha256`. Same recovery path, one more file. |
| "The binary is the T4 fork binary `5fc93016…`" | true | **unchanged.** No `0002-` patch, no third hash, the charter's CM1 pin does not move. |
| The three shipped scenarios | `isnd=5` | **untouched** — all deck gates still byte-identical (`test_deck` 16/16, `test_seed_t4` 17/17, `test_scenario_t6` 11/11, `test_supercell_t2` 10/10). |
| Bitwise reproducibility (same config, binary, ranks) | holds | **holds** — the file is deterministic text; CM1's read of it is deterministic. |
| Neutrality vs `isnd=5` | n/a | **NOT bitwise** — CM1 interpolates the file onto its levels. The gate is a base-state comparison (§4.1), and the storm-level check is the Phase 0 same-family test. |

**What is NOT verified, stated bluntly.** The CM1 source is not in this repository and
its website is egress-blocked from the session that wrote this, so three facts are from
memory of `README.namelist`, not from a source read: (a) the `isnd=7` file format above;
(b) that at `isnd=7` the wind is taken from the file and `iwnd` is not applied on top;
(c) the maximum number of file levels `base.F` accepts (the writer emits 441). The
project's own rule — T4 and T5 both found their plan's premise false by reading the
source first — applies here with full force: **step 1 of T5s is a `base.F` read, not a
run**, and the neutrality gates in §4.1 are the empirical check either way. The deck
generator already hedges (b): it *requires* `iwnd=0` at `isnd=7`, which is correct if
`iwnd` is ignored and is caught immediately by the wind-neutrality gate if it is not
(0 would zero the winds; `u0` would read 0 instead of `t5probe_a`'s profile).

---

## 3. What landed in this commit (gated offline; nothing run on the box)

### 3.1 `pipeline/cm1post/sounding.py` — the environment generator

Every formula cites its paper in the module docstring; the summary:

- **Thermodynamics: Weisman & Klemp (1982) eqs. 1–2**, hydrostatic in Exner form with
  virtual potential temperature (how CM1 builds its own base state). Defaults θ₀=300 K,
  θ_tr=343 K, T_tr=213 K, z_tr=12 km, qv_pbl=14 g/kg, p_sfc=1000 hPa. Measured by the
  generator: T(z_tr)=217.3 K (WK82's constants are self-consistent to 4 K),
  p(z_tr)=202 hPa.
- **CIN knob — capped mixed layer.** A well-mixed layer beneath a capping inversion of
  strength Δθ that relaxes linearly onto WK82 over a blend depth. Knob semantics follow
  McCaul & Cohen (2002) and McCaul & Weisman (2001); the piecewise construction is this
  module's own and is written out in `apply_cap` so it can be checked, not trusted. The
  cap edits θ only; qv stays WK82's. **CAPE is held** by solving qv_pbl for a target
  CAPE with the cap applied. Measured: Δθ = 0…4 K moves SB CIN −48 → −74 J/kg while
  CAPE drifts 3 J/kg.
- **Wind: `tanh` (WK82 §2; CM1's `iwnd=4` is U_s=35, z_s=3 km) and `linear` (RKW88;
  CM1's `iwnd=1` is U_s=10, z_s=2.5 km)**, with U_s and z_s free. The generator
  reproduces T5 §2.1's hand-derived numbers: 35 tanh(z/3 km) reads 33.5 m/s at CM1's
  5.75 km scalar level (33.74 at exactly 6 km), and its 0–6 km mean is 23.1 m/s (probe A
  used 23.2).
- **Diagnostics, reported never fed back:** SB and ML500 parcel CAPE/CIN/LCL/LFC/EL
  (pseudo-adiabatic on Bolton 1980 θ_e, with the Doswell & Rasmussen 1994 virtual
  correction — gated to be *live*: it moves CAPE by +106 J/kg); 0–6 km bulk shear;
  layer-mean wind (the `umove` estimate); **BRN (WK82 eq. 3)** and **the WK82 regime it
  predicts** (10 ≤ BRN ≤ 50 supercell; > 50 multicell; < 10 shear-dominated).
- **A saturated base state is refused, never clipped** — a 14 g/kg well-mixed layer
  1 km deep saturates at its top (its LCL is ~1 km); the generator says so. A silently
  drier layer would be a different CAPE shipped under the declared one.

### 3.2 The integration

- `scenario.py` loads `sim.sounding`; **`deck.py` Category 6** refuses `isnd=7` without a
  block, a block without `isnd=7`, and `isnd=7` with `iwnd≠0`; nothing is substituted
  into the namelist (no bogus `sounding =` line).
- `gen_sounding.py` renders the file and a diagnostics JSON; `--wk82-reference` writes
  the stock profile for the neutrality gate.
- `run_scenario.sh` generates the file with the deck, **removes any stale
  `input_sounding` from the run dir before staging** (an `isnd=7` run would read a
  leftover from another scenario silently; an `isnd=5` run would ignore it silently),
  and records `input_sounding_sha256` in `run_meta.txt`.
- `pipeline/tests/test_sounding_t5s.py` — **29/29**, seven families with negative
  controls: WK82 fixed points; parcel behaviour (monotone in moisture, zero when dry,
  virtual correction live); the CIN knob (monotone, CAPE held, saturation refused,
  malformed cap refused); BRN monotone in shear with the 50-crossing inside the gap; file
  format round-trip and malformed-file refusal; the coupling (all four refusals + the
  positive path, shipped scenarios untouched); and that every `t5s_*` probe config's
  recorded prediction equals what its own sounding computes.

### 3.3 The measured picture the sweep is designed on

WK82 reference thermodynamics (14 g/kg), tanh wind, z_s = 3 km — computed by the
generator before any run:

| U_s (m/s) | 0–6 km bulk shear | BRN | WK82 prediction |
|---|---|---|---|
| 10 | 9.6 | 132 | multicell |
| **15** | **14.5** | **59** | **multicell** |
| **20** | **19.3** | **33** | **supercell** |
| 25 | 24.1 | 21 | supercell |
| 30 | 28.9 | 15 | supercell |
| 35 (= `iwnd=4`) | 33.7 | 11 | supercell (candidate A: confirmed supercell, T5 §9.3) |

SB CAPE 1859 J/kg, CIN −48 J/kg, LCL 1.0 km, LFC 1.7 km, EL 11.4 km for every row (the
thermodynamics are fixed; only the wind varies). **The BRN=50 boundary sits between
U_s 15 and 20 — the middle of T5's unreachable 10–31.8 m/s gap.** The `iwnd=1` RKW
profile (10 m/s over 2.5 km) has BRN 90 by the same arithmetic, and B still came back a
rotating cell — the honest caveat that BRN is a regime *tendency* at 1 km/NSSL, which
is exactly why the sweep is pre-registered as a prediction to be falsified, not as a
result.

---

## 4. T5s — the proposed task, pre-registered

**Sequence** is §8's of the T5 doc, which worked three times: source read → controls
committed and run → gates pass → *then* the sweep is run and read. Configs are tracked in
`sim/probes/configs/t5s_*.json` and each carries its prediction.

### 4.0 Source read (no run) — **DONE 2026-09-02. All three confirmed; findings and
line numbers in `sim/probes/README.md`.**

In `base.F` of the pinned tarball: confirm (a) the `isnd.eq.7` reader and its column
order/units; (b) whether `iwnd` is applied at `isnd=7`; (c) the level cap. Record the
three line numbers in `sim/probes/README.md`. If (a) differs from §2's format, fix the
writer *before* any run; if (b) says `iwnd` is applied, keep `iwnd=0` and confirm the
file's winds survive in `u0` (the gate below); if (c) is below 441, raise `dz_m`.

**Outcome.** (a) the format is exactly as §2 states; (b) `iwnd` is ignored, settled
three ways in source — `param.F` even forces it to 0 with a *non-fatal* warning, so
this project's refusal is stricter than CM1's; (c) the cap is 1 000 000 levels, and the
binding constraint is instead that the file's last `z` exceed the top **scalar** level
(19 750 m, not the 20 000 m nominal top) — the writer's 22 000 m clears it. §2's
"what is NOT verified, stated bluntly" paragraph is now discharged; nothing in the
design changed.

**One thing the read caught that a run would not have.** The deck template runs
`output_basestate = 0`, so `th0`/`qv0`/`prs0`/`u0`/`v0` are simply not written to the
netCDF — the §4.1 gates would have been **unevaluable after** their runs. The `t5s_*`
configs now declare `output_basestate: 1` (a Category 5 optional key, so the shipped
scenarios stay byte-identical). CM1's other candidate output for this,
`input_sounding_grid`, is dead code behind `dothis = .false.`

**Also fixed before any run:** `sim/probes/run_probe.sh` did not generate
`input_sounding` at all — the probes README claimed it did. A `t5s_*` probe launched
through it would have died on a missing file, or silently read a stale one left from an
earlier version of the same config. It now generates the file from the config, removes
any stale one before staging, and records `input_sounding_sha256` in `run_meta.txt`.

### 4.1 Neutrality controls — two 1 km runs, ~13 min each at `np=4`

| Run | Reference | Gate (pass/fail, fixed now) |
|---|---|---|
| `t5s_neutral_pc` — PC's deck with `isnd 5→7`, WK82 reference file, no wind | `t5probe_pc` (on disk) | `th0`, `qv0`, `prs0` at t=0: \|Δθ\| < 0.1 K and \|Δqv\| < 0.05 g/kg at every level; CM1's own `cape`/`cin` at t=0 within 10 % of `input_sounding.report.json`'s SB values; same pulse cell: peak `w` within 5 %, peak time ± 5 min. |
| `t5s_neutral_a` — A's deck with `isnd 5→7`, `iwnd 4→0`, WK82 + tanh U_s=35 | `t5probe_a` (on disk) | `u0` at every level within 0.2 m/s of A's, `v0` = 0 (**confirms in the run what §4.0 settled in the source**); same supercell family: peak `w` within 5 %. |

**The `neutral_pc` gate tests two separable claims, and they are scored separately.**
"CM1 read the file and honoured it" (plumbing) and "this project's WK82 equals CM1's
WK82" (two implementations of one paper) would otherwise fail as one number, and an
innocuous formula difference would stop T5s under a gate meant for the plumbing. So a
tolerance breach triggers a **second comparison first**: CM1's t=0 base state against
**the generated file's own values interpolated to CM1's levels the way `base.F` does
it** (RH-preserving — `base.F:686-716`). That comparison contains no WK82 content at
all. Plumbing is only declared broken if *it* also fails. Pre-registered here before
the run, not chosen after seeing a residual. (The §4.0 read makes a large residual
unlikely: the two WK82s share constants, formulas and the moisture clip — see
`sim/probes/README.md`. The two known differences, a saturated-surface first half-step
at `isnd=5` and the 100 m-to-model-level interpolation, are expected in the residual.)

**RESULT 2026-09-02 -- BOTH GATES PASSED, 11/11.** Plumbing at floating-point noise
(theta 2.2e-05 K, qv 8.5e-07 g/kg); implementation at the offline-predicted 0.0048 g/kg;
CM1's own t=0 CAPE within 0.03 %; the wind is the file's and is not zeroed by `iwnd=0`;
the pulse cell reproduces to 0.07 % and the supercell to 2.45 %, both at identical peak
times. Full table in `sim/probes/README.md`. **§4.2's sweep is unblocked, and option (i)
is now measured to be unnecessary (owner decision 2).**

**Either gate failing stops T5s.** A base-state mismatch means `isnd=7` is not what §2
says; a wind mismatch with `u0 ≡ 0` means `iwnd` *is* applied and the deck rule must
change to "iwnd=0 is forbidden at isnd=7, declare the file's own profile" — a
different, still namelist-only fix. Neither outcome costs a fork.

**Also banked by these runs, at no extra cost:** CM1's t=0 `cape`/`cin` against this
generator's parcel numbers. The offline gate only asserts a WK82-plausible band
(1500–2800 J/kg); the run is where the parcel method meets a second implementation.

### 4.2 The shear sweep — three 1 km runs

`t5s_us15` (BRN 59, **predicted multicell**), `t5s_us20` (BRN 33, predicted supercell),
`t5s_us25` (BRN 21, supercell-side anchor). WK82 thermodynamics fixed; `imove=1` with
`umove` = the profile's 0–6 km mean (probe A's convention); `irandp=0`; the six-probe
geometry (180² @ 999 m, 2 h).

**Scoring, fixed before the runs:**

1. **The existing classifier, thresholds UNCHANGED** (`classify_t5.py`: criterion 1′
   persistence, 2′ organisation, 3 sustained system; T5 §12). Nothing is re-tuned for
   the sweep — T5 spent three rounds establishing that k, the floor and `P2` are not to
   be moved, and this sweep inherits that.
2. **WK82's own multicell signature, discrete propagation**, which no T5 criterion
   measures and which H3 says is the missing discriminator: *after the first cell's
   updraft maximum decays below half its peak, a new |w| ≥ 10 m/s updraft component at
   3–6 km appears ≥ 8 km (storm-relative) from every existing component's centroid and
   persists ≥ 15 min — a "birth".* **Multicell if births ≥ 3 in 2 h.** The split of a
   supercell is one birth by this definition (the left mover appears ~20 km away, once),
   so the threshold is deliberately above it; a multicell regenerates on the gust front
   every 20–30 min (WK82 §4), giving 3–5 births in 2 h. **Validated on SC and PC first**
   (both on disk): SC must score ≤ 1 birth, PC ≤ 1 (its daughter ring at t > 70 min is
   the risk — if PC scores ≥ 3, the persistence floor is raised on the CONTROLS only and
   the sweep is not read until the controls pass). The measurement is implemented and
   committed with its control results before the sweep runs.
3. **Prediction table:** us15 → MULTICELL by both (1) and (2); us20, us25 → SUPERCELL by
   both. Recorded here and in each config's `provenance.brn_regime_prediction`.

**SCORING AMENDED 2026-09-02, BEFORE THE SWEEP WAS READ.** Criterion 2 above **failed
its own control validation** and is therefore **not promoted and does not label
anything** (full record: `sim/probes/README.md`). In one line: its trigger could not
fire on five of six runs; with the trigger replaced and two threshold-free
implementation defects fixed, the supercell control scores 2 births against a bar of
<= 1, and the single-cell control's 0 is not a pass but a non-exercise -- its
gust-front ring appears four times over, identical to the decimal, in the censored
tail, and fifteen minutes earlier it would have labelled the single-cell control
MULTICELL. Criterion 2 is reported as a descriptor with its control numbers attached.

**What this leaves, stated in advance.** Scoring falls back to the existing classifier
(criterion 1-prime persistence, 2-prime organisation, 3 sustained system), thresholds
unchanged. **And criterion 1-prime is expected to saturate**: `P1` is measured over the
mature window (t >= 40 min of a 120 min run), so its ceiling is 80 min, T5 section 13.4
measured every one of its six storms at that ceiling, and the SUPERCELL band starts at
35 min. So:

- **`P1 = 80` is the ceiling, not evidence.** A member reading 80 has told us its
  rotation did not break for the whole mature window; it has *not* told us it is a
  supercell rather than a multicell whose successive cells each rotate. This is
  written down now so that an 80 cannot later be read as a result.
- **If all three members read `P1 = 80`,** criterion 1-prime has no discriminating
  power on this sweep, criterion 2 is unavailable, and the honest outcome is **"no
  discriminator" -- not "three supercells."** That lands in section 4.2's own 500 m
  contingency, which is then about resolution *and* about H3, not about the
  environment.
- **The environment question is separately answerable and is the point of the sweep.**
  BRN, bulk shear and the base state are properties of the file, already verified. What
  the three runs add is the *descriptor family* across U_s = 15/20/25 -- updraft counts,
  cold-pool area, echo organisation `R`/`E`, `P2` path-to-net ratio, births as a
  descriptor -- read as a TREND across a controlled one-parameter sweep. A monotone
  trend across three members is evidence about the regime even when no single member
  can be labelled, and it is the first time this project has had a one-parameter
  environmental sweep to read at all.

**What would falsify what.** All three SUPERCELL → BRN does not predict regime at
1 km/NSSL in this family, and the next step is a 500 m re-run of `t5s_us15` (T5 §6.1's
resolution caveat: 1 km under-resolves 5–10 km cells) *before* concluding the
environment is wrong — not a lower U_s, which would be §7.4's trap with a config as
victim. ~~us15 MULTICELL by (2) but SUPERCELL by (1)~~ and ~~us15 MULTICELL by
both~~ -- **both branches are VOID**: they turn on criterion 2, which did not clear its
control and cannot promote anything. What replaces them, pre-registered above: read the
descriptor family as a trend across U_s, and treat a saturated `P1` as a ceiling rather
than a supercell finding. If the descriptors trend toward multicell structure while no
member can be labelled, that is a *result about the classifier* (H3) sitting on top of
a *result about the environment*, and both get recorded as what they are.

**SWEEP RESULT 2026-09-02 (full record: `sim/probes/README.md`).** All three ran,
all three contained (60-71 km clearance vs a 15 km floor). All three label SUPERCELL
**on a criterion at its ceiling** -- `P1 = 80` for every sheared storm this project has
run, against 5 for the unsheared control, so `P1` separates sheared from unsheared and
not multicell from supercell: H3, sharpened by a controlled sweep. The descriptors are
**monotone** in shear (`R` 0.364 -> 0.526 -> 0.560, `E` 2.721 -> 1.948 -> 1.546), and
criterion 2-prime read alone on UNCHANGED thresholds puts **`us15` decisively on the
multicell side on both statistics** while `us20`, `us25` and the supercell control are
all INDETERMINATE. **The structural transition lands between U_s 15 and 20 -- exactly
where BRN crosses 50**, as section 3.3 predicted from the sounding before any run.
NOT claimed: that `us15` is a multicell. Its own descriptors complicate it -- fewest
updrafts, zero births -- so its signature is line-like (elongated, incoherent) rather
than discrete-cell multiplicity, and those are different objects. **SPLIT TEST (the alternative T5 section 8.3 names) RUN AND FALSIFIED:** `us15` has
ONE two-component echo frame in its mature window while `us20`/`us25` have 6 and 9 --
perfectly mirrored, equal areas to the km2, diverging at 3-4 m/s -- and the splitters
score HIGHER R, not the R~0 that section 8.3 predicts. So `us15` is not a split
misread, and `us20`/`us25` carry the textbook supercell signature measured with no
classifier at all -- separating the sweep in the same place BRN did. Next step is this
section's own contingency, a 500 m re-run of `us15`, with THREE branches fixed in
advance: P1 breaks and E holds (resolution artifact -> MULTICELL); P1 breaks and E
collapses (the elongation was resolution-driven too); P1 still reads 80 (the ceiling
is structural and H3 needs a criterion this project does not have).

### 4.3 Cost

Five 1 km probes × ~13 min at `np=4`; one classifier addition (discrete propagation)
with its control run before the sweep; no CM1 rebuild; no pin moves. A 500 m
contingency re-run of one member is ~2 h. Total well under one working day of machine
time.

### 4.4 What T5s retires

- **Option (i), the `0002-` shear patch** — its premise ("only a source edit can reach
  the gap") is false. **RESOLVED 2026-09-02 (owner).** **The owner dropped it.** Retired: no third
  binary, no pin move, fork count stays at one.
- **T5 §11.7's carried consequence** (a periodic-y line has no finite condensate extent
  in y, so the crop-box measurement inherits an error one level up in the export path):
  a compact WK82 multicell at open boundaries replaces the line as the T6 asset, so the
  hazard is avoided rather than solved. If the owner still wants the squall line as a
  scenario, that hazard returns and needs the box-measurement fix first.
  — **RESOLVED 2026-09-02 (owner): KEEP.** **The owner keeps the squall line, so the hazard is NOT avoided
  and this bullet does not retire.**

**What keeping it costs, scoped 2026-09-02.** T5 §11.7 named one hazard — a periodic-y
domain has no finite condensate extent in y, so the crop-box measurement would apply a
compact-storm criterion to a wrapping direction. Reading the export path to size the
work found a **second and sharper** problem the note did not have:

1. **The scenario schema cannot describe a line.** `Scenario` carries a single
   `crop_half_width_m`, and the derived grid hardcodes `ny = nx`
   (`pipeline/cm1post/scenario.py`) — the export box is **square by construction**. A
   squall line needs a *compact* extent across the line and the *full domain* along it.
   With the schema as it stands the only legal box for a line is the full square
   domain: the largest possible package, mostly empty. So this is not only a
   measurement fix; the contract needs a separate along-line half-extent, and
   `nx`, `ny`, `origin_m` and every consumer follow.
2. **The measurement itself** — on a periodic axis the extent is the full domain **by
   construction**, not a measured condensate union. `require_measured_box` must accept
   that as a *valid measured route* rather than treating it as an unmeasured
   placeholder, or a line can never clear the gate that exists to stop a box being
   copied from a different storm.
3. **Downstream:** `manifest.py`'s `bbox_center_m` and grid record follow the new
   extents. The SVT static-centre rule is *easier* here, not harder — a full-domain
   axis is inherently static across the sequence.

None of this is started, and none of it blocks anything currently in flight: it is
owed **before C2 could ship as a scenario package**, not before T6. Sizing it properly
is its own task and needs a go.


---

## 5. H2 — the CIN knob, and what it is for

The knob exists (§3.1) and is deliberately **not** used in the T5s sweep: changing two
things at once would make the sweep unreadable. Its uses, in order of value:

1. **A clean single-cell control.** T5 §7.5 found the zero-CIN pulse cell rings up
   daughter convection after t=70 min, which is what broke the PC control's role. A
   capped variant is a one-block change to `t5probe_pc` and would give the classifier
   the "one bubble, one cell, then nothing" control it was designed against.
   ****RESOLVED 2026-09-02 (owner).** APPROVED, deferred — not today.**

   **Feasibility measured offline 2026-09-02, and this paragraph's own numbers were
   wrong.** A **1 km** mixed layer is NOT available at 14 g/kg — the generator refuses
   it (RH 1.002). And the obvious workaround is **backwards**: holding CAPE against a
   cooling cap makes the solver *raise* `qv_pbl`, which saturates harder still (RH
   1.091 at 1 km), so a 1 km layer needs a **lower CAPE target**, not lower moisture.
   The runnable envelope at `qv_pbl` 14 g/kg, with CAPE holding itself to within
   2 J/kg of the 1860 J/kg reference and no solver needed:

   | `z_cap_m` | Δθ = 2 K | 3 K | 4 K | 5 K | 6 K |
   |---|---|---|---|---|---|
   | 600 | −53 | −60 | −67 | −74 | −82 |
   | 700 | −49 | −56 | −63 | −70 | −78 |
   | 800 | −44 | −51 | −59 | −66 | −73 |
   | 900 | −39 | −46 | −53 | −60 | −68 |
   | 1000 | refused — saturated | | | | |

   (SB CIN in J/kg; uncapped reference is −48.) CIN **strengthens with Δθ and weakens
   with depth**, so the strongest suppression at fixed CAPE is the *shallowest* cap with
   the *largest* Δθ — the opposite of the "deeper mixed layer" intuition. Pick from
   this table when the run is scheduled; nothing else is owed first.
2. **The forecast → outcome panel.** Two scenarios with identical CAPE and shear and
   different CIN — one that initiates, one where the bubble fails to break the cap — is
   the charter's honest "why storms form" lesson made literal, and the generator holds
   CAPE across them by construction. A Phase 4 teaching scenario, not Phase 3.
3. **Mixed-layer depth as a knob** (McCaul & Cohen 2002's actual experiment) is exposed
   but constrained: at 14 g/kg a well-mixed layer deeper than ~0.9 km saturates, and the
   generator refuses it. Deeper mixed layers need lower moisture, i.e. a CAPE hold at a
   lower target. That interaction is real physics and the tool says so instead of
   clipping.

### 5.2 The capped single-cell control — PRE-REGISTERED 2026-09-04, before either member ran

Two members, run **concurrently at `-np 4` each** (the charter's concurrency note; all
six T5 probes ran this way, so wall clock is the ~13 min the owner priced, not 26).
`sim/probes/configs/t5s_capped_dt3.json` and `t5s_capped_dt6.json`. Both are
`t5s_neutral_pc` with a cap block added and **nothing else changed**: deck generation
produces a file **byte-identical** to `t5s_neutral_pc`'s (8173 bytes, verified by
`diff`), so `input_sounding_sha256` is the only difference between the runs. This is
what makes it a one-variable control.

**Bracket, not an optimum.** `z_cap_m = 600` is held (§5.1 measured depth as the
*weakening* knob) and Δθ is varied: 3 K (SB CIN −59.9) and 6 K (−81.6). §5.1's table
bottom-right is unusable — 900 m/2 K gives −39, **weaker than the uncapped −48
reference** — so nothing below about −53 suppresses more than doing nothing.

**Three things measured offline before any compute was spent**
(`sim/probes/bubble_feasibility.py`, tracked for the same reason the probe configs
are — it is what makes these numbers reproducible; its elevated-parcel routine is
gated to reproduce `sounding.parcel(kind="sb")` to 0.000e+00 before it is used for
anything):

1. **`z_blend_m = 500` is not a free choice.** §5.1's table records `z_cap_m` and
   `dtheta_k` only, and CIN depends on the blend depth. 500 m reproduces all twenty
   entries to max |err| **0.46 J/kg** (rounding); 400 m is off by 10.1 and 100 m by
   39.2. Without this the run would have been at a cap nobody could reproduce.
2. **CAPE holds by construction, and §5.1's own claim was slightly optimistic.**
   Measured SB CAPE 1858.4 (3 K) and 1855.9 (6 K) against the uncapped 1859.7 — so
   **3.8 J/kg**, not the "within 2 J/kg" §5.1 claims. `hold_cape_jkg` stays unset, per
   §5.1's measured finding that the solver's response is backwards.
3. **The "cap too strong to initiate" failure mode does not exist here, and the reason
   is structural.** §5.1's table is the CIN of an *unperturbed surface* parcel; what has
   to break the cap is a parcel carrying the warm bubble's θ excess. CM1's bubble
   (`iinit=1`, `init3d.F:456-479`) is centred at **z = 1400 m** with **`bptpert` = 1.0 K**
   — its warm core sits **above** a 600 m cap. On CM1's own scalar levels the bubble
   carries θ′ = 0.077 K at 250 m, 0.556 K at 750 m and 0.972 K at 1250 m, and the bubble
   parcel's CIN is **0.00 J/kg from 750 m or 1250 m in both members**, while the 250 m
   parcel still carries the full −60 / −82. So the cap acts on **surface-based
   (gust-front) parcels only** and leaves initiation alone — which is exactly the
   separation the control wants, and it means the live risk is entirely on the *too
   weak* side. Recorded now so a surviving storm is not later read as the cap having
   failed to bite.

**The two-sided criterion, direction-only, no new thresholds.** The comparison run is
**`t5s_neutral_pc`** (26 frames, on disk) — *not* `t5probe_pc` — because it is the same
`isnd=7` path, so the cap is the only variable.

- **Initiation.** The run produces deep moist convection: peak `w` ≥ 15 m/s and peak
  `dbz` ≥ 49 dBZ at some frame. Both numbers are **T5 §7.5's own** ("peak w 15–32 m/s and
  49–56 dBZ — that is convection, not speckle"), reused rather than invented. Note that
  the capped storm may be *stronger*, not weaker: the 750 m bubble parcel gains CAPE
  (2545 → 3226 J/kg at 6 K) because its source air sits inside the inversion. The
  criterion is therefore one-sided by design.
- **Singleness.** Fewer secondary convective entities than `t5s_neutral_pc` after
  **t = 70 min** (T5 §7.5's own onset time), ideally zero. **Sharpened 2026-09-04 while
  the two members were still running and before any of their output existed to read**,
  because the first wording ("strictly fewer … at every frame") had two readings and
  the literal one is unfair: if the uncapped run shows a single updraft in some frame,
  nothing but "no storm at all" can be strictly fewer *there*. The precise form, still
  direction-only and still with no new thresholds:
  - **Primary, on the named instrument.** Births after t = 70 min, `births_t5s.py`,
    counting **confirmed *plus* censored**: the capped member has **strictly fewer**
    than `t5s_neutral_pc`, ideally 0. The "plus censored" is §4.2's own lesson, and it
    was fixed by scoring the **uncapped reference alone** while both capped members
    were still integrating and had produced no output. That scoring is why it is not a
    free choice: `t5s_neutral_pc` returns **0 confirmed births and 8 censored**, every
    one of them at t = 110 min, `8.64` km from the nearest updraft, `18.08` m/s peak,
    `5.99` km² — **identical to the decimal**, which is T5 §7.3's axisymmetric
    gust-front ring resolved into eight lobes. Counting confirmed births only would
    have compared 0 against 0 and called a vacuum a pass, which is precisely the
    right-censoring trap §4.2 documented.
  - **Secondary, per frame.** The count of updraft components (`classify_t5.py`'s own
    definition — column-max `w` ≥ 10 m/s, area ≥ 4 km²) is **≤** the uncapped run's in
    **every** frame after t = 70 min, and strictly fewer in at least one. Reported as a
    paired per-frame sequence, not a summary statistic.

  Frame sets are aligned by construction (identical deck: `timax` 7200 s, `tapfrq`
  300 s → the same 26 frames), so the pairing is exact rather than interpolated.

**The instrument, and the honesty problem with using it.** Singleness is scored with
`sim/probes/births_t5s.py`, which §4.2 **retired for cause**. Using it here is stated in
those terms rather than quietly: §4.2 retired it as a *regime label* — it cannot
separate an axisymmetric ring from N discrete cells, and its control failed on exactly
that. It is **not** retired as a detector of *whether secondary convection exists at
all*, and "0 against the uncapped run's 4" is precisely the use the retirement did not
touch. The comparison is between two runs scored by the identical instrument, so a
shared bias cancels; only the difference is read.

**Explicitly forbidden**, because it is T5 §7.5's mistake verbatim: inventing a new
radial-symmetry or ring-detection metric *after* seeing the capped output. If the
existing instrument cannot separate the two runs, that is the result.

**The outcome branches, fixed now.**

| Outcome | Reading |
|---|---|
| Both members initiate and both suppress the ring | The control exists. §5.1 item 1 is delivered; the classifier gets the "one bubble, one cell" control it was designed against. Prefer the **3 K** member as the shipped control (weakest cap that works). |
| 3 K still rings, 6 K does not | Same, with the threshold bracketed between −60 and −82. Ship the 6 K member. |
| Both still ring | The cap does not suppress gust-front regeneration at this CAPE. A real negative finding about the pulse-cell control, **not** licence to strengthen the cap until something works — the envelope above −82 is not reachable at 14 g/kg (§5.1). |
| A member fails initiation | Contradicts finding 3 above, which is arithmetic on CM1's own source. That would mean the bubble parcel argument is wrong and the offline check is the thing to fix, not the cap. |

#### 5.2.1 AMENDMENT 2026-09-04 — the first execution was contaminated; the clean re-run is the run of record

**Written before any capped output had been scored.** No number from either
attempt existed when this was fixed.

**What happened.** The launcher was fired twice. WSL cold-boots in ~20 s; the
first launch was still starting when its run directory was checked for, absence
was read as "the launch did nothing", and a second launcher went out. Both
reached the box, so **each capped member ran as two concurrent CM1 jobs in one
persistent run directory**. `run_probe.sh` shares `RUNDIR` by probe name and
rewrites everything in it, so the two jobs interleaved one `cm1.out` on
independent file offsets and contended over the first output file — that is the
`netcdf status returned an error: 13 ... Permission denied` on
`cm1out_000001.nc` that appears in both capped logs and in **neither** the
uncapped reference (which ran alone) nor any earlier T5s probe.

Evidence preserved in `runs/t5s_capped_launch/incident_snapshot/`
(both raced `cm1.out`, both `PROBE_STATUS` including dt6's `PROBE_FAIL` before
the surviving job overwrote it, the launcher `RC`, and the process table).

**The ruling, and why it is written now rather than after scoring.** The raced
runs are **not** the run of record and cannot become it, whatever they say.
Both members are re-run cleanly, one launcher, and **the clean set is the only
data §5.2's criteria are applied to.** The raced output is moved aside and kept
for exactly one purpose: a **reproducibility check** — same config, same forked
binary, same `np=4` and same decomposition, which is the condition Phase 0
verified bitwise. Holding two datasets and scoring after the fact would hand
back the freedom to prefer the nicer one, which is the whole thing §5.2 exists
to close.

**What the check is expected to show, stated in advance.** The aborting job died
at 33 s having written no output file except the contended frame-1 attempt, and
both jobs' `rm -f cm1out*.nc` ran before either `mpirun` produced anything — so
no frame was deleted and frames 2 onward came from a single job. The scrambled
`cm1.out` is therefore expected to be the worst of the damage, and the clean and
raced frames are expected to **agree at data level**. That is the prediction, not
a reason to skip the test. The comparison is made on decoded variable arrays, not
with `cmp`: netCDF-4 files can differ byte-wise for benign reasons (creation
attributes, chunk layout, deflate nondeterminism).

**The one hazard that is physics rather than bookkeeping**, recorded so it is not
lost: the second job's `cp input_sounding` could have raced the first job's read
of it at initialisation, giving CM1 a silently truncated profile. Re-generating
the sounding and matching the recorded sha256 proves the file is right *now*, not
what CM1 read at 09:49:28. The clean-run data comparison covers this; if it does
not agree, this is the first thing to check.

**Harness defect, fixed in the same batch:** `run_probe.sh` now takes an
exclusive `flock` on `/home/boiko/thunderstorm/runs/.<name>.lock` for the life of
the script and refuses to start (`PROBE_LOCKED`, exit 3) if another invocation
holds it. "Be careful next time" is not a fix for a race whose trigger is a slow
cold start.

#### 5.2.2 AMENDMENT 2026-09-05 — two further interrupted attempts; only a completed run is data

**Written before any capped output existed to score**, for the same reason §5.2.1 was:
a ruling recorded after a number is visible is a choice, not a rule. Neither attempt
below produced a scorable frame set, and neither can become the run of record.

- **Attempt 2 (2026-09-04 10:29, the clean re-run §5.2.1 ordered).** Reached `mpirun`
  and integrated normally; it stopped at **frame 4 of 25** at 10:35 when the WSL VM was
  shut down (`journalctl --list-boots`: boot −1 ends 10:36:11). `cm1.out` carries no CM1
  error — the last line is a normal `cflmax` report at 15.7 min of storm time. Preserved
  at `runs/t5s_capped_clean.aborted-0904/`.
- **Attempt 3 (2026-09-05 22:49).** Both members failed **before** `mpirun`, so no frame
  of either exists. `gen_deck.py` wrote the deck to a `mktemp` path under `/tmp` and the
  file was gone ~10 s later at the `cp` that stages it into the run dir
  (`cp: cannot stat '/tmp/tmp.D0CWPlTljn'`), identically on both members; `run_probe.sh`
  exited 1 under `set -e`. `/tmp` is not durable on this box at present — every entry in
  it, including the systemd private directories, carried a timestamp minutes newer than
  the boot. Preserved at `runs/t5s_capped_clean.failed-tmpdir-0905/`.

**The fix, and what it deliberately does not touch.** The launcher exports
`TMPDIR=/home/boiko/thunderstorm/tmp` (ext4, under `$HOME`) before invoking
`run_probe.sh`. **`run_probe.sh` is not edited**: `mktemp` honours `TMPDIR`, so the
tracked script — and with it the provenance of every probe already run against it —
is unchanged. The launcher itself is a throwaway wrapper on `M:\claud_projects\temp`,
per the detached-launch pattern (a harness background task or a `wsl` session that can
close is what killed attempt 2's kind of run before).

**A correction this forced, recorded rather than quietly fixed.** §5.2 says the two
members and `t5s_neutral_pc` share "the same 26 frames". The reference on disk has
**25** (`cm1out_000001`…`000025`), and the deck says so: `timax 7200 / tapfrq 300` is
24 intervals plus the initial write. **25, not 26.** The pairing the secondary criterion
needs is still exact by construction — identical deck, identical output cadence — so
nothing in §5.2 changes except the count.

**Everything else in §5.2 and §5.2.1 stands**: the criteria are applied once, to a
*completed* clean set; the raced set remains a reproducibility check only; an
interrupted attempt is not a dataset and is not scored, in either direction.

---

## 6. Plan amendments (supersede the Phase 3 task table for T5/T6)

| Task | Was | Now |
|---|---|---|
| T5 | Multicell initiation design | **CLOSED as measured:** no multicell reachable from the namelist under two independent criterion-1 designs; classifier reach measured (`phase3-t5-multicell.md` §13.9). Not a failure of the task — the answer it produced is the reason T5s exists. |
| **T5s** (new) | — | External sounding path (§4): source read → two neutrality controls → discrete-propagation measurement validated on SC/PC → three-member shear sweep. **Needs owner go.** |
| T6 | Multicell run + export + diorama | Unchanged in content; the asset is T5s's confirmed multicell at 333 m (a `sim/scenarios/multicell_333m.json` with a `sim.sounding` block). The scenario manifest's provenance gains the sounding block and the file's sha256 — the same inline-provenance decision the owner has carried since Phase 2, now with a second input that needs recording. |
| T7 | Close-out | Unchanged, plus: settle fork neutrality generality (Phase 3 plan §6) and record the `base.F` line numbers from §4.0 in the patches README. |

**Phase 3T (terrain) — H5, prerequisites designed in now, not scheduled:** the
regridding module needs CM1's `zh`/`zf` on terrain-following levels *and* the terrain
height field in the output (`output_zs`-class flags — verify against the template's
`&param9` before the first terrain run, the same way `check_output_flags` protects
`dbz`); the export box gains a z-offset (the Cartesian box floor is the terrain
minimum, not 0), which touches `scenario.origin_m` — the one place the SVT
static-centre rule lives. `imove=1` and terrain are mutually exclusive (Phase 3 plan
§2.1), so `deck.py` should refuse `terrain_flag=true` with `imove=1` as a Category 3
rule *before* Phase 3T opens.

**Phase 4 (lightning) — H6, prerequisites:** McCaul et al. (2009) flash rate needs the
graupel mass flux at the −15 °C level and the updraft volume; both need temperature
(`output_th` + `output_prs`, or `output_t`) in the deck, and the NSSL scheme's separate
hail category (`qhl`) has to be assigned to "graupel" or excluded *by a cited choice*.
Add the flags to `REQUIRED_OUTPUT_FLAGS` when Phase 4 opens so a hero run cannot
finish without them. **H4** belongs here too: signed updraft helicity (∫ w·ζ dz over
2–5 km, Kain et al. 2008) computed in the pipeline from `w` and `vort` would give the
left mover its signal and is a web-only diagnostic field like `w` — a T8-shaped task.

---

## 7. Owner decisions — **ANSWERED 2026-09-02**

1. ~~**T5s go/no-go**~~ — **GO given, and T5s ran to completion.** Source read, two
   neutrality controls, three sweep members, all recorded (§§4.0–4.2,
   `sim/probes/README.md`).
2. ~~**Drop option (i)**~~ — **RESOLVED 2026-09-02 (owner).** **DROPPED.** The `0002-` shear
   patch is retired: no third binary hash, no new row in `sim/cm1-patches/README.md`,
   and the charter's CM1 pin stays where T4 left it (`5fc93016…`). Its premise — "only
   a source edit can reach the 10–31.8 m/s gap" — was measured false by §4.1, and the
   sweep then ran *inside* that gap on the unchanged binary. **The project's fork count
   stays at one.** Nothing further is owed to this option; it is not "kept priced".
3. **Capped single-cell control** (§5.1) — **RESOLVED 2026-09-02 (owner).** **APPROVED, deferred
   — not today.** 13 min when scheduled. Feasibility settled offline so the run cannot
   fail on a `SoundingError` (see §5.1's amended note).
4. **Squall line (C2) as a wanted scenario** — **RESOLVED 2026-09-02 (owner): KEEP.** It does **not** retire
   with T5s. T5 §11.7's box hazard is therefore live work, and scoping it found the
   note understated it — see §4.4.
5. **500 m re-run of `t5s_us15`** (§4.2's contingency, ~2 h) — **RESOLVED 2026-09-02 (owner).**
   **APPROVED, deferred — not today.** The three outcome branches are already fixed in
   §4.2 and must not be renegotiated when it runs.
6. Carried, unchanged: UE SVT visual streaming sign-off; diorama 5c pan gestures; VHDX
   resize number; manifest inline provenance (now with `input_sounding` as a second
   input to record).

---

## 8. Structural changes made alongside (why they belong in the same commit)

The blocker in H1 was a *reading* failure: an option the record never considered, in a
file whose status section had grown to 686 lines and 60 KB (78 % of the charter). A
charter that long is not read; it is searched, and a search for "shear" finds T5's
conclusion, not CM1's option list. So:

- **`CLAUDE.md` is a charter again** (239 lines): principles, architecture, decisions,
  environment, layout, conventions, pins, a one-line-per-phase table and the open owner
  calls. The status log moved to **`docs/STATUS.md` verbatim** (gated by the move script:
  the old block is a substring of the new file), where new task records are appended.
- **`docs/README.md`** indexes every document by kind and collects the standing method
  rules with the task that taught each.
- **`README.md`** no longer says "pre-implementation" (it did, three phases in) and
  describes the pipeline and players as they are.
- The deck/template/probe/pipeline READMEs describe Category 6 and the `t5s_*` configs.

Everything above is reversible with `git revert` of one commit; nothing touches a
shipped package, a manifest, or a pinned hash.

---

## References

- Weisman, M. L., and J. B. Klemp, 1982: The dependence of numerically simulated
  convective storms on vertical wind shear and buoyancy. *MWR*, **110**, 504–520.
- Weisman, M. L., and J. B. Klemp, 1984: The structure and classification of numerically
  simulated convective storms in directionally varying wind shears. *MWR*, **112**,
  2479–2498.
- Rotunno, R., J. B. Klemp, and M. L. Weisman, 1988: A theory for strong, long-lived
  squall lines. *JAS*, **45**, 463–485.
- Bolton, D., 1980: The computation of equivalent potential temperature. *MWR*, **108**,
  1046–1053.
- Doswell, C. A., and E. N. Rasmussen, 1994: The effect of neglecting the virtual
  temperature correction on CAPE calculations. *WAF*, **9**, 625–629.
- McCaul, E. W., and M. L. Weisman, 2001: The sensitivity of simulated supercell
  structure and intensity to variations in the shapes of environmental buoyancy and
  shear profiles. *MWR*, **129**, 664–687.
- McCaul, E. W., and C. Cohen, 2002: The impact on simulated storm structure and
  intensity of variations in the mixed layer and moist layer depths. *MWR*, **130**,
  1722–1748.
- Moncrieff, M. W., and J. S. A. Green, 1972: The propagation and transfer properties of
  steady convective overturning in shear. *QJRMS*, **98**, 336–352.
- Kain, J. S., et al., 2008: Some practical considerations regarding horizontal
  resolution in the first generation of operational convection-allowing NWP. *WAF*,
  **23**, 931–952 (updraft helicity).
- McCaul, E. W., S. J. Goodman, K. M. LaCasse, and D. J. Cecil, 2009: Forecasting
  lightning threat using cloud-resolving model simulations. *WAF*, **24**, 709–729.
- Bryan, G. H., CM1 release cm1r21.1: `README.namelist` (`isnd`, `iwnd`, `input_sounding`)
  — **to be confirmed against `base.F` on the box (§4.0).**
