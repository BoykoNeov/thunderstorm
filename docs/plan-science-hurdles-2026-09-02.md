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
all INDETERMINATE. **[CORRECTED 2026-09-06, §4.2a: only `E` carried multicell-side weight through the rule -- `organised` is an OR of `R >= 0.60` and `E >= 2.40`, and `R` = 0.364 sits BELOW its floor, contributing nothing. Both statistics are outside their bands; one of them is evidence.]** **The structural transition lands between U_s 15 and 20 -- exactly
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

### 4.2a The 500 m re-run — PRE-REGISTERED 2026-09-06, WHILE THE RUN WAS IN FLIGHT AND BEFORE ANY OF ITS FIELDS WERE OPENED

The run was launched at 06:22 on 2026-09-06 and this subsection was written before its
first frame was read. It exists because §4.2's three branches, as written, have a hole
big enough to swallow the result, and because the two words "stays high" in branch (i)
have no number attached to them.

**The configuration, and why the diff is the whole argument.** `t5s_us15_500m.json`
doubles `nx`/`ny` and halves `dx`/`dy` **exactly** — 360 × 499.5 m = 179 820 m =
180 × 999 m — and touches nothing else. The generated deck differs from `t5s_us15`'s in
**six lines**: `nx`, `ny`, `dx`, `dy`, and the two geometry-derived `dx_inner`/`dy_inner`.
`tot_x_len`/`tot_y_len` are identical. `nz`, `dz`, `timax`, `tapfrq`, `dtl`, `adapt_dt`,
`imove`, `umove`, `irandp`, `iinit`, `iorigin`, `icor`, `ptype`, `ihail` and the entire
sounding block are unchanged. **Measured before launch, not asserted:** the generated
`input_sounding` has sha256 `3761542a…`, which is byte-for-byte the value in
`t5s_us15`'s own `run_meta.txt`. So "only resolution moved" is a *measurement*. `dtl`
stays 6.0 on purpose: at 1 km, `adapt_dt=1` raised dt to 6.6 then 7.26 at the first two
adaptations with `cflmax` near 0.06, so `dtl` is a seed value the solver immediately
leaves behind, and halving it would have moved a second variable for no effect.
`np=8` rather than the sweep's `np=4` because this is one run and not a concurrent
pair (charter, production run config).

**Order of reading, fixed: containment first.** `drift_fit`'s 15 km void rule is
evaluated before `P1` or `E` is looked at, exactly as `score_t5s.py` did for the sweep.
The 1 km members' 60–71 km clearance is **not inherited**: measured drift ran 7–14 %
below declared `umove` on all three, and a better-resolved storm may propagate
differently. A void member is not scorable at any label and branch selection does not
happen.

#### The hole in branch (i), and the instrument that closes it

Branch (i) reads a broken `P1` as *the rotation stopped persisting*. But `P1` is a
chain-linking statistic over `uh` components that have first been filtered by
`UH_MIN_AREA_KM2`, and **halving the grid spacing can break that chain with no physical
change at all**: one blob that cleared the area floor at 1 km can appear at 500 m as
several pieces that individually do not. That is this project's own twice-recorded
lesson — *component counting measures fragmentation, not quantity* (T5 §13; T5s §5.6,
where it inverted outright: fewer components, four times the convection) — arriving in
a third place. Left unaddressed, a broken `P1` would be read as physics when it may be
arithmetic.

**The fix is a different reduction, not a moved threshold** — the §5.6 move. Because
499.5 = 999/2 **exactly**, every 1 km cell is exactly four 500 m cells, so the 500 m
fields can be block-reduced onto the 1 km grid and the **unchanged** classifier run on
the result. Pre-registered now:

- **Primary reduction: block-MEAN** over 2×2 cells. It is the honest analogue of what a
  coarse grid can represent — a 1 km cell cannot hold the gaps between fragments — and
  it is the *conservative* direction, since averaging lowers peaks. A chain that
  survives block-mean coarsening is a strong reading.
- **Sensitivity: block-MAX**, reported beside it as the lenient bound. **If mean and max
  disagree, that is reported as an indeterminate coarsening test and neither is
  chosen.** Picking the one that gives a cleaner answer is exactly the move this
  document exists to prevent.
- The coarsened field is an *approximation* to what CM1 would have computed at 1 km, not
  a reconstruction of it. Nothing here claims otherwise; the test is a direction test.

**Decision rule, written before the numbers exist:**

| raw 500 m `P1` | coarsened `P1` | reading |
|---|---|---|
| breaks (< 80) | still 80 | **the break is fragmentation, not physics.** Branch (i) does NOT fire; `us15` is not labelled MULTICELL on it. |
| breaks (< 80) | also breaks | the break survives the confound → **branch (i) or (ii) as §4.2 wrote them**, decided by `E` below. |
| 80 (ceiling) | 80 | **branch (iii)**: the ceiling is structural, H3 needs a criterion this project does not have. Coarsening is still run, as an instrument gate. |

**Instrument gates, run before any verdict is read** (the §5.5 pattern — the instrument
proves itself on data whose answer is already known):

1. The coarsened grid's `xh`/`yh` must equal the 1 km run's to floating point.
2. Applying the same code path to the 1 km run with a 1×1 block must be the identity —
   bitwise.
3. Whole-domain integrals of the reduced field must equal the 500 m whole-domain
   integrals (block-mean conserves the sum by construction; a non-zero residual means
   the reduction is wrong, not that the physics moved).

**Supporting reading, not a criterion:** per-frame `uh` component areas with any frame
within 2× of `UH_MIN_AREA_KM2` flagged. If the chain break lands on a near-floor frame,
that is the tell, independent of the coarsening test.

#### "E stays high" gets its number now

§4.2's branches say "stays high" and "collapses" with no bar, which is a post-hoc
negotiation waiting to happen. The bars are **already pre-registered elsewhere and are
not new**: criterion 2′'s decisive edges, `E ≥ 2.40` **and** `R ≤ 0.40` (T5 §8,
unchanged). So:

- **"E stays high"** = `E ≥ 2.40` **with** `R ≤ 0.40` — the same decisive-on-both-sides
  reading that made `us15` the only decisive member of the 1 km sweep.
- **"E collapses"** = `E` falls below 2.40, or `R` rises above 0.40, or both. Inside the
  band on either statistic is **not** "stays high".

#### The escalation, named so it is not discovered late

If branch (i) fires, the label rests on "`P1` breaks at 500 m", and the immediate and
correct question is whether `P1` breaks at 500 m for a *known* supercell too. The
coarsening test above is the cheap first answer. If it comes back indeterminate, the
escalation is a **500 m `t5s_us20`** — named here as the path, **not run**: the owner's
go covers one run.

#### RESULT 2026-09-06 — **BRANCH (iii) FIRED. No multicell label; the ceiling is structural, and the elongation was not.**

The run completed (`PROBE_OK`, 25 frames) and the reading was taken in the order this
subsection fixed: containment, then the instrument gates, then the verdict. Nothing was
renegotiated and no threshold moved.

**Containment, read first and measured on this run, not inherited.** `t5s_us15_500m`
clears the open wall by **67.93 km** (echo cells) and **63.44 km** (updraft) against the
15 km floor — contained, and therefore scorable. The 1 km member re-measured alongside
it at 69.93 / 70.93 km.

**Instrument gates, all three PASS.** G2 (block size 1 on the 1 km reference is the
identity) — 25 frames, **0 metric differences**, run before the 500 m data existed. G1
(reduced grid equals the 1 km grid) — max |dx| and |dy| **7.629e-06 km**, both
reductions. G3 (block² × reduced sum equals the 500 m sum) — worst relative residual
**9.367e-15**, on `thpert`.

| run | label | `P1` | `R` | `E` | span |
|---|---|---|---|---|---|
| `t5s_us15` (1 km reference) | SUPERCELL | 80 | 0.364 | 2.721 | 80.0 |
| `t5s_us15_500m` | SUPERCELL | **80** | 0.247 | **1.813** | 80.0 |
| `t5s_us15_500m_coarse_mean` | SUPERCELL | 80 | 0.197 | 1.730 | 80.0 |
| `t5s_us15_500m_coarse_extremum` | SUPERCELL | 80 | 0.257 | 1.770 | 80.0 |

**The decision table's third row fired: raw `P1` = 80 → branch (iii).** §4.2 wrote branch
(iii) as *"`P1` still reads 80 (the ceiling is structural and H3 needs a criterion this
project does not have)"*, and that is what happened, without hedging. Doubling the
resolution did not break the ceiling and did not produce a multicell. **The confound this
subsection's instrument was built for never arose** — `P1` did not break at 500 m at all,
so there was no chain break to attribute to fragmentation. The coarsened runs read 80 as
well, which closes the other direction too: the ceiling is not an artifact of the
measurement grid in either direction. §4.2's own contingency is now **spent**, and it
returned a negative.

**A correction to §4.2's wording, made here rather than left standing.** §4.2 records
that criterion 2′ "puts `us15` decisively on the multicell side **on both statistics**".
That is loose, and the code is the authority: `organised = (R ≥ 0.60) or (E ≥ 2.40)`
(`classify_v2` ~line 844, `classify_v3` ~line 923 — identical), and `organised` is what
gates MULTICELL. `R = 0.364` sits *below* its floor and contributes **nothing** to
`organised`. Both statistics are decisive in the sense of sitting outside their §8.6
bands, but **only `E` carried multicell-side weight through the rule.** `us15`'s
multicell-side evidence at 1 km was one statistic, not two.

**So "E stays high" is FALSE, by the number fixed above before the run was read.**
`E = 1.813` is below 2.40 and inside the 1.667–2.40 band, which is §8.6's INDETERMINATE
zone. **The single statistic that put `us15` on the multicell side at 1 km does not clear
its floor at 500 m.**

**And the drop is in the flow, not in the measurement — which the instrument answers by
accident.** This is stated plainly because it is *not* what `coarsen_test.py` was
pre-registered for: it exists for the `P1` fragmentation confound, which never fired.
Used on `E` and `R` instead, it says something the raw comparison cannot. Block-reduced
onto the *exact* 1 km grid and read by the *unchanged* classifier, the 500 m storm gives
`E` = 1.730 (mean) and 1.770 (extremum) — beside the raw 500 m 1.813, and nowhere near
the 1 km run's 2.721. Same for `R`: 0.197 / 0.257 coarsened, 0.247 raw, against 0.364 at
1 km. **Coarsening does not restore the 1 km values.** The two reductions agree in every
case, so the test is not indeterminate. A better-resolved storm in this environment is
genuinely less elongated and less coherent; the 1 km elongation was a property of the
1 km *simulation*, not of the 1 km *measurement*.

**The descriptors do not move together under refinement, and that matters.** The 1 km
sweep trends were `R` 0.364 → 0.526 → 0.560 (rising with shear) and `E` 2.721 → 1.948 →
1.546 (falling). Refining `us15` moves **both down**: `R` to 0.247, *further* from
`us20`/`us25`, so that separation **strengthens**; `E` to 1.813, into the *middle* of the
1 km trend between `us20`'s 1.948 and `us25`'s 1.546, so that separation **weakens**. Any
reading that treats the descriptor family as one coherent signal is not supported.

**A bound on the resolution confound, not a measurement of it.** Refining one member
moved `E` by **0.908**, larger than the `us15` → `us20` shear step of **0.773**. That
**bounds** the confound on the `E` trend — a resolution change on a single member exceeds
the shear step between members — and it is **not** a finding that the `E` trend is an
artifact, because **only one member was refined**. The measurement that would settle it
is a 500 m `t5s_us20`, which §4.2a named as the escalation and which is **NOT RUN**: the
owner's go covered one run.

**What survives §4.2 and what does not.** The structural-transition-between-15-and-20
claim does **not** rest on `E` alone: the split test (§4.2, a classifier-free measurement
of mirrored two-component echoes) is untouched by this run, and `R`'s separation gets
*stronger* under refinement. That claim stands. What does **not** survive is any reading
in which `us15`'s `E ≥ 2.40` at 1 km is resolution-robust evidence of a line-like regime.
It is not.

**H3 confirmed a third time.** Criterion 1′ sat at its ceiling for every sheared storm at
1 km; it sits there at 500 m too, and it sits there for the same storm measured on two
different grids by two different reductions. This project still has no criterion that
separates a multicell from a supercell, and resolution is now measured — not assumed — to
be the wrong lever for building one.

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

### 5.3 The capped control RAN — and the reading of it is pre-registered here, before the discriminating test

**Scored once, on the completed clean set** (both members `PROBE_OK`, 25 frames each,
`runs/t5s_capped_clean/SCORE.txt`). §5.2's verdicts, verbatim and not revisited:

| member | initiation | singleness, primary (births after 70 min) | singleness, secondary (per-frame) |
|---|---|---|---|
| `t5s_capped_dt3` (CIN −60) | **PASS** (peak w 63.1 m/s, cref 65.3 dBZ) | **PASS** — 4 (4 confirmed + 0 censored) vs uncapped 8 (0+8) | **FAIL** |
| `t5s_capped_dt6` (CIN −82) | **PASS** (peak w 59.9 m/s, cref 64.2 dBZ) | **FAIL** — 28 (8+20) vs 8 (0+8) | **FAIL** |

Per-frame updraft components after t = 70 min (capped / uncapped):

- `dt3`  75:1/4 80:1/8 85:1/8 90:8/4 95:8/8 100:8/4 105:12/1 110:4/4 115:4/4 120:8/8
- `dt6`  75:20/4 80:16/8 85:8/8 90:20/4 95:48/8 100:56/4 105:32/1 110:12/4 115:20/4 120:28/8

**The signature that has to be tested before any of this is interpreted.** Thirty of
those counts are divisible by 4 (the exceptions are two isolated 1s). This configuration
is **axisymmetric by construction** — zero shear, a centred bubble, a square domain — and
§5.2 already diagnosed exactly this for the reference: its 8 births were one gust-front
ring resolved into eight lobes, "8.64 km from the nearest updraft, 18.08 m/s peak,
5.99 km², identical to the decimal". If the capped members' components are arcs of one
expanding ring, then `n_updrafts` is measuring a cold pool's circumference, not a number
of cells — and §5.2's secondary criterion, which compares those counts frame by frame,
is measuring the same thing. dt6's 56 would then be a *bigger* cold pool, which §5.2
predicted in advance ("the capped storm may be stronger, not weaker": the 750 m bubble
parcel gains CAPE 2545 → 3226 J/kg at 6 K).

**The test, with its readings fixed before it runs.** For `t5s_neutral_pc` at t = 120
(8 components), `dt3` at t = 105 (12) and `dt6` at t = 95 (48), list every updraft
component's centroid distance from the domain centre, its area, and its peak
column-max `w`, using `classify_t5.py`'s own definitions (column-max `w` ≥ its
`W_UPDRAFT`, ≥ 4 km², 8-connectivity) and nothing new.

- **RING** — at least **75 % of a frame's components have a centroid radius within
  ±10 % of the median radius** of that frame. One expanding annulus, chopped into arcs.
- **CELLS** — fewer than 75 % do. Objects at genuinely different distances from the
  ignition point, which one ring cannot produce.
- **MIXED** — a ring plus outliers. Then the ring members and the residual are reported
  **separately**, and the residual count is the one the criterion should have used —
  computed by this ±10 % rule, never by picking.

**What each outcome means, decided now.**

- **RING ⇒ §5.2's secondary criterion is VOID on an axisymmetric configuration.** It
  counts arcs, not cells, for capped and uncapped alike. The control is **not
  delivered**, and the reason is the *instrument*, not the cap. The design consequence:
  a clean single-cell control needs either symmetry breaking (shear, or seeded
  perturbations) or an instrument that does not count arcs — the cap is not what needs
  fixing first, and no third capped member should be run until one of those exists.
- **CELLS ⇒ the numbers mean what they say.** The cap did not suppress secondary
  convection; at −82 J/kg it made it markedly worse, and §5.2's own reasoning says where
  to look (the cap acts on surface-based parcels only, while the bubble parcel above it
  gains buoyancy — a stronger storm, a stronger cold pool, more gust-front triggering).
  The capped-mixed-layer knob then fails as a single-cell control **at this CAPE with no
  shear**, which is a physics result about the design, not about the code.
- **MIXED ⇒ both are reported**, and the criterion is re-read on the residual only.

**One thing the ring cannot explain either way, and it is reported as weak.** `dt3`'s
first three frames after the window opens are 1, 1, 1 against the reference's 4, 8, 8,
and its births are 4 confirmed + 0 censored where the reference is 0 + 8 — a different
*composition*, not just a different count. That is weak evidence the cap did bite early
and was then overrun. It is recorded as weak and is not promoted to a finding.

**Logged, cannot move the verdict.** All three peak `w` values sit at the undiluted
parcel ceiling (√(2·1858) = 61.0 m/s vs 61.55 / 63.14 / 59.92 measured) — higher than
unsheared cells usually reach. Worth one look at which level the maximum sits on (a
spike at or above the `zd` = 15 km damping layer would explain it). Initiation is
one-sided and `cref` clears its floor independently, so this cannot change a PASS.

### 5.4 RESULT — the control is NOT delivered, and the blocker is the instrument plus the symmetry

Two findings, deliberately kept apart, because one of them is a judgement made after
seeing the data and must be legible as one.

**(a) §5.3's test yields NO verdict: its positive control failed.** By the letter of
the rule, all three frames read `CELLS` — including `t5s_neutral_pc`, the frame this
document had *already* established is one gust-front ring in eight lobes (§5.2: eight
births at 8.64 km, 18.08 m/s, 5.99 km², "identical to the decimal"). A test that
mislabels its own known positive control says nothing about the two unknowns. The
defect is in the rule, not the data: §5.3 assumed a **circular** annulus and tested
radius clustering, and the ring here is **square-ish** — axis lobes at 6.83 km,
diagonal lobes at 8.95 km, a ratio of 1.31 where a circle gives 1.00 and a square
1.414. Two orbits of one ring, which a ±10 % radius band cannot hold. This is the
fourth entry in this project's run of control-design failures and it belongs beside
the others: *a control that cannot fail proves nothing, and a control that fails when
it should pass invalidates the test rather than the subject.*

**(b) §5.2's secondary criterion is void anyway — on evidence that does not route
through §5.3. Flagged: this reading was reached after the numbers were seen.** The
configuration is *exactly* symmetric — `irandp=0` (no perturbation at all in the T5s
probes), a bubble on the domain centre, a square domain — so CM1 evolves the field
under exact four-fold symmetry and every feature appears as **4 copies** (on an axis or
a diagonal) or **8** (generic). The output confirms it to the decimal:

| frame | components | the orbits |
|---|---|---|
| `t5s_neutral_pc` t=120 | 8 | 4 at r=6.83 km, each 5.99 km², each peak w 22.09 m/s · 4 at r=8.95, each 23.95 km², each 26.64 m/s |
| `t5s_capped_dt3` t=105 | 12 | 4 at r=5.89 (5.99 km², 11.69 m/s) · 4 at r=6.99 (11.98, 18.90) · 4 at r=11.75 (10.98, 24.82) |
| `t5s_capped_dt6` t=95 | 48 | groups of 4 and 8, e.g. **8** at r=25.14 all 5.99 km² / 16.90 m/s, **8** at r=88.53 all 4.99 km² / 23.44 m/s |

Eight independent cells cannot agree to two decimals on **both** area and peak updraft.
`n_updrafts` is counting symmetry copies. Capped and uncapped runs are both
copy-inflated, but the factor is **per feature** (4 on an axis or diagonal, 8 generic),
so the frame-by-frame comparison is not even inflated by a common factor — it is not
stable in kind. **Void.**

**Not promoted, deliberately:** counting *orbits* instead is not the fix. The
reference's single ring yields **two** orbits (axes and diagonals), so orbit-counting
over-counts a non-circular ring exactly as component-counting does, one level up —
the project's own "component counting cannot tell N cells from one ring in N lobes"
lesson repeating. The only defensible statement is bounded: **distinct features ≤
count / 4**, and that is an upper bound, not an estimate.

**(c) A second, independent reason the late `dt6` frames are not a clean interior
count:** components at r = 81.41, 88.53 and 103.36 km on a domain of half-width
89.4 km. The disturbance is at and past the open boundary, whatever instrument reads it.

**What the control delivered, stated without rescue.**

- **Initiation: PASS for both members.** That criterion is sound and one-sided.
- **Primary singleness: exactly as scored** — `dt3` 4 vs 8 PASS, `dt6` 28 vs 8 FAIL.
  Births inherit the same copy inflation, so the part that carries information is the
  **composition**: `dt3` is 4 confirmed + 0 censored where the reference is 0 + 8.
  That remains **weak evidence** that the cap bit early and was then overrun. It is
  **not** promoted to a finding.
- **Secondary singleness: void** — (b).

⇒ **The capped single-cell control is NOT delivered.** The blocker is the instrument
plus the configuration's symmetry, **not the cap**. Nothing measured here says the CIN
knob failed; it says this experiment cannot see whether it worked.

**Owed before any third capped member** — this is §5.3's pre-registered RING
consequence, unchanged by the route taken to it: either **break the symmetry** (the T4
`var7` seed hook, or shear) **or build an instrument that does not count copies**.
**No third capped member runs until one of those exists.** Running one now would buy
another set of copy-inflated counts.

**The §5.2.1 reproducibility check: PASSES, exactly as predicted.** For each member,
**24 of 25 frames compare bitwise identical on every shared variable**; the one
exclusion is the raced copy of `cm1out_000001.nc`, unreadable (HDF error) — the file
the two jobs contended over, named in advance on 2026-09-04. `compare_raced.py` now
**reports** an unreadable frame and keeps it in the denominator instead of crashing on
it; a known casualty must not become an invisible one. This closes the one hazard in
the race that was physics rather than bookkeeping: had the second job's
`cp input_sounding` raced the first job's read at initialisation, the fields would
differ. They do not.

**Logged closed (non-blocking).** Peak `w` sits at the undiluted parcel ceiling in all
three runs — 61.55 / 63.14 / 59.92 m/s against √(2·1858) = 61.0 — at z = 11.25 /
11.25 / 12.75 km, all at t = 25 min. That is well below the `zd` = 15 km damping
layer, so it is **not** a damping artifact. Initiation is one-sided and `cref` clears
its floor independently, so it cannot move a verdict either way.

**Artefacts.** `runs/t5s_capped_clean/SCORE.txt`, `RING_TEST.txt`, `RACED_CHECK.txt`;
instrument `sim/probes/ring_test.py` (tracked, so the arrangement measurement is
reproducible); the interrupted attempts at `runs/t5s_capped_clean.aborted-0904/` and
`runs/t5s_capped_clean.failed-tmpdir-0905/`.

---

### 5.5 The copy-blind instrument — PRE-REGISTERED 2026-09-06, before it was written or run

**Disclosure, first, because it is the thing that most weakens what follows.** This
instrument is designed *after* §5.3's per-frame counts were read (dt3 1/1/1/8/8/8/12/4/4/8,
dt6 20/16/8/20/48/56/32/12/20/28) and after §5.4 diagnosed why they are void. The design
therefore knows the shape of the answer it is looking for. The mitigation is the one
§5.4(b) already used on itself: the criterion and **both** of its outcomes are written
here and committed **before** the script exists, and the outcome that reflects badly on
the cap is written first.

**Why not the two obvious routes.**

- **A better ring-vs-cells classifier is blocked for want of a negative control.**
  §5.3's rule failed because it assumed a circular annulus; a shape-agnostic replacement
  (does the updraft set form a closed circuit around the ignition point?) would pass the
  RING side on `t5s_neutral_pc`. But **there is no frame on disk that must read CELLS.**
  An axisymmetric configuration cannot produce genuinely distinct cells — the physical
  truth there is always a ring — so such a classifier could only ever be exercised on the
  side it is guaranteed to pass. That is this project's *control that cannot fail* mode,
  hit twice already. **Not built.**
- **Breaking the symmetry costs three members, not one.** `irandp=1` with a `var7` seed
  would destroy §5.2's one-variable design: `input_sounding_sha256` stops being the only
  difference from the on-disk uncapped reference, so a new uncapped reference at the same
  seed is owed too. And it does not fix the instrument anyway — a lumpy ring is still a
  ring, and component counting still counts arcs of it. Priced at **3 members** if the
  owner ever wants it; not proposed here.

**The principle this instrument rests on.** §5.4(b)'s defect is a property of *object
counts*: the copy factor is 4 for a feature on an axis or diagonal and 8 for a generic
one, so it is "not even inflated by a common factor". A whole-domain **integral** of any
field has no such problem — under exact four-fold symmetry it is exactly 4× the
one-quadrant integral, whatever the features are or where they sit. The factor is a
uniform 4 in the capped and uncapped runs alike, so a **direction-only comparison of
integrated quantities is valid under the symmetry, on the data already on disk, with no
new compute.** That is what the pre-registered gate asked for: *an instrument that does
not count copies*.

**The precondition, measured 2026-09-06 before the criterion was written.** Exact
quadrant tiling is not automatic — with `nx = ny = 180` (even) it requires the domain
centre to fall *between* cells, not on one. Measured on all three runs: `xh`/`yh` span
[−89.4105, +89.4105] km at `dx` = 0.999001 km, the centre is 0.000000, the nearest cell
centre is **0.5000 cells** away on both axes, and the coordinate mirror residual
(`(x−c) + reverse(x−c)`) is **0.000e+00** exactly. The four quadrants tile with no shared
centre row or column.

**What is measured.** The object set is `classify_t5.py`'s own, imported and not
restated — column-max `w` ≥ `W_UPDRAFT` (10 m/s), 8-connectivity, per-component floor
`W_MIN_AREA_KM2` (4 km²) — i.e. exactly the objects §5.2's criterion counted. Only the
**reduction** changes, from a count to two integrals over that mask:

- **`A`** — total updraft area, km².
- **`F`** — the same area weighted by column-max `w`, m s⁻¹ km². Extent alone could hide
  an intensity change.

**The primary/secondary split needs no radius threshold.** The confound §5.2 flagged is
real — the cap is expected to make the *primary* storm stronger (the 750 m bubble parcel
gains CAPE 2545 → 3226 J/kg at 6 K), so a whole-domain total would confound "more primary"
with "more secondary". The split used here is topological, not metric: **the primary is
the updraft component connected to the domain centre** (the bubble is centred and, with
zero shear, does not translate); **secondary is every component that is not.** No radius
is chosen, so no radius can be tuned. Where no component reaches the centre, the primary
is empty and every component is secondary — reported, not patched.

Because that split could in principle be unstable (a ring that touches the centre in one
frame and not the next would move a large area between the two categories), the
**split-free totals are reported alongside** and the verdict must survive both.

**The headline reading, fixed now.** Over §5.2's own window — frames at **t = 75, 80, …,
120 min** (`T_SECONDARY_MIN` = 70 unchanged, 10 frames) — form the time-integrated
secondary totals and take the ratio to the uncapped reference:

  `R_A = ΣA_secondary(capped) / ΣA_secondary(t5s_neutral_pc)`, and `R_F` likewise.

Direction only; no new physical threshold; both members scored the same way. The per-frame
table and the **full radial profile** (updraft area in 5 km annuli from the centre out to
the corner) are reported unreduced beside the ratio, so the reader can see where §5.4(c)'s
boundary contamination begins — the inscribed radius is 89.41 km and dt6 had components at
81.41, 88.53 and 103.36 km.

**The three outcomes, decided now.**

- **`R_A` > 1 and `R_F` > 1 ⇒ the cap did NOT suppress secondary convection; it increased
  it.** The capped-mixed-layer knob then **fails as a single-cell control at this CAPE with
  zero shear** — a physics result about the *design*, not about the code, and exactly the
  reading §5.3 already pre-registered under its CELLS branch (the cap acts on surface-based
  parcels only, while the bubble parcel above it gains buoyancy: a stronger storm, a
  stronger cold pool, more gust-front triggering). This outcome **delivers the control** —
  as a negative result. It does not send the CIN knob back for repair; it says this
  configuration is the wrong vehicle for it.
- **`R_A` < 1 and `R_F` < 1 ⇒ the cap suppressed secondary convection** in that member,
  and §5.2's singleness criterion is answered in the direction it hoped for, on an
  instrument that does not count copies.
- **`R_A` and `R_F` disagree, or the split-free totals contradict the split ones ⇒
  AMBIGUOUS.** Reported as ambiguous with all four numbers; nothing is picked. An
  ambiguous outcome does **not** authorise a third capped member — the §5.4 gate stands
  until something new is on disk.

**Gates the instrument must pass before any of its numbers are read** (all three are
checks on the *instrument*, and any failure voids the run rather than the cap):

1. **Symmetry is exact, measured not assumed.** The mirror residual of `winterp` under
   x-flip, y-flip and transpose is reported per frame. If the field is only approximately
   symmetric the integrals are still valid (the factor is still uniform), but the "counts
   are copies" diagnosis of §5.4(b) is quantified rather than argued.
2. **Quadrant identity.** One-quadrant integral × 4 must equal the whole-domain integral
   to floating-point round-off. This is the copy-stability claim itself, tested directly.
3. **Same objects as §5.2.** At the three frames §5.3 named, the instrument's total area
   must equal the sum of `ring_test.py`'s component areas. If it does not, it is not
   measuring the objects the criterion counted.

**What this instrument does NOT do**, stated so it cannot be over-read later: it does not
classify ring versus cells, it does not count distinct features (§5.4's bound *distinct
features ≤ count / 4* stands untouched), and it delivers no multicell label. It answers
one question — *did the cap increase or decrease the amount of secondary convection* — and
that is the only question §5.2 needed answered.

---

### 5.6 RESULT — the cap did NOT suppress secondary convection; it increased it, monotonically

`sim/probes/integral_test.py` (tracked), output `runs/t5s_capped_clean/INTEGRAL_TEST.txt`.
Run once, on the three runs already on disk, no new compute. §5.5's outcomes were fixed
and committed (f913be4) before the script existed.

**All three instrument gates pass, with exact zeros.**

1. **Symmetry is exact, not approximate.** `max |w − mirror(w)|` over every frame of
   every run is **0.000e+00** under x-flip, y-flip *and* transpose (peak |w| 59.9–63.1 m/s).
   §5.4(b)'s "every feature appears as 4 or 8 copies" is no longer an inference from
   coincidental areas — the field is bitwise invariant under the symmetry group.
2. **Quadrant identity holds to the bit.** whole-domain integral − 4 × one-quadrant
   integral is **0.000e+00** for both area and flux, every frame, every run. The
   copy-stability of the reduction is measured, not argued.
3. **The objects are §5.2's own.** At §5.3's three named frames the instrument's total
   area equals the sum of `ring_test.py`'s component areas exactly: 119.76 km² (8 comps),
   115.77 (12), 431.14 (48). **Recorded weaker than it looks:** `integral_test.py`
   imports `ring_test.components()`, and both build the mask from the same
   `classify_t5` constants with the same connectivity, so exact agreement is close to
   arithmetically forced. The gate confirms the *reduction* was not fumbled; it is not
   independent evidence that the object set is the one `score_capped.py` counted. The
   check that does bite is against a **different script's** recorded numbers, and it
   passes: the instrument's kept-component counts at those frames are 8 / 12 / 48,
   equal to the `n_updrafts` values `score_capped.py` wrote and §5.3 tabulated
   (`t5s_neutral_pc` 120:8, `dt3` 105:12, `dt6` 95:48).

**The headline, over §5.2's own window (t = 75 … 120 min, 10 frames).**

| member | ΣA_sec km² | `R_A` | ΣF_sec m s⁻¹ km² | `R_F` | verdict |
|---|---|---|---|---|---|
| `t5s_neutral_pc` (reference) | 894.2 | 1.000 | 13 263.9 | 1.000 | — |
| `t5s_capped_dt3` (CIN −60) | 1 273.5 | **1.424** | 21 182.9 | **1.597** | **NOT SUPPRESSED** |
| `t5s_capped_dt6` (CIN −82) | 2 738.5 | **3.062** | 42 920.3 | **3.236** | **NOT SUPPRESSED** |

Both ratios exceed 1 for both members, so this is §5.5's **first** outcome, the one
written first because it is the uncomfortable one. **The capped mixed layer fails as a
single-cell control at this CAPE with zero shear.** It is a physics result about the
*design*, not about the code, and not about the CIN generator.

**The confound §5.2 feared does not arise, and that is measured rather than assumed.**
The centre-connected component is **absent in every frame of the window in all three
runs** — last seen at t = 65 min in the reference and in `dt3`, t = 55 in `dt6`. So the
split and split-free readings are *identical numbers*, not merely consistent ones
(`R_A0` = `R_A`, `R_F0` = `R_F`), and **no part of the verdict rests on the topological
split.** That is the load-bearing statement and it is fully supported.

**Stated narrowly on purpose.** "No centre-connected component" is **not** "the pulse
cell died". The mask is column-max `w` ≥ 10 m/s and the split reads the four cells at the
domain centre, so a mature cell whose core has tilted or whose downdraft has opened
underneath it drops out of the *primary* category while it is still very much alive —
`dt6` loses its centre component at t = 60 while `A_tot` is still 495 km². What the code
supports is "no updraft column ≥ 10 m/s within ~1 km of the domain centre", and that is
all that is claimed. Nothing here dates the pulse cell's death.

**Post-hoc robustness (flagged as such, and it cannot create a verdict).** Restricting to
the geometrically complete interior (r ≤ the inscribed radius, 89.41 km) leaves `dt3`
unchanged (1.424 / 1.597 — none of its convection is out there) and moves `dt6` from
3.062 / 3.236 to **2.433 / 2.562**. §5.4(c)'s boundary material is real and it is all
`dt6`'s, but it is not what makes `dt6` worse. Direction unchanged in both members.

**The dose–response is monotone, and it is the evidence that the cap bit.** −60 J/kg
gives 1.42×, −82 J/kg gives 3.06×. A knob that did nothing would not order its members
by its own strength. Nothing here says the CIN generator (§3.1) failed — it says the
mechanism §5.2 predicted **in advance** is what happened: the cap acts on surface-based
parcels only, while the bubble parcel above it *gains* CAPE (2545 → 3226 J/kg at 6 K), so
the capped storm is stronger, its cold pool is stronger, and it triggers more along its
gust front. `dt6`'s secondary convection starts at **t = 50 min**, twenty-five minutes
before the reference's t = 75, and its radial reach in the window runs from 15 km out
past 125 km against the reference's 5–15 km.

**§5.4's "weak evidence that the cap bit early and was then overrun" is CONTRADICTED and
is withdrawn.** It rested on `dt3`'s counts of 1, 1, 1 at t = 75/80/85 against the
reference's 4, 8, 8. The integrals at those same frames are `dt3` 111.8, 119.8, 51.9 km²
against the reference's 27.9, 87.8, 87.8. At **t = 75 the capped run has four times the
updraft area of the reference and one quarter of its component count** — the count is
*anti-correlated* with the amount, because a fully connected annulus counts as 1 and a
fragmented one counts as 4 or 8. That single frame is the clearest statement of why
§5.2's criterion had to be replaced: `n_updrafts` was measuring the *fragmentation* of a
ring, not the number of cells and not the amount of convection.

**What §5.4's gate asked for is now discharged — and the answer removes the reason to
spend it.** The gate was "no third capped member until the symmetry is broken **or** an
instrument exists that does not count copies". The instrument exists, has passed three
gates and has been read. Its verdict is that a stronger cap makes this worse, so a third
capped member at any Δθ is not worth running: the design, not the setting, is what fails.
**The clean single-cell control that `classify_t5.py` was written against must come from
somewhere other than a capping inversion at this CAPE with no shear.** No option is
proposed here and no go is asked for.

**What this result does NOT say**, so it cannot be over-read later: it does not classify
ring versus cells (§5.5 declined to build that, for want of a negative control); it does
not count distinct features (§5.4's bound *distinct features ≤ count / 4* stands); it
carries no multicell label; and it says nothing about the capped sounding in a **sheared**
environment, where the symmetry does not exist and a cold pool does not close a ring.

**Artefacts.** `runs/t5s_capped_clean/INTEGRAL_TEST.txt`; instrument
`sim/probes/integral_test.py`, tracked for the same reason `ring_test.py` is.

**Lesson.** *A count of connected components measures fragmentation, not quantity, and
under a symmetry it measures neither.* The project already knew the first half — "component
counting cannot tell N cells from one ring in N lobes" — and this is the frame where it
inverted: fewer components, four times the convection. The fix was not a better classifier
but a different reduction, and the reduction that survives a symmetry is the integral.

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
