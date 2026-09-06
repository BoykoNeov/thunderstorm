# Output checksum baselines

One `sha256` line per CM1 output file, for every **shipped** scenario, sorted by
filename.

## Why these exist

The charter's data policy is deliberate and it has a hole this fills:

> raw netCDF is regenerable and never committed … packages are not backed up by git —
> regeneration from `sim/` + `pipeline/` is the recovery path

Raw output is **disposable by design**, and 240 GB of it currently sits in
`~/thunderstorm/runs/`. It is the only thing any reproducibility claim can be checked
against — so the first time someone reclaims that disk, every such claim becomes
uncheckable, permanently. Not just the Phase 3 T4 fork question, but the next compiler
bump, the next OpenMPI, the next netCDF.

These files are the part of that 240 GB worth keeping: ~100 KB that answers *"does this
still reproduce?"* after the run dirs are gone.

## What a baseline does and does not prove

- It proves **bitwise identity** — the strongest form, and the one the charter's
  Conventions section names first.
- It proves nothing about *why* two runs differ. A mismatch says which files diverge,
  not whether the cause is the binary, the rank count, the toolchain or the machine.
  That is a diagnosis, and it starts here rather than ending here.
- It is **rank-count specific.** Floating-point summation order changes with the
  decomposition, so a baseline is only comparable to a run at the same `np`. Every file
  below records it.

## Provenance

Every field below was **read off each run's own `namelist.input` and `run_meta.txt`**
on 2026-09-07, not carried over from a plan or a summary. "Grid" is the **CM1
simulation grid** (`nx`/`ny`/`nz` in the deck) — not the export crop box, which is a
different and smaller thing (`supercell_333m` exports 540×540×**54** voxels up to the
condensate top; it *simulates* on 40 stretched levels). Confusing the two is easy and
would make this table quietly wrong.

| File | Scenario | CM1 grid | Ranks | Binary | Files |
|---|---|---|---|---|---|
| `single_cell_500m.np8.sha256` | `single_cell_500m` | 160×160×40 @ 500 m | 8 | `5da2c2aa…` (stock, pre-fork) | 302 |
| `single_cell_333m.np8.sha256` | `single_cell_333m` | 240×240×40 @ 333 m | 8 | `5da2c2aa…` (stock, pre-fork) | 302 |
| `supercell_333m.np8.sha256` | `supercell_333m` | 540×540×40 @ 333 m | 8 | `5da2c2aa…` (stock, pre-fork) | 602 |

All three were produced by the **stock Phase 0 binary**, before the T4 fork — each run
directory keeps a copy of the binary that produced it, and all three hash `5da2c2aa…`.
That is what makes them usable as the *before* side of a fork-neutrality comparison
rather than merely a record of what happened.

`cm1out_stats.nc` is included alongside the numbered frames: it is model output like
any other, and excluding it would leave an unchecked file in every run.

## How to check a run against one

```sh
cd <run dir>
sha256sum cm1out_*.nc | sort -k2 > /tmp/got.sha256
diff /tmp/got.sha256 sim/baselines/<scenario>.np8.sha256 && echo IDENTICAL
```

The comparison is only meaningful at the recorded rank count, and only for a run whose
deck the production generator reproduces —
`pipeline/gen_deck.py --scenario <name> --verify <that run's namelist.input>`. Without
that, a difference could mean "different build" or "different deck", and the check
would not distinguish them.

## First use

Phase 3 T7's fork-neutrality gate (`sim/gates/t7_neutrality.sh`,
`docs/phase3-completion-2026-09-06.md` §2). The `single_cell_500m` list is that gate's
own comparison-2 baseline, written by the gate itself.
