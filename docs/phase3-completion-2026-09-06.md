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

*(pending)*

---

## 5. Phase 3 exit options — owner calls

*(pending)*
