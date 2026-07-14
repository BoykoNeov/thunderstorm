# Phase 0 — Throughput benchmark & final-resolution gate

**Deliverable: a resolution *decision*, not a single hour figure.**

- **Realistic production final resolution: 333 m** — overnight-able in every
  configuration (flat ~2.4 h, terrain ~7 h for a 2 h storm), including terrain.
- **250 m reserved for flat/imove "hero" runs** (no terrain): ~7 h for a 2 h
  storm — feasible — but ~19–28 h with terrain, i.e. NOT reliably overnight.
- **500 m is the fast-iteration / preview tier**: <1 h flat, ~2 h terrain.
- **Rank count: `mpirun -np 8`.** No explicit core binding. NSSL `ptype=27`.
- **Reproducibility: bitwise.** The charter contract stays at the strong tier.

This confirms the charter's a-priori guidance ("333–500 m may be the realistic
final; 250 m is the reach") with measured numbers, and correctly attributes the
charter's "15–30 h @ 250 m" planning figure to the **terrain / large-domain**
configuration.

All timings use CM1's own `timestats=1` "Total time:" integration clock (not
wall-clock date-diff), on the clean machine (BOINC + Docker down). Throughput
metric = `cells × large-steps ÷ Total time` in **cell-steps/s**.

---

## 1. Rank scaling — and the SMT surprise, resolved

Morrison (`ptype=5`), early storm (300 large steps), cell-steps/s:

| Resolution | grid | np=4 | np=6 | np=8 | np=16 | fastest |
|---|---|---|---|---|---|---|
| 1 km | 120²×40 | 3.09M | 3.66M | 3.89M | **4.92M** | 16 (+26%) |
| 500 m | 240²×40 | — | 3.50M | 3.76M | **4.26M** | 16 (+13%) |
| 333 m | 360²×40 | — | — | **3.40M** | 3.06M | 8 (+11%) |
| 250 m | 480²×40 | — | — | 2.88M | **3.00M** | 16 (+4%) |

The a-priori assumption was "SMT likely useless — memory-bound." What the data
shows is subtler: at **1 km** the per-rank working set fits the 7800X3D's 96 MB
3D V-cache, the code is **cache-bound**, and 16 SMT threads win by 26%. As
resolution refines, the working set outgrows cache, the code becomes
**memory-bandwidth-bound**, and the SMT advantage collapses to noise
(±10%, no consistent winner at ≤333 m).

**But this whole table is Morrison.** Production uses NSSL 2-moment
(`ptype=27`), which is far heavier per cell — see §2 — and there np=16 loses
decisively. So the production rank choice is **np=8**, and the Morrison
fine-res oscillation is moot.

### Binding is not the explanation, and pinning hurts
500 m, np=8: default OpenMPI mapping **183.76 s** vs `--bind-to core --map-by
core` **212.27 s** — explicit pinning is **15% slower**. The default placement
is already good on this hybrid-topology single node. **Decision: no explicit
binding.** The coarse-res 16>8 effect is a genuine cache/SMT phenomenon, not a
placement artifact.

---

## 2. NSSL `ptype=27` is much more expensive than Morrison — and it grows with maturity

Production microphysics is NSSL 2-moment with a true hail category (`ptype=27`);
the validation and scaling runs used Morrison (`ptype=5`). The cost ratio is not
constant — it **increases as hydrometeors accumulate**, because NSSL has far
more work once there is actual graupel/hail to process:

| Comparison (1 km, np=8) | Morrison | NSSL | NSSL/Morrison |
|---|---|---|---|
| Early storm (300 steps) | 44.47 s | 54.48 s | **1.22×** |
| **Mature, 2 h run** | 3.40M cs/s | **2.45M cs/s** | **1.39×** |

Measuring the mature ratio directly was essential: composing an *early-storm*
scheme ratio (1.22×) with a Morrison maturity factor would have **under-counted**
production cost — the dangerous direction for a gate. The mature 2 h NSSL run
(**2.45M cell-steps/s @ 1 km, np=8**) folds maturity *and* scheme into one
measured anchor.

NSSL also kills SMT: NSSL 1 km np=16 = 84.68 s, **55% slower** than NSSL np=8
(54.48 s). Heavier per-cell work → more memory traffic → oversubscription hurts.
This is the decisive argument for np=8 in production.

---

## 3. Reproducibility — bitwise

1 km, np=8, run twice with the identical 8-rank decomposition, full-field
compare across all 56 output variables:

```
compared 56 vars; bitwise_identical = True; max_abs_diff = 0
```

The charter's reproducibility contract stays at the **strong (bitwise)** tier —
no downgrade to statistical-equivalence needed. (Verified once at 1 km / Morrison /
fixed 8-rank decomposition, as the charter asks; CM1 determinism is scheme- and
resolution-independent, but this was not separately re-tested at the NSSL / 333 m
production config.) Every scenario still records
seed(s), binary hash, rank count, and decomposition (§ charter Conventions).

---

## 4. Extrapolation to production wall-clock

**Method** (per advisor guidance — replace composed guesses with one measured
anchor + one measured ratio):

```
production throughput(R) = mature_NSSL_1km × resolution_derating(R)
```

- **Anchor:** mature NSSL 1 km np=8 = **2.45M cell-steps/s** (§2, measured).
- **Resolution derating**, measured from the early-Morrison np=8 runs (§1),
  relative to 1 km — assumed scheme-independent (it reflects
  working-set-vs-cache/bandwidth scaling, similar for both schemes):

  | R | 1 km | 500 m | 333 m | 250 m |
  |---|---|---|---|---|
  | derating | 1.00 | 0.966 | 0.874 | **0.740** |
  | ⇒ mature-NSSL cs/s | 2.45M | 2.37M | 2.14M | **1.81M** |

**Run cost** = `cells × steps ÷ throughput`. Fixed inputs: nz=40, ztop=18 km,
2 h storm time, CFL-limited `dtl` (fixed-step; see caveat). Two domain regimes:

- **Flat / imove** (120 km box, moving domain) — validated to hold the 2 h
  split with 26 km edge clearance (§5).
- **Terrain / large** (200 km box, no imove — `imove` is incompatible with
  terrain). **200 km is a placeholder, not a measurement:** a storm translating
  ~13 m/s ground-relative covers ~93 km in 2 h, plus ~46 km split spread, so
  200 km may be tight in the travel direction and terrain domains want to be
  non-square — validate per-scenario in Phase 3. (The flat numbers are measured;
  the terrain numbers are order-of-magnitude sizing.)

| Res | dtl | steps | flat cells | **flat 2 h** | terrain cells | **terrain 2 h** |
|---|---|---|---|---|---|---|
| 500 m | 3.0 s | 2400 | 2.30M | **0.65 h** | 6.40M | **1.8 h** |
| 333 m | 2.0 s | 3600 | 5.18M | **2.4 h** | 14.4M | **6.7 h** |
| 250 m | 1.5 s | 4800 | 9.22M | **6.8 h** | 25.6M | **18.9 h** |

For a **3 h** storm multiply by 1.5 (e.g. terrain 250 m → ~28 h; flat 250 m →
~10 h; terrain 333 m → ~10 h).

**Reconciliation with the charter's "15–30 h @ 250 m":** that figure is the
**terrain 250 m** case (18.9 h @ 2 h → 28 h @ 3 h). Confirmed, and now
attributed to the right configuration.

### Caveats (do not chase — sizing, not precision)
- **adapt_dt:** benchmarks used fixed `dtl` (`adapt_dt=0`); production uses
  `adapt_dt`, which can *raise* the step count at fine resolution during peak
  updrafts. The step counts above are therefore lower bounds → real cost skews
  slightly higher, especially at 250 m.
- **Derating is scheme-independent by assumption.** If NSSL's bandwidth
  footprint derates faster than Morrison's, fine-res throughput is optimistic.
- **nz=40 fixed.** More vertical levels scale cost linearly.
- The resolution decision is robust to a **1.5× error** in these factors: 333 m
  stays overnight-able in both regimes; terrain 250 m does not. That robustness —
  not the two-sig-fig hours — is the gate's actual output.

---

## 5. Domain containment (flat / imove) — measured

The validation run *is* the flat/imove production config (120 km moving domain,
Bunkers `umove=12.5, vmove=3.0`, full 2 h). Tracking the two dominant updraft
cores (left/right movers) and their distance to the nearest domain edge
([`sim/validation/containment.py`](../sim/validation/containment.py)):

| t (min) | #cores | right mover (x,y) | edge | left mover (x,y) | edge | sep (km) |
|---|---|---|---|---|---|---|
| 75 | 2 | (−2.5, 3.5) | 56 | (−10.5, 19.5) | 40 | 17.9 |
| 90 | 2 | (−0.5, 0.5) | 59 | (−13.5, 24.5) | 35 | 27.3 |
| 105 | 4 | (−0.5, −2.5) | 57 | (−10.5, 25.5) | 34 | 29.7 |
| 120 | 5 | (4.5, −5.5) | 54 | (−20.5, 33.5) | **26** | 46.3 |

The imove frame tracks the right (dominant) mover, which stays near center; the
**left mover** is the one racing toward the boundary. Closest approach over 2 h:
**26 km** — well beyond the ~10 km storm-core clearance rule. **120 km holds the
2 h flat split.** The margin is shrinking (extrapolates to ~10 km by 3 h), so
120 km is solid at 2 h and **marginal at 3 h** — use 140–160 km for a 3 h flat
scenario (which raises flat cost ~1.4–1.8×, still well under the terrain figures).

---

## 6. Machine & method notes

- Ryzen 7800X3D (8C/16T, 96 MB 3D V-cache), 64 GB, `.wslconfig` memory=48 GB,
  processors=16. WSL2 Ubuntu 24.04, OpenMPI 4.1.6, CM1 cm1r21.1
  (see [phase0-cm1-build.md](phase0-cm1-build.md)).
- MPI (not OpenMP), single node, `--oversubscribe` only for the np=16 SMT runs.
- Each throughput run: `rm -f cm1out*.nc` first, `tapfrq=9999` (no I/O), fixed
  300 large steps (except the mature 2 h anchor and the validation run). Runs
  were executed **serially on a dedicated machine** — never concurrently — so
  each Total-time reflects uncontended cache/bandwidth.
- Raw netCDF from benchmark runs is disposable (charter data policy) and not
  committed; the reproducible decks and analysis scripts are.

## 7. What this closes / opens

- **Closes the Phase 0 benchmark gate.** Final resolution is chosen from
  measurement: **333 m default, 250 m for flat hero runs, 500 m preview.**
- Feeds the **Pinned versions** table: production is `-np 8`, NSSL `ptype=27`,
  no core binding.
- **Phase 1 pipeline sizing:** a 333 m / 2 h flat scenario is ~2.4 h of compute —
  cheap enough to regenerate freely during the VDB/SVT de-risking spike. The
  frame-count for SVT streaming (charter's ~30–50 MB/frame budget) is set by
  `tapfrq`, independent of these throughput numbers.
