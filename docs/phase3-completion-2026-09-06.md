# Phase 3 close-out (T7) — flat convective regimes

Companion to `docs/phase3-plan-2026-07-20.md` (the plan), its 2026-09-02 amendment,
`docs/plan-science-hurdles-2026-09-02.md` (which supersedes the plan's T5/T6 rows), and
`docs/STATUS.md` (the per-task record). This document closes the phase: it dispositions
every carried item, states plainly what Phase 3 delivered and what it did not, and
settles — or records as unsettleable — the one extrapolation T4 deliberately left open.

Written 2026-09-06. Sections 2 and 3 are **pre-registered**: they were written and
committed before the gate they describe was run and before any of its output was
hashed.

---

## 1. T6 is void as specified, and that is a measurement, not a slip

The plan's T6 row reads *"Multicell run + export + diorama"*, and the 2026-09-02
amendment pins its asset precisely: *"the asset is T5s's **confirmed** multicell at
333 m (a `sim/scenarios/multicell_333m.json` with a `sim.sounding` block)."*

**That asset does not exist, and the reason it does not exist is the result of T5s.**
The external-sounding path works — the environment reaches the multicell regime with
the pinned binary unchanged, both neutrality gates passed 11/11, and the structural
transition lands between 15 and 20 m/s of 0–6 km shear exactly where the
bulk-Richardson-number boundary predicts. What never arrived is a **multicell label**:
the classifier's persistence criterion sat pinned at its 80-minute ceiling for every
sheared storm at 1 km *and* at 500 m, so refinement was measured to be the wrong lever,
and the one piece of multicell-side evidence any member had (`us15`'s elongation
statistic) did not survive that refinement.

So T6's input was measured unreachable, not merely un-run. Nothing else in the T6 row
survives that either:

- **"Export box for a multi-cell field (broad, several updrafts)"** — the general
  problem was solved anyway, offline, by the squall-line export contract
  (`plan-science-hurdles-2026-09-02.md` §§4.4–4.4a): the box is now per-axis, a
  periodic axis is gated to the full domain, and the resampling hazard on a periodic
  wall is refused by name. Gate `pipeline/tests/test_squall_box.py` 27/27.
- **"Appears in the diorama picker"** — the picker is scenario-agnostic since Phase 2
  T7; a new package needs no viewer work at all.
- **"Legends/labels reviewed for the new regime"** — there is no new regime to label.

**T6 is therefore recorded as BLOCKED BY MEASUREMENT.** It is not carried forward as
pending work, because "run the multicell scenario" is not a task anyone can pick up:
the thing it would run does not exist yet. What *can* be picked up is named in §5 as
Phase 3 exit options, each an owner call.

**No substitute asset was shipped.** A package could be built from the `us20` sweep
member — the environment is real and the storm is organised — but it could not honestly
be *named* multicell, because that is the one claim T5s measured we cannot make. An
education tool that ships a storm under a class label it failed to earn is exactly the
failure mode the charter's "legibility over photorealism" principle exists to prevent.
That call belongs to the owner (§5, option C), not to the close-out.

---

## 2. The gate this close-out owes: fork-neutrality generality — PRE-REGISTERED

### 2.1 The claim under test, and why it is load-bearing

`docs/phase3-t4-seed.md` §4.1 states the open extrapolation in its own words:

> gate 1a was measured at **one** configuration (500 m, 60×60, np=4). The patched
> block is unreachable at `irandp=0`, so generality is *expected* — but the patch adds
> 35 lines to a source file, and in principle that can move compiler decisions in the
> enclosing routine. So *"the fork is bitwise-neutral for every `irandp=0` run at any
> grid and rank count"* is an **extrapolation from one datum, not a measurement**.

It is load-bearing because of the charter's data policy: scenario package payloads are
deliberately outside git history, and **"regeneration from `sim/` + `pipeline/` is the
recovery path."** Since T4 that recovery path runs the *forked* binary
(`runs/cm1.exe` is a symlink into the build tree). All three shipped scenarios declare
`irandp=0`, so the recovery path holds **if and only if** stock ≡ fork there — at the
grids and rank count the shipped scenarios actually use, not only at the one small
configuration T4 measured.

T4 named the settling measurement: *"regenerate one shipped package on the forked
binary and compare against that run's recorded output checksums."*

### 2.2 What is actually available to compare against

There are no recorded output checksums in the repo — `scenarios/*/manifest.json`
carries none, and no checksum file was committed. **The raw netCDF is better than a
checksum file and it is still on disk**, which the charter did not promise (raw output
is disposable by design):

| Run dir (WSL ext4) | Scenario | Grid | Ranks | `cm1out_*.nc` | Size |
|---|---|---|---|---|---|
| `runs/singlecell` | `single_cell_500m` | 160×160×40 @ 500 m | 8 | 302 | 6.1 G |
| `runs/singlecell333` | `single_cell_333m` | 240×240×40 @ 333 m | 8 | 302 | 17 G |
| `runs/supercell333` | `supercell_333m` | 540×540×40 @ 333 m | 8 | 602 | 218 G |

Each dir holds a **copy of the binary that produced it**, and all three hash
`5da2c2aa…` — the stock Phase 0 binary. That is provenance, not inference.

**`single_cell_500m` is the member under test.** It is the cheapest (2.34 core-hours
recorded in its own `cm1.out` ⇒ ~18 min at np=8) and it varies **both** quantities the
extrapolation was scoped on: grid 160×160×40 against T4's 60×60, and rank count 8
against T4's 4.

**Pre-run deck gate, already passed and reported here before the run:** the production
generator reproduces that run's deck.
`pipeline/gen_deck.py --scenario single_cell_500m --verify runs/singlecell/namelist.input`
⇒ **PASS, all 344 keys match** (by parsed value, modulo comments and ordering). Without
this, a byte difference in the output could mean "the fork differs" *or* "we ran a
different deck", and the gate would prove nothing.

### 2.3 The hazard that had to be designed around

`sim/run_scenario.sh` runs a scenario into **the config's own `run_dir`** and executes
`rm -f cm1out*.nc` before launching. For `single_cell_500m` that directory *is*
`runs/singlecell` — the baseline. Running the shipped script would have deleted the
only copy of the thing being compared against, before producing the thing to compare.
The gate therefore uses its own runner (`sim/gates/t7_neutrality.sh`) into fresh
directories and **refuses to start if its target dir is any scenario's `run_dir`**.

### 2.4 The design: two fresh runs, one deck

Both members run the **same generated deck file** — generated once, copied to both — so
no difference between them can come from their input. Both run `mpirun -np 8`,
sequentially (8 ranks on 8 physical cores; concurrent members would oversubscribe and
buy nothing, since the comparison is bitwise, not timing).

| Member | Run dir | Binary | sha256 |
|---|---|---|---|
| **A** fork | `runs/t7neutral_fork` | `runs/cm1.exe` | `5fc93016…` |
| **B** stock | `runs/t7neutral_stock` | `runs/singlecell/cm1.exe` | `5da2c2aa…` |

Instrument: **sha256 over every `cm1out_*.nc`** — the same instrument T4's four gates
used, so this measurement is directly comparable to the datum it extends.

Environment recorded now, before the run: OpenMPI **4.1.6** (identical to the string in
July's `run_meta.txt`), gfortran 13.3.0, 16 hardware threads, 673 G free on the WSL
volume against a 12.2 G requirement.

### 2.5 Three comparisons, and what each one can and cannot show

1. **A vs B** — *the neutrality claim itself*, at 160×160×40 / np=8. Immune to any
   drift in the machine since July, because both members run today. **This is the
   comparison T7 owes.** PASS = every file identical.
2. **B vs July's on-disk output** — whether the July run *reproduces at all* today.
   This is a **different claim** — it is the recovery path's own reproducibility across
   time and environment, not the fork's neutrality — and a failure here does not
   impugn the fork.
3. **A vs July's on-disk output** — the composite the charter actually leans on: run
   today's recovery path, get July's bytes back. Only interpretable given 1 and 2.

### 2.6 Pre-registered branches

- **1 PASS, 2 PASS** ⇒ 3 passes by transitivity. The extrapolation becomes a
  measurement at a **second** configuration differing in both grid and rank count; T4
  §4.1 is upgraded from "expected" to "measured twice", and the charter's recovery path
  is settled for the shipped scenarios.
- **1 PASS, 2 FAIL** ⇒ the fork **is** neutral (which is exactly what T7 owes), but the
  recovery path is not bitwise across time/environment. The charter's own Conventions
  section anticipates this: the contract downgrades to *statistical equivalence +
  recorded output checksums*. Record it as such; do not blame the fork, and do not
  report Phase 3 as closing a claim it did not close.
- **1 FAIL** ⇒ the fork is **not** bitwise-neutral at this configuration. §4.1's
  extrapolation is refuted and every shipped package's regenerability is in question.
  That is the finding; it earns its own follow-up (which frame first diverges, which
  variable, how large), and Phase 3 does not close over it.
- **1 FAIL *and* 2 FAIL** ⇒ the instrument may be measuring machine nondeterminism
  rather than the fork. Escalate to a same-binary A/A repeat **before** concluding
  anything about the patch.

An A/A control is deliberately **not** run up front: T4 gate 3 already established
same-binary bitwise reproducibility at fixed rank count, so an A/A here would re-measure
a settled point. It is pre-registered above as the 1-FAIL-and-2-FAIL escalation only.

### 2.6a Amendment, written while the gate ran and before any of its output was read

The 1-PASS/2-FAIL branch above says the contract *"downgrades to statistical
equivalence + recorded output checksums"* — and §2.2 says, correctly, that **no
recorded output checksums exist**. As written, that branch points at a fallback with
no artifact behind it.

**So this gate creates the artifact.** It already computes
`t7neutral_baseline.SHA256SUMS` for `singlecell` as a side effect of comparison 2; that
list, and the equivalents for the other two shipped scenarios, are committed to
`sim/baselines/` as part of T7 — about 100 KB in total for 1206 output files, well
inside the charter's "nothing >10 MB in plain git" rule.

This is not tidiness. **The only baseline for all three shipped scenarios today is
240 GB of raw netCDF that the charter explicitly calls disposable by design.** The
first time anyone cleans `runs/`, this gate becomes permanently un-re-runnable and the
extrapolation reverts to unsettleable — not only for this fork, but for every future
compiler, MPI or netCDF bump. A checksum list survives the cleanup that the thing it
describes is *designed* to not survive.

`supercell333`'s list is deliberately computed **after** the gate finishes: hashing
218 GB during the run would steal memory bandwidth from it.

### 2.7 What this gate does NOT settle, stated in advance

One shipped scenario at one grid and one rank count. It does **not** license
*"neutral at any grid and rank count"* — it moves the claim from one datum to two, at
the largest grid and rank count that is cheap to measure. `supercell_333m` (540², 218 G,
~4.5 h) stays unmeasured, and if the owner ever wants that closed too, it is a known
run, not a new design.

---

## 3. RESULT — pending

*(This section is written after the gate runs. It is empty on purpose at commit time.)*

---

## 4. Carried items — disposition

Every row the Phase 3 plan §6 carried in, plus everything Phase 3 itself generated.
"Carried forward" is used only where a *named* successor owns it; nothing is left
pointing at "later".

### 4.1 Carried in from Phase 1/2 (plan §6)

| Item | Disposition |
|---|---|
| **Y-flip unverified** (Phase 1 #1) | **Still deferred, with the UE app.** Phase 3 shipped no placement code and no UE work at all; the diorama is a separate renderer with its own mapping. Belongs to whichever phase first puts a package into UE placement. |
| **`cref` orientation earned only from write convention** (Phase 2 T9) | **DISCHARGED — T3, 2026-07-28.** Measured against CM1's own `xh`/`yh` (separation-vector error 0.03–0.04 km vs 42.9–59.1 km transposed) and against real-GPU pixels (0.6–2.7 px vs 284–331 px), on two frames at two azimuths, plus a committed write-convention gate (`test_orientation_t3.py` 11/11) whose fixture is non-square *and has a control proving that matters*. Closed. |
| **UE SVT visual streaming sign-off** (Phase 1 task 3) | **Untouched — carried forward, owner-owed.** No UE this phase. It is a look-at-it check, not a build task. |
| **Diorama 5c pan-gesture sign-off** | **Untouched — carried forward, owner-owed.** Same shape. |
| **Fork neutrality generality** (new at T4) | **§3 of this document.** This was T7's one owed measurement. |
| **Manifest inline provenance** (cm1 sha256 / ranks / decomposition) | **Still open, still all-or-nothing, and now with a second input.** T5s made `input_sounding` a second scenario input, so a manifest fix must record its sha256 too. **Ordering matters and is recorded here:** the fix requires re-exporting every package and re-baselining the byte-identity gate, so it must not be done *before* a package-level reproducibility check — it would invalidate the baseline by construction. §3's gate was run first for exactly this reason. Owner call. |
| **VHDX 1024 GB ceiling** (Phase 1 #4) | **Not Phase 3, confirmed.** Flat 333 m runs stayed far under it (the largest, `supercell_333m`, is 218 G raw). It gates the 250 m terrain hero runs. Still needs the owner's resize number **before Phase 3T's first hero run** — carried forward to that phase, by name. |

### 4.2 Generated by Phase 3 itself

| Item | Disposition |
|---|---|
| **T5 — multicell from the namelist** | **CLOSED as measured**, not abandoned. Two independent criterion-1 designs, six runs, agreement on all six. The floor sweep turned out to *be* the median test, so raising a floor to find a result was measured impossible. |
| **T5s — the external-sounding path** | **DELIVERED, and it works**: `isnd=7` reaches the shear gap the namelist cannot, both neutrality gates 11/11, and the structural transition lands between 15 and 20 m/s where the bulk Richardson number crosses 50. The generator, the deck coupling (Category 6), and the `input_sounding` sha256 in `run_meta.txt` are all shipped. |
| **T5s — the multicell *label*** | **NOT reachable, and the route is spent.** The persistence criterion sat at its ceiling for every sheared storm at 1 km and again at 500 m; resolution was measured to be the wrong lever; and `us15`'s single piece of multicell-side evidence did not survive refinement. |
| **T5s — the transition-location claim** | **Stands on the split test alone.** Its two other supports are gone: `R`'s "separation strengthens" was **retracted** as a one-sided-refinement artifact, and the elongation gap lost more than half its size under matched refinement. |
| **The split test at 500 m** | **UNVERIFIED — indeterminate, not withdrawn.** Two escalations are **named and not run**, each its own owner go: (1) a connectivity reach in kilometres applied identically at both resolutions, with its own bar and neutrality gate; (2) longer runs, since the split signature lands at t ≥ 90–105 min in a 120-minute window. Carried forward as §5 option B. |
| **The CIN knob (H2)** | **Built and gated offline** (`pipeline/cm1post/sounding.py`), and **measured** — as a negative. The capped mixed layer produced *more* secondary convection than the uncapped reference (area ratios 1.42 and 3.06), monotone in cap strength, by the mechanism §5.2 predicted in advance. So the knob exists and works; the **capped-single-cell design** fails at this CAPE with zero shear. A clean single-cell control for the classifier must come from a different design — **carried forward without a named successor, because no design is on the table.** |
| **Squall line (C2)** | **Export contract DONE** (per-axis box, periodic-extent gate, `test_squall_box.py` 27/27); **no scenario shipped.** One repair is an **owner call not taken**: export a periodic axis at the simulation spacing, or give `regrid` real periodic wrapping. Until it is taken, a line ships at its sim spacing or not at all. §5 option D. |
| **Diorama performance** | **Owner calls 1–3 answered and C.2 shipped** (`export-web --web-voxel-m`; 6.53× fewer bytes, stalls 682 → 7). Not a Phase 3 task; recorded because it landed inside the phase's window. |
| **T6 — multicell run + export + diorama** | **BLOCKED BY MEASUREMENT — §1.** Not carried forward as pending work: its input does not exist. |
| **Terrain/motion deck rule** | **DONE at T7** — `deck.py` refuses `terrain_flag=true` (or `itern != 0`) with `imove != 0`; `test_deck.py` 16/16 → 20/20 with two refusals and two controls. The amendment asked for this "before Phase 3T opens"; it is in. |
| **`base.F` line numbers in the patches README** | **DONE at T7.** Recorded beside the pin, not only in the probes README. |

---

## 5. Phase 3 exit options — owner calls

Phase 3 delivered the flat-scenario system, the supercell, the seed mechanism, the
external-sounding environment generator, the CIN knob, the orientation discharge and
the squall-line export contract. It did **not** deliver a multicell scenario, and §1
says why. These are the options for what happens next; each is an owner decision, and
**none of them is started.**

**A. Close Phase 3 and open Phase 3T (terrain).** The prerequisites are known and
short: the VHDX resize number (§4.1), the Cartesian regridding module, the
heightfield render path, and the `output_zs`-class flag check — plus the
terrain/motion deck rule, which is now already in. This is the option that moves the
project forward rather than finishing an argument.

**B. Finish the split-test thread.** Two named escalations (§4.2). Escalation 1 is
analysis-shaped and cheap; escalation 2 is real compute (longer runs). What it buys is
*verification of a claim already made*, not new capability — and the claim's own value
is scientific honesty about where the regime transition sits, which matters for the
teaching narrative but ships nothing.

**C. Ship an organised-convection package from the `us20` environment.** The storm is
real and the environment is the sheared one T5s built. **The blocker is the name, not
the physics**: it cannot be called multicell. If the owner is content with an honest
descriptive name — the environment's shear, or "organised convection" — then this is a
333 m run, a measured export box, and a `sim/scenarios/` config. If not, it does not
ship.

**D. Ship a squall line.** Needs the periodic-axis resampling call taken (§4.2), then a
run, a measured x half-width from that run's own sweep, and a config. The export side
is already gated.

**E. Take the manifest inline-provenance decision.** All-or-nothing: re-export every
package and re-baseline the byte-identity gate. Cheap in wall-clock, and it is the last
charter reproducibility field that lives only in `run_meta.txt` rather than in the
shipped contract. **Do it after, never before, any package-level reproducibility
check** (§4.1).
