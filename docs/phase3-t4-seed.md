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

*(§5.2 measured separately at 1 km / 179.82 km domain / 2 h, the same domain and
window as `supercell_333m`, with `iwnd=2`/`imove=1` — see §7.)*

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

## 7. Open: does T4 ship packages?

Deferred to the owner by design (§ header). Pending on §5.2.
