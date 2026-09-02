# sim/

Scenario configs, the CM1 deck template, and the generic run script.

CM1 raw output (netCDF) is written to **WSL ext4**, never through `/mnt/*`, and is
never committed (regenerable, disposable by design). Only finished scenario packages
are copied out to durable storage.

## Layout

| Path | What it is |
|---|---|
| `scenarios/<name>.json` | **The single source of truth for a scenario.** Feeds both the CM1 deck generator and the post-processor, so a scenario cannot be simulated with one geometry and exported with another. |
| `templates/base.namelist.input` | The validated Phase 0 deck. ~8 KB of numerics, boundary conditions, SGS constants and the NSSL block that must not drift. A scenario overrides ~17 of its 413 lines; the rest stay byte-identical. |
| `run_scenario.sh` | Generic runner: generate deck (+ `input_sounding` for `isnd=7` scenarios) → stage binary → run → write `run_meta.txt` (binary sha256, sounding sha256, grid, provenance). |
| `probes/` | Throwaway diagnostic runs, never exported — the T5 multicell probes and the T5s external-sounding controls + shear sweep (`probes/README.md`). |
| `cm1-patches/` | The CM1 fork: patches over the pinned upstream tarball, with the provenance hash table that every other file quoting a binary hash is gated against. |
| `single_cell/namelist.input` | The hand-written Phase 1 deck. **Kept as the generator's regression reference** (`gen_deck.py --verify`), not as an input to any run. |
| `validation/`, `benchmark/` | Phase 0 artifacts. |

## Running a scenario

```bash
# from Windows
wsl -d Ubuntu -- bash /mnt/m/claud_projects/thunderstorm/sim/run_scenario.sh <name>
# validate the deck without burning the wall clock
bash run_scenario.sh <name> --dry-run
```

The runner reads `run_dir`, the grid line and the provenance block **through the
pipeline's own scenario loader** (`pipeline/scenario_info.py`), never with `grep`.
That is the point: `run_meta.txt` is generated from the same object the export reads,
so it cannot describe a different run than the one that executed.

Two refusals happen before CM1 starts, when they cost seconds instead of hours:

- `run_dir` under `/mnt/*` — raw output on the 9P bridge (charter data policy).
- an output flag the exporter needs is off — `deck.check_output_flags` catches the
  failure mode where a run completes and only then turns out to have written no `dbz`.

## Adding a scenario

1. Copy an existing `scenarios/<name>.json`. `sim.namelist` must declare **all**
   `REQUIRED_KEYS` (deliberately not defaulted from the template) and may declare
   nothing else — unrecognised keys are refused, since a typo would otherwise be
   silently ignored.
2. Leave `export` marked `"_provisional": true` with any placeholder box. **The crop
   box is an output of the run, not an input** — it is measured from that run's own
   active-voxel union. `export`/`export-web` refuse a provisional box; `bbox` and deck
   generation deliberately do not, or every new scenario would deadlock before it
   could produce the data its box is measured from.
3. Run it, then `export_scenario.py bbox` to measure the union, write the padded box
   back into `export`, and drop the flag.

Padding rule: size the **symmetric** box to the max extent over all four horizontal
directions. Never re-centre it on a drifting cell — the SVT bounding-box centre must
be static across the sequence, and a symmetric box about (0,0) satisfies that by
construction rather than by luck.

## Scenarios today

| Name | Grid | Notes |
|---|---|---|
| `single_cell_500m` | 160² × 40 @ 500 m | Phase 1 spike dataset. Zero-shear pulse cell. |
| `single_cell_333m` | 240² × 40 @ 333 m | Phase 2 T6. The **same** cell at finer resolution — vertical grid, sounding, shear, initiation, microphysics, duration and output cadence are all identical, so resolution is the only variable and any visible difference is attributable to it. |
| `supercell_333m` | 540² × 40 @ 333 m, `imove=1` | Phase 3 T1. The Phase 0 WK splitting supercell on NSSL microphysics in a Bunkers-tracked moving frame; measured box = the full domain (the anvil fills it). Run + box validated; package export is T2/T3 territory. |

### Scenarios with an external sounding (`isnd=7`)

From Phase 3 T5s on, a scenario may carry a `sim.sounding` block instead of relying on
CM1's analytic `isnd=5` sounding and its three fixed `iwnd` wind profiles. The block is
rendered to `input_sounding` by `pipeline/gen_sounding.py` (WK82 thermodynamics, a
capping-inversion CIN knob with CAPE held, tanh/linear wind profiles with free shear
magnitude and depth); `run_scenario.sh` stages the file beside the deck and records its
sha256. Rules, enforced by `deck.py`: the block and `isnd=7` appear together or not at
all, and `iwnd` must be 0. See `sim/probes/configs/t5s_*.json` for worked examples and
`docs/plan-science-hurdles-2026-09-02.md` for the gates a first `isnd=7` run must pass.
