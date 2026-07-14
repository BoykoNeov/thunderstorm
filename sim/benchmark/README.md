# Phase 0 throughput benchmark — scripts & decks

Provenance for [`docs/phase0-benchmark.md`](../../docs/phase0-benchmark.md).
These ran in WSL under `/home/boiko/thunderstorm/runs/`; raw netCDF output is
disposable (charter data policy) and not committed — only the reproducible
decks and scripts are.

All timings use CM1's own `timestats=1` "Total time:" integration clock.
Throughput = `cells × large-steps ÷ Total time` (cell-steps/s). Runs were
executed **serially on a dedicated machine** (BOINC + Docker down) so each
timing reflects uncontended cache/bandwidth.

## Scripts
- `bench_scaling.sh` — 1 km Morrison rank scaling (np=4/6/8/16).
- `bench_fineres.sh` — 500 m & 333 m rank scaling (the resolution-dependent
  SMT crossover).
- `bench250.sh` — 250 m production-candidate run (np=8 vs np=16).
- `bench_nssl_mature.sh` — **the extrapolation anchor**: mature 1 km NSSL
  (`ptype=27`) to 2 h, np=8. Folds maturity + scheme cost into one measured
  throughput number.
- `repro.sh` + `repro_compare.py` — bitwise reproducibility (1 km np=8 twice,
  full-field `np.array_equal` over all variables).
- `run_batch1.sh` (repro + fine-res) / `run_batch2.sh` (NSSL multiplier +
  np=8 pinned-vs-default binding check) — batch drivers.

## Decks (`decks/`)
Exact `namelist.input` for each grid. All are WK supercell decks derived from
the validation deck; they differ only in `nx/ny`, `dx/dy`, `dtl`, `timax`, and
(for `bench_nssl_mature`) `ptype=27`. `tapfrq=9999` on the timed runs to remove
I/O from the measurement.

## Headline results (see the doc for the full tables)
- Rank count: **np=8** (NSSL np=16 is 55% slower at 1 km; the coarse-res Morrison
  16-rank win is a V-cache artifact that vanishes at production resolution).
- No explicit core binding (pinning is 15% slower at 500 m).
- Reproducibility: **bitwise** (`max_abs_diff = 0`, 56 vars).
- Final resolution: **333 m default**, 250 m for flat/imove hero runs, 500 m
  preview.
