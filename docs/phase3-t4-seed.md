# Phase 3 T4 — seed-driven variation

**Date:** 2026-07-28. Plan: `docs/phase3-plan-2026-07-20.md` §4.3, task T4.
**Owner scope call (asked at T4 start):** *mechanism now, decide packages after
seeing the spread.* So T4 delivers the mechanism, the reproducibility contract and
the measured spread; it ships **no** scenario package. That decision is now due —
see §7.

## 1. The plan's premise was falsified before any code was written

Plan §4.3 scoped T4 as: *"adds the seed key to `REQUIRED_KEYS`, wires `irandp=1` +
the CM1 seed/amplitude keys"*. **The CM1 seed and amplitude keys do not exist.**
Measured in the cm1r21.1 source first, which is why this is a scoping correction
and not a bug found late:

| Claim | Reality in cm1r21.1 |
|---|---|
| there is a seed namelist key | **No.** No `namelist /paramN/` in `input.F` contains one. |
| `irandp=1` gives random perturbations | It gives the **same** perturbations every run. |
| perturbation amplitude is tunable | Hardcoded `amplitude = 0.25` (K), `init3d.F`. |
| bubble geometry/position is tunable | Hardcoded. `centerx`/`centery` are module variables set from domain geometry in `param.F:7408`, not namelist keys. |

The mechanism behind row 2 is the load-bearing find. `init3d.F:168`:

```fortran
      logical, parameter :: use_truly_random_pert  =  .false.
```

A **compile-time constant**. It selects between a `date_and_time`-based reseed and
the branch commented *"generate same set of pseudorandom numbers every time
(default for cm1)"*, which seeds from a hardcoded ramp. Stock CM1 therefore has
exactly two behaviours available — perfectly reproducible with **zero** variation,
or wall-clock-seeded and **not reproducible at all**. Neither is what a teaching
ensemble needs, and no namelist value moves between them.

So seed variation is not reachable from the namelist, and a CM1 **fork** is
unavoidable. Plan §3's line — *"seed variation is a deliberate `REQUIRED_KEYS`
addition"* — survives intact; what it adds is simply not a CM1 key.

## 2. The fork, and why it is nine lines

The Phase 3 plan (§2.3) assigned "this task needs a source edit" to **T5**
(multicell initiation), and warned that a source edit costs the reproducibility
recovery path unless designed for. That consequence arrives one task early.

It argues for doing T4 **now** rather than deferring it behind T5: the
fork-provenance mechanics (vendored patch, fresh binary hash, charter pin, per-run
provenance) get built exactly once, and it is far safer to debut them on a nine-line
uncomment than alongside novel multi-bubble initiation physics. T5 inherits working
mechanics.

**The patch enables CM1's own hook.** Immediately inside `IF( irandp.eq.1 )THEN`,
upstream ships this loop commented out — the author's own seed hook, unused:

```fortran
!        do n=1,nint(var7)
!          if(myid.eq.0) print *,'  pert loop = ',n
!        ...  call random_number(rand)  ...
```

`sim/cm1-patches/0001-seed-via-var7.patch` uncomments it and documents the
semantics in-source. It adds no new logic.

### 2.1 What the fork does and does not cost

Phase 2 §10.2 earns *"the generated deck reproduces the **run**, not just the
deck"* from two separate facts. Only one moves:

- **"The namelist is CM1's sole scenario input"** — **still true.** `var7` is an
  *existing* CM1 key (`&param8`), already in the template, already MPI-broadcast.
  No scenario value became a hardcoded constant.
- **"The binary is the Phase 0 binary"** — **no longer true**, for any run using
  this binary. Hence the vendored patch, the hashes below, the charter pin naming
  the fork, and `run_meta.txt`'s existing per-run `cm1_binary_sha256`.

| Artifact | sha256 |
|---|---|
| upstream `cm1r21.1.tar.gz` | `dc49fe84531056d1ae6249b37a5e3ee453fd96861c3b6bafd63828d92e64edf7` |
| stock binary (Phase 0, pre-fork) | `5da2c2aa49b9f226cedb5c833219d915dca71c4f328923e47cdbf596bab016bd` |
| forked binary (T4) | `5fc9301623fb2f8b00ebf476cef39b7046e50a2ce0bacfdad560941ae80eb59d` |

The stock hash was verified against `docs/phase0-cm1-build.md:45` **before** the
patch was applied, so any later difference is attributable to the patch and not to
a binary that had already drifted. The stock binary is preserved at
`run/cm1.exe.phase0-stock` so the two can be A/B'd — which §4 does.

### 2.2 It is a stream offset, not a re-seed

Stated plainly because it bounds the claim. `var7` advances the PRNG stream by
`nint(var7)·nk·(ny+2)·(nx+2)` draws before the perturbations are drawn. Different
seeds therefore get a **shifted reuse of one stream**: decorrelated at every grid
point, but not independently drawn. That is sufficient for *"same environment,
divergent trajectory"*, which is what the teaching scenario needs. A true
`random_seed(put=)` is a small further edit on an already-forked binary if
independence is ever required.

The advance stride deliberately differs from the consumption stride (which draws
twice, over `0..nx+2`/`0..ny+2`), so no feature aliases between seeds.

**Banked property:** the perturbation loop iterates the *global* domain on every
rank and each rank applies only the points it owns, so the perturbation field is
**decomposition-independent** — the same seed gives the same field at any rank
count. This is what licenses verifying the mechanism at 500 m/np=4 instead of
333 m/np=8. It does **not** make a whole run rank-independent: floating-point
summation order still differs, so *"same seed ⇒ bitwise identical"* holds at a
fixed rank count, which is exactly what the charter's reproducibility contract
records.

## 3. The scenario-to-deck contract

`seed` is a **REQUIRED** key (`cm1post/deck.py`), declared semantically and emitted
as `var7`. The indirection is deliberate: a raw `"var7": 3.0` in a scenario file
tells a future reader nothing, and the seed has to carry a real name into
provenance.

Making it REQUIRED looked like it would force churn in the three existing
scenarios and **did not**: they declare `"seed": 0`, which substitutes `0.0` into a
template line that already reads `0.0`, at the same column width. Verified —
all three generated decks are **byte-identical** to their pre-T4 versions
(references extracted from `HEAD` with `git archive`, the same A/B technique
Phase 2 T1 used):

```
BYTE-IDENTICAL  single_cell_500m   4EEF9F40B4A0E679...
BYTE-IDENTICAL  single_cell_333m   278F0E1F89313C53...
BYTE-IDENTICAL  supercell_333m     DF0987167197DEED...
```

So T1c's reproduction gate and T6's differential gate do not move. The only test
change needed anywhere was T6's hardcoded override count, 28 → 29 (`REQUIRED_KEYS`
gained `seed`, which is popped and re-emitted as `var7`).

**`scenario.SCHEMA_VERSION` deliberately stays `1.0`.** Written down because this
repo has spent effort on version-bump questions twice already (T3 bumped then
reverted; T4/T5 of Phase 2 bumped deliberately). Adding a REQUIRED key *looks* like
a schema change, but the requirement is enforced in `deck.py`, not in the loader:
`scenario.load` neither reads nor validates `seed`, so **no 1.0-era reader breaks**,
and a 1.0 config missing `seed` fails at deck generation with a precise message
rather than silently. The version describes what the *loader* contracts for; it did
not move.

### 3.1 Three ways a seed is silently ignored — all refused

Each of these generates a valid deck, runs for hours, and returns the **wrong
ensemble member**, with no crash and no warning. `_seed_to_var7` refuses all three:

- **Negative seed.** `do n=1,nint(-5.0)` is a **zero-trip** loop. CM1 does not
  error; seed −5 silently *aliases to seed 0*. Two "different" members come back
  bitwise identical.
- **Non-integer seed.** `nint()` rounds, so 1.4 and 0.6 both alias to seed 1.
- **`seed > 0` with `irandp = 0`.** The advance lives inside
  `IF( irandp.eq.1 )THEN`, so with perturbations off the seed is read, broadcast
  and ignored. **This is the one most likely to be hit in practice** — building an
  ensemble by copying an unseeded scenario and changing only the seed yields N
  identical storms.

`seed = 0` with `irandp = 0` stays legal: it is how the three shipped scenarios
declare themselves honestly unseeded. The guard is targeted, not blanket.

## 4. The run gates — measured on real CM1, both binaries

Six runs, 500 m / 60×60 / 20 min / np=4, decks rendered through the **production**
generator (`cm1post.deck.generate`), comparison by sha256 over every netCDF output
file. Full harness kept out of git with the run dirs (346 MB source tree, two
binaries, six runs — same one-shot shape as T3's links A and B).

| Gate | Comparison | Want | Got |
|---|---|---|---|
| 1a neutrality, `irandp=0` | stock vs fork | IDENTICAL | **IDENTICAL** |
| 1b neutrality, `irandp=1`, seed 0 | stock vs fork | IDENTICAL | **IDENTICAL** |
| 2 positive | fork seed 0 vs seed 1 | DIFFERENT | **DIFFERENT** |
| 3 same-seed reproducibility | fork seed 1 vs seed 1 | IDENTICAL | **IDENTICAL** |

**Gate 1b is the real neutrality claim**, not 1a. 1a only exercises code outside
`IF(irandp.eq.1)`; 1b runs the patched block itself and confirms the zero-trip loop
is a genuine no-op — the forked binary reproduces stock CM1 bitwise at seed 0.

**Gate 2 is the load-bearing one**, for a reason beyond the science. `init3d.f90`
is the cpp artifact of `init3d.F`. Edit the `.F`, fail to regenerate the `.f90`, and
the binary is silently unchanged — which **passes neutrality trivially**. Only the
positive gate catches that. (The Makefile's `.F.o` rule regenerates `$*.f90` on
every build, so the trap is structurally covered too; verified directly —
`init3d.f90:1468` carries the live loop.)

**Gate 3 is bitwise at fixed rank count** (np=4), per §2.2.

### 4.1 Gate 1a is quietly holding up the charter's recovery path

Worth making explicit, because it is the first question a future reader should ask.
The charter's data policy accepts that *"packages are not backed up by git —
regeneration from `sim/` + `pipeline/` is the recovery path."* T4 changed the binary
that recovery path runs (`runs/cm1.exe` is a symlink into the build tree, so it now
resolves to the fork — see `sim/cm1-patches/README.md`).

The reason that is still fine is **gate 1a**: all three shipped scenarios declare
`irandp=0`, and stock ≡ fork bitwise there. Regenerating any shipped package on the
forked binary therefore reproduces it.

**Scoped honestly:** gate 1a was measured at **one** configuration (500 m, 60×60,
np=4). The patched block is unreachable at `irandp=0`, so generality is *expected* —
but the patch adds 35 lines to a source file, and in principle that can move compiler
decisions in the enclosing routine. So *"the fork is bitwise-neutral for every
`irandp=0` run at any grid and rank count"* is an **extrapolation from one datum, not
a measurement**, and is recorded here as such.

**What would settle it:** regenerate one shipped package on the forked binary and
compare against that run's recorded output checksums. That is a real check, not an
argument — carried to T7 rather than asserted here.

**SETTLED 2026-09-07 (T7).** The check named above ran, and the extrapolation is now a
measurement — see `docs/phase3-completion-2026-09-06.md` §§2–3. The gate re-ran
`single_cell_500m` (160×160×40, np=8) on **both** binaries on the same machine on the
same night, from one generated deck, and compared each against the July on-disk output:
all three comparisons IDENTICAL over 302 files. That is a second configuration
differing in **both** quantities this paragraph scoped on — grid (160² vs 60²) and rank
count (8 vs 4) — so the claim above is upgraded from *expected* to **measured twice**.

It is still not *"any grid and rank count"*: `supercell_333m` (540², 218 GB) remains
unmeasured, and closing it is a known run rather than a new design. The checksum lists
that make any such future check possible after the raw output is deleted now live in
`sim/baselines/`.

Note the plan's stated gate — *"same seed ⇒ identical deck"* — is nearly
tautological (deterministic text substitution on identical input). It is kept as
`test_seed_t4.py`'s weakest check and labelled as such; the reproducibility claim
that matters is gate 3, at run level.

## 5. Measured spread

Different bytes can mean a 1e-7 perturbation that is scientifically nothing, so
the divergence is quantified rather than asserted.

### 5.1 Pulse cell (the gate configuration) — large

500 m, 30 km domain, 20 min, `irandp=1`, seed 0 vs seed 1:

| t (s) | peak w seed 0 | peak w seed 1 | Δ |
|---|---|---|---|
| 300 | 1.61 | 1.89 | +17.4 % |
| 600 | 10.29 | 13.93 | +35.4 % |
| 900 | 28.02 | 25.26 | −9.8 % |
| 1200 | 29.14 | 33.98 | +16.6 % |

Final frame, field level: max |Δw| **35.4 m/s**, mean |Δw| 0.45 m/s, **7.8 %** of
voxels differ by >1 m/s, and the updraft core sits **~9 grid cells apart**
horizontally. These are two genuinely different storm realizations, not a
numerical wobble.

**But this is the flattering regime.** A 30 km pulse cell is weakly constrained —
the 1 K bubble barely dominates the 0.25 K noise, and there is no shear to organize
the outcome. It says the mechanism works; it does **not** predict what a supercell
does.

### 5.2 Supercell regime — the number the package decision turns on

Measured on a **sheared, splitting** storm: `iwnd=2`, `imove=1`, NSSL `ptype=27`,
the same 179.82 km domain and 2 h window as `supercell_333m`, but at 1 km / `dtl=6`
— roughly 27× less work (~13 min per run instead of ~4.5 h), and the resolution
Phase 0 validated the WK supercell at. `irandp=1`, seed 0 vs seed 1.

**The two answers point in opposite directions, and both matter.**

**Intensity is robust.** After the first ~40 min the storms agree closely:

| metric | seed 0 | seed 1 | Δ |
|---|---|---|---|
| peak w over the run | 55.64 | 57.62 m/s | **3.6 %** |
| max dbz @ t=110 | 70.2 | 66.7 dBZ | 3.5 dB |
| peak w, t=40…120 | — | — | mostly within ±5 %, worst −11 % |

This is the shear doing its job: the environment sets the storm's *class*, and the
0.25 K noise cannot move it. Physically right, and worth saying out loud — it is the
opposite of the pulse cell in §5.1, where noise moved peak w by 35 %.

**Structure and placement diverge steadily.** Measured with metrics that need no
cell identification (pattern correlation of composite reflectivity over the echo
union; IoU of the ≥40 dBZ area; displacement of the ≥40 dBZ centroid):

| t (min) | corr | IoU@40 dBZ | centroid offset | ≥40 dBZ area (0 / 1) |
|---|---|---|---|---|
| 50 | 0.810 | 0.736 | 1.6 km | 323 / 316 |
| 70 | 0.722 | 0.657 | 12.0 km | 777 / 744 |
| 90 | 0.511 | 0.516 | 15.7 km | 1592 / 1325 |
| 120 | **0.397** | **0.417** | **18.7 km** | 3160 / 2451 (**−29 %**) |

Plus: peak w at t=30 differs by **+60 %** (26.2 vs 41.9 m/s) — the *timing* of
initial intensification is highly seed-sensitive even though the mature intensity is
not — and peak hail `qhl` differs by 40–80 % frame to frame (0.77 vs 1.37 g/kg at
t=70). Final-frame field divergence: mean |Δw| 0.80 m/s, **16.9 %** of voxels differ
by >1 m/s.

**So the character is: same storm type, same intensity class, genuinely different
individual storm** — different position, different size, different hail, different
split geometry. That is a better teaching story than "one supercells and one
doesn't" would have been: it is the honest forecast→outcome lesson the charter's
principle 2 asks for. The environment is predictable; the individual storm is not.

**Caveats, stated rather than buried.** (a) This is 1 km, not 333 m. At 333 m the
divergence would most likely be *larger* — finer grids carry more degrees of freedom,
and T6 already found the 333 m cell more vigorous than its 500 m twin — but that is
an expectation, not a measurement. (b) `sc_spread.py`'s per-mover tracker (argmax
within a y-half) jumps between cells and its separation column is **not** trustworthy;
the table above deliberately uses only identification-free metrics. (c) These runs use
`irandp=1`, whereas the shipped `supercell_333m` runs `irandp=0` — a seeded variant is
a new config, not a re-run of the shipped one.

## 6. What is gated permanently vs measured once

`pipeline/tests/test_seed_t4.py` — **15/15**, reading only committed files.

The run-level claims (§4) cannot live in git: they need the source tree, two
binaries and six CM1 runs. What is gated permanently is the half that can silently
rot — the scenario→deck contract, including all three silent-aliasing guards, the
`0.0`-vs-`0` float trap, and a check that `deck.SEED_NAMELIST_KEY` and the vendored
patch still agree on which `varN` carries the seed (repoint one without the other
and the seed silently stops working).

**The guards were verified to fire**, not merely to pass — four mutations of
`_seed_to_var7` were run against the committed suite:

| Mutation | Result |
|---|---|
| no validation at all (bare float cast) | **CAUGHT** (4 gates fail) |
| drops the negative-seed guard | **CAUGHT** |
| drops the `irandp=0` guard | **CAUGHT** |
| returns `int` instead of `float` | **CAUGHT** (byte-identity trap) |

Full suite after T4: `test_deck` 15/15, `test_manifest` 17/17,
`test_orientation_t3` 11/11, `test_regrid_cref` 13/13, `test_regrid_dbz` 3/3,
`test_regrid_w` 10/10, `test_scenario_t6` 11/11, `test_supercell_t2` 10/10,
`test_seed_t4` 15/15.

## 7. Does T4 ship packages? — RESOLVED: no (owner, 2026-07-28)

**Owner's call: ship nothing; proceed to T5.** T4 stands as *mechanism plus a
measured spread* — the fork, the `seed` key, the guards, and §5.2's numbers. No
seeded package is produced now; the machinery is in place to produce one at any
later point (the decision is reversible, and cheaply so for the single cell).

Recorded here because the deferral was itself a documented decision — leaving §7
reading "due" would misstate the state of the phase.

The evidence the call was made on, kept for the record, stated neutrally:

**For shipping two 333 m seeded supercells.** At t=120 the two storms sit ~19 km
apart with only 42 % echo overlap and 29 % different storm area, while both remain
unmistakably supercells — visibly different in the diorama picker, which is exactly
the A/B a "seed-driven variation" teaching asset wants. The mechanism, the box
discipline and the export path all already exist; nothing new has to be built.

**Against.** ~9 h of overnight runs plus an export cycle, for an asset whose *value*
is a side-by-side comparison the diorama cannot currently show side by side — the
Phase 2 T7 picker switches by page reload, one scenario at a time. And a seeded
supercell needs a new config (`irandp=1`, a measured box of its own) plus its own
bbox/run-health gate, which is T1/T2-shaped work, not a re-export.

**A cheaper middle option exists:** seed the *single cell* instead. `single_cell_333m`
is far quicker to run, and §5.1 shows the pulse cell is where seed sensitivity is
most dramatic (35 % peak-w swings, wholly different cells) — arguably the *better*
teaching demo of "same setup, different outcome", precisely because a supercell's
intensity is seed-robust.

Recommendation at the time: **the single-cell pair**, unless the supercell split
geometry is specifically what you want to teach with. The owner chose neither —
see the resolution at the head of this section.
