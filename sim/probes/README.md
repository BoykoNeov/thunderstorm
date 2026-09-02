# Probes

Throwaway diagnostic runs — **not** shippable scenarios. Nothing here produces a
scenario package; `sim/scenarios/` is for configs that can be exported, and a probe
config in there would be a config that `export_scenario.py` cannot honour.

## Why the configs are tracked

`docs/phase3-t5-multicell.md` §§7, 9 and 11 rest on six 1 km runs. Per the T4
finding, **the namelist is CM1's sole scenario input** (`isnd=5` computes the WK
sounding internally), and these configs are the sole input to the namelist
generator. The run directories are large and disposable; these six files are ~15 KB
and are what makes the record reproducible — the same argument the charter's data
policy makes for scenario packages.

**Measured claim, stated exactly:** config + `pipeline/` reproduces **the deck each
run used, byte-for-byte** (verified on all six). Reproducing the *run* additionally
needs the pinned fork binary `5fc93016…` **and the rank count**, because T4 banked
"same seed ⇒ bitwise identical" only *at fixed rank count* — and `nranks` is not a
config key. All six T5 probes ran at **`-np 4`**; each run's own `run_meta.txt`
records it, and that file is not tracked, so the number is written here.

| config | §2 role | key overrides |
|---|---|---|
| `t5probe_sc.json` | control — known supercell | `iwnd=2`, `imove=1` |
| `t5probe_pc.json` | control — known single pulse cell | `iwnd=0` |
| `t5probe_a.json` | candidate A | `iwnd=4` (CM1's own "multicell" profile) |
| `t5probe_b.json` | candidate B | `iwnd=1` (10 m/s bulk shear) |
| `t5probe_c.json` | candidate C — line thermal | `iwnd=1`, `iinit=8` |
| `t5probe_c2.json` | candidate C2 — C with periodic y | `iwnd=1`, `iinit=8`, `sbc=nbc=1` |

C2 differs from C in exactly two deck lines, both boundary keys (§10.3). All six
run `irandp=0` and the fork binary `5fc93016…`.

### T5s — external sounding (`isnd=7`), pre-registered 2026-09-02, NOT YET RUN

`docs/plan-science-hurdles-2026-09-02.md`. These configs carry a `sim.sounding` block;
`run_probe.sh`/`run_scenario.sh` generate `input_sounding` from it and record its
sha256. Each config's `provenance` records the BRN and the WK82 regime it PREDICTS,
computed from the sounding alone before any run (`test_sounding_t5s.py` gates that the
recorded prediction equals what the config's own sounding computes).

| config | role | environment | prediction |
|---|---|---|---|
| `t5s_neutral_pc.json` | control — PC re-run through the file path | WK82 14 g/kg, no wind | base state ≡ `t5probe_pc` (θ/qv to interpolation accuracy); same pulse cell |
| `t5s_neutral_a.json` | control — A re-run through the file path | WK82 + tanh U_s=35 | u0 ≡ `t5probe_a`'s (CONFIRMS in the run what the source read settled); same supercell |
| `t5s_us15.json` | sweep | WK82 + tanh U_s=15 (14.5 m/s 0–6 km) | BRN 59 → **multicell** |
| `t5s_us20.json` | sweep | WK82 + tanh U_s=20 (19.3 m/s) | BRN 33 → supercell |
| `t5s_us25.json` | sweep | WK82 + tanh U_s=25 (24.1 m/s) | BRN 21 → supercell |

The neutrality controls run FIRST and gate everything else: if `t5s_neutral_pc` does
not reproduce `t5probe_pc`'s base state, `isnd=7` is not what the plan believes and the
sweep is not run.

#### §4.0 source read — **DONE 2026-09-02**, all three questions answered from source

The plan's §4.0 required reading `base.F` before any run, because the three facts the
proposal rests on came from memory of `README.namelist`, not from the source. Read in
`/home/boiko/thunderstorm/build/cm1r21.1/src/` (the pinned tarball, `dc49fe84...`):

| Question | Answer | Source |
|---|---|---|
| (a) `isnd=7` file format | **Confirmed exactly as the plan states.** Header `p_sfc[mb] th_sfc[K] qv_sfc[g/kg]`; then `z[m] theta[K] qv[g/kg] u[m/s] v[m/s]` ascending. `qv` is divided by 1000 on read. | `base.F:463-494` (comment), `:543-560` (reader) |
| (b) is `iwnd` applied at `isnd=7`? | **No -- settled three ways.** The comment says so; the whole analytic-wind section is skipped; and `param.F` *forcibly sets* `iwnd=0` with a **non-fatal** warning. This project's deck rule is **stricter than CM1's**: CM1 warns and continues, `deck.py` refuses. | `base.F:466`, `base.F:2263` (`IF(isnd.ne.7)`), `param.F:836-853` |
| (c) level cap | **`nmax = 1000000`**, comment "# of levels is arbitrary". The writer's 441 is nowhere near it. The real constraints are `nsnd > 2` and **the last `z` must exceed `zh(nk)`** (the top *scalar* level = 19750 m here, not the 20000 m nominal model top) or CM1 stops. The writer's 22000 m clears it. | `base.F:501` (`nmax`), `:565-572` (`nsnd>2`), `:492` + `:681-684` (z-top check) |

**Five further findings from the same read, none of which change T5s's design:**

1. **`output_basestate=0` in the template -- the gate would have been unevaluable.**
   `th0`/`qv0`/`prs0`/`u0`/`v0` are written *only* at `output_basestate=1`
   (`writeout.F:4431-4494`, `:6886`, `:7347`), and the template runs 0. Every `t5s_*`
   config now declares `output_basestate: 1`; it is a Category 5 optional key in
   `deck.py`, so the shipped scenarios that omit it stay byte-identical (all four
   byte-identity suites re-run green). Found *before* the runs, not after.
2. **`input_sounding_grid` is dead code.** `base.F:3247` sits behind `dothis = .false.`,
   so CM1 never writes the interpolated sounding to a plate. The netCDF base state is
   the only gate input, which is what item 1 makes possible.
3. **CM1's WK82 and this project's agree line for line**, which is what the
   thermodynamics gate actually compares. Same theta (eq. 1) and RH (eq. 2) constants
   (`base.F:369-374`, `:390-396`); the mixed layer is the **same implicit clip** in both
   (`if(qv0.gt.qv_pbl) qv0=qv_pbl` is `min(rh*qvs, qv_pbl)`), so the PBL join is at the
   same height by construction rather than by agreement; same saturation formula
   (Bolton 1980, `rslf` in `cm1libs.F:35-41`); and identical physical constants
   (`constants.F:110-117`: `g=9.81, rd=287.04, cp=1005.7, rv=461.5`). Two known small
   differences remain and are expected in the gate residual, not treated as failures:
   CM1's `isnd=5` builds its first half-step from a **saturated** surface
   (`qv_sfc = rslf(p_sfc,T_sfc)`, about 22.6 g/kg) while the `isnd=7` path takes the
   file header's 14 g/kg -- worth a few Pa; and the file is interpolated from 100 m
   spacing onto CM1's levels, RH-preserving.
4. **The writer's level spacing is now 50 m, and the reason was measured before the
   run.** CM1 interpolates the file's **RH** linearly onto its own levels, and the
   mixed layer ends in an implicit *kink* in RH(z) (where WK82's RH stops demanding
   more moisture than the `qv_pbl` clip allows -- 1300 m for the 14 g/kg reference). A
   model level straddling that kink picks up a moisture error. Measured offline against
   the isnd=5 reference run's own base state: 100 m spacing gave **0.046 g/kg at
   z=1250 m -- 92 % of the gate's 0.05 g/kg budget**; 50 m gives 0.0048; 25 m gives
   0.0048 (converged). `DEFAULT_DZ_M` is 50 m. This is a fix found *before* spending a
   run, which is the whole point of doing the source read first -- the alternative
   would have been a gate that passed by 8 % and nobody knowing why.
5. **CM1 extrapolates the surface wind** rather than reading it -- the header line has no
   wind columns, so `usnd(1)`/`vsnd(1)` come from levels 2 and 3 (`base.F:611-618`).
   For a `tanh` profile at 100 m spacing that is a 0.004 m/s error. Recorded so a future
   profile with curvature at the ground does not silently disagree with the bulk shear
   the generator reports.

**`u0` in the output is grid-relative.** `base.F:2661-2668` subtracts `umove`/`vmove`
after the sounding is built, for `isnd=7` exactly as for `isnd=5`. The neutrality
comparison is unaffected (A and `t5s_neutral_a` both run `umove=23`), but a comparison
of `u0` against the *file* must add `umove` back.

**`iwnd=3` -- ruled out in T5, now measured from source.** T5 section 2.2 ruled it out on
the grounds that its source comment is `Mulit-cell type profile (?)` with no citation.
Computed from the constants at `base.F:2366-2392` (`u` linear from -12.73 to +52.73 m/s
over 7500 m, `v` constant at 12.73 so it adds nothing to the vector difference), its
0-6 km bulk shear is **52.4 m/s** (48.0 between CM1's 250 m and 5750 m scalar levels) --
**above** the 10-31.8 m/s gap, not inside it. So T5's conclusion is unchanged and now
rests on arithmetic rather than on a missing citation. It is not probed: wrong side of
the gap, and probing an uncited profile to look for a wanted answer is T5 section 7.4's
trap.

**`isnd=17` -- a real option the record did not have.** Same file, columns 4-5 ignored,
wind from `iwnd` (`base.F:495`, `:552-554`; `README.namelist`). It decouples the two
knobs, so a future task could hold CM1's validated `iwnd=2` wind while sweeping CIN
through the file. It also **inverts** the `iwnd=0` rule, and no gate covers it, so
`deck.py` refuses it by name rather than letting it pass Category 6 vacuously.

#### §4.1 neutrality controls — **PASSED 2026-09-02, 11/11.** `isnd=7` is what the plan believed.

Two runs, `-np 4`, ~13 min each, concurrent. Scored by `sim/probes/gate_t5s_neutrality.py`,
committed before the runs with section 4.1's thresholds unchanged.

| Claim | Measured | Tolerance |
|---|---|---|
| recovery identity (`th-thpert`, `qv`, `prs`, `uinterp` at t=0 **are** CM1's own base state) | **0.000e+00** on all five fields | — |
| **PLUMBING** — CM1's base state IS the file it was given | theta 2.2e-05 K, qv 8.5e-07 g/kg, u 1.9e-06 m/s | 0.1 K, 0.05 g/kg, 0.2 m/s |
| **IMPLEMENTATION** — this project's WK82 == CM1's WK82 | theta 6.1e-05 K, qv 0.0048 g/kg | 0.1 K, 0.05 g/kg |
| wind is NOT zeroed at `iwnd=0` (it comes from the file) | max abs u0 20.09 m/s grid-relative (35.0 absolute) | > 1 m/s |
| wind matches `t5probe_a`'s at every level | 5.1e-05 m/s | 0.2 m/s |
| CM1's own t=0 CAPE | 1943.0 vs 1942.4 J/kg (**0.03 %**) | 10 % |
| base-state pressure (named in §4.1, no tolerance given) | **7.04 Pa** at z=250 m, falling with height — the saturated-surface first half-step at `isnd=5` vs the file header's 14 g/kg, predicted by the source read | reported, not gated |
| same pulse cell as `t5probe_pc` | peak w 61.55 vs 61.60 m/s (0.07 %), both at t=1500 s | 5 %, 300 s |
| same supercell as `t5probe_a` | peak w 54.18 vs 52.88 m/s (2.45 %), both at t=7200 s | 5 %, 300 s |

**What this settles.** The environment reaches CM1 through a generated text file, with the
binary unchanged. The PLUMBING numbers are at floating-point noise, which also means this
project's reimplementation of `base.F`'s interpolation (in the gate script) and CM1's own
agree — two independent paths to the same base state. The IMPLEMENTATION residual is the
0.0048 g/kg predicted offline before the runs, and its cause is known (the 100 m-to-model-
level interpolation across the mixed-layer kink, now at 50 m spacing).

**The supercell's 2.45 % is the largest number here and it is expected**: a supercell is
chaotic, so a base state differing in the 5th decimal diverges over 2 h far more than the
pulse cell's 0.07 %. It is inside the pre-registered 5 % and the peak time is identical.
This is why section 4.1 asked for "the same storm family", not bitwise equality — CM1
interpolates the file, so bitwise was never on offer (section 2's table said so).

**Consequence for owner decision 2:** option (i), the `0002-` shear patch and its third
binary hash, is now **measured to be unnecessary** — the gap is reachable with the pinned
fork binary and a text file. Recommend dropping it. That is the owner's call, not this
document's.

**One defect found and fixed while scoring:** the gate's frame glob also matched CM1's
`cm1out_stats.nc` (a domain-statistics file with no 3D fields), which crashed the storm
comparison. A file-matching bug, not a threshold change; the thresholds are untouched.
Also fixed: `run_probe.sh` hardcoded `pre-registration : docs/phase3-t5-multicell.md` in
every `run_meta.txt`, so the T5s runs named the wrong document. It now reads the config's
own `provenance.probe_of`. (The two runs above have the wrong line in their `run_meta.txt`
and are not re-run for it; this note is the correction.)



#### §4.2 criterion 2 (discrete propagation) — **control validation FAILED 2026-09-02. NOT promoted.**

Implemented in `births_t5s.py` and validated on the two controls **before** any sweep
member was scored, which is what the validation was for. Two rounds, both on the
controls, no threshold moved in either:

**Round 1 — the plan's trigger cannot fire.** §4.2's birth was gated on "after the
first cell's updraft maximum decays below half its peak". Measured on all six T5 runs,
that fires on **one** of them (PC), and *not* on the supercell control: SC and A both
peak at the final frame. The clause reads the domain-wide peak updraft, a running
maximum over whichever cell is strongest, which does not fall when a cell dies. Every
sheared run would have scored 0 births and §4.2's "us20, us25 → SUPERCELL by (2)"
would have been **correct and vacuous**. Re-pre-registered with the trigger replaced
by "not a continuation, and convection already present"; 8 km, 15 min, 3 births and
every field threshold left as the plan wrote them.

**Round 2 — two defects in clause (d), both threshold-free.** The first version scored
SC at 3 births. Both extra births rested on the implementation, not the storm:
*right censoring* (the run ends at t=120 and they were born at t=105, so they
"persisted 15.0 min" because the data ran out — and any birth after t=105 was being
silently dropped), and *greedy hopping* (the forward walk chose the nearest of several
candidates, which is the argmax tracker T4 §5.2 retired and `chain_stats` explicitly
refuses; SC carries 3→5→7→9 components in its last four frames). Fixed: births in the
final 15 min are **unscorable** and reported apart, and two or more candidates within
`LINK_KM` **end** the chain rather than being resolved by proximity.

**The corrected control result:**

| control | §4.2's bar | measured | reading |
|---|---|---|---|
| `t5probe_sc` | ≤ 1 birth | **2** | over the bar. The label is still right (2 < 3) but the margin to MULTICELL is **one birth**. |
| `t5probe_pc` | ≤ 1 birth | **0** — with **3** clause-(c)-gated re-initiations | **NOT EXERCISED.** PC's updrafts run `… 1 1 0 0 0 4 4 4 4 …`; the zero frames mean clause (c) gates the entire daughter ring, so nothing was rejected — there was simply nothing to propagate *from*. A 0 here is not a pass. |

**And the finding that settles it.** PC's censored tail holds **four entries at t=110
that are identical to the decimal** — 9.07 km separation, peak 18.28 m/s, area
5.99 km², all four. That is T5 §7.3's axisymmetric gust-front ring, four lobes
quantised by a square grid, arriving here through a completely independent
construction. **Had that ring formed fifteen minutes earlier it would have scored four
births and labelled the SINGLE-CELL control MULTICELL.** Criterion 2 is foolable by the
same artifact that retired T5's original count-based criterion 2.

**Consequence, pre-registered before the sweep is read:** criterion 2 is **not
promoted** and does not score the sweep. It is reported as a descriptor with its
control numbers attached, never as a label. **H3 stands, and is now confirmed by an
independent construction** — two different entity definitions (≥40 dBZ cells in T5,
≥10 m/s updrafts here) are each documented-fooled by the same axisymmetric ring. Per
the standing method rule, the entity definition is *not* iterated a third time: that
would be shopping for a construction that flatters the controls.

## Running one

```sh
bash sim/probes/run_probe.sh sim/probes/configs/t5probe_c2.json 4
```

Two at 4 ranks beats one at 8 on this machine (charter, "Wall-clock matters").

## Scoring

```sh
python3 sim/probes/classify_t5.py --only sc,pc          # controls first
python3 sim/probes/classify_t5.py --only sc,pc,a,b,c,c2
```

The classifier implements a **pre-registered** rule and no threshold in it may be
moved to make a candidate come out a particular way — see its docstring and the
doc's header. Its guards are gated by `pipeline/tests/test_classifier_t5.py`, which
needs no run data and must stay green.
