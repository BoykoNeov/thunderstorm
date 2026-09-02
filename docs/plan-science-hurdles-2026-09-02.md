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

### 4.3 Cost

Five 1 km probes × ~13 min at `np=4`; one classifier addition (discrete propagation)
with its control run before the sweep; no CM1 rebuild; no pin moves. A 500 m
contingency re-run of one member is ~2 h. Total well under one working day of machine
time.

### 4.4 What T5s retires

- **Option (i), the `0002-` shear patch** — its premise ("only a source edit can reach
  the gap") is false. Recommend the owner drop it once §4.1 passes.
- **T5 §11.7's carried consequence** (a periodic-y line has no finite condensate extent
  in y, so the crop-box measurement inherits an error one level up in the export path):
  a compact WK82 multicell at open boundaries replaces the line as the T6 asset, so the
  hazard is avoided rather than solved. If the owner still wants the squall line as a
  scenario, that hazard returns and needs the box-measurement fix first.

---

## 5. H2 — the CIN knob, and what it is for

The knob exists (§3.1) and is deliberately **not** used in the T5s sweep: changing two
things at once would make the sweep unreadable. Its uses, in order of value:

1. **A clean single-cell control.** T5 §7.5 found the zero-CIN pulse cell rings up
   daughter convection after t=70 min, which is what broke the PC control's role. A
   capped variant (`cap.dtheta_k` 2–3 K over a 1 km mixed layer, CAPE held at the
   reference 1859 J/kg) is a one-block change to `t5probe_pc` and would give the
   classifier the "one bubble, one cell, then nothing" control it was designed
   against. **Owner's call whether that is worth a 13-minute run**; it is not needed
   for T5s.
2. **The forecast → outcome panel.** Two scenarios with identical CAPE and shear and
   different CIN — one that initiates, one where the bubble fails to break the cap — is
   the charter's honest "why storms form" lesson made literal, and the generator holds
   CAPE across them by construction. A Phase 4 teaching scenario, not Phase 3.
3. **Mixed-layer depth as a knob** (McCaul & Cohen 2002's actual experiment) is exposed
   but constrained: at 14 g/kg a well-mixed layer deeper than ~0.9 km saturates, and the
   generator refuses it. Deeper mixed layers need lower moisture, i.e. a CAPE hold at a
   lower target. That interaction is real physics and the tool says so instead of
   clipping.

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

## 7. Owner decisions requested

1. **T5s go/no-go** (§4). Step 1 is a source read; steps 2–3 are five 13-minute runs.
2. **Drop option (i)** (the `0002-` shear patch) once §4.1 passes, or keep it priced.
3. **Whether to run the capped single-cell control** (§5.1) — optional, 13 min.
4. **Whether the squall line (C2) stays a wanted scenario** — if yes, T5 §11.7's box
   hazard is real work; if no, it is retired with T5s.
5. Carried, unchanged: UE SVT visual streaming sign-off; diorama 5c pan gestures; VHDX
   resize number; manifest inline provenance (now with a second input to record).

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
