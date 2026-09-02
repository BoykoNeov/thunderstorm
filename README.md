# Thunderstorm Simulator

An education & outreach thunderstorm simulator. A **headless physics engine
([CM1](https://www2.mmm.ucar.edu/people/bryan/cm1/))** produces precomputed storm
scenarios; an **Unreal Engine 5** app plays them back with volumetric clouds,
lightning, rain/hail, selectable data layers, and teaching UI (sounding / indices
panels, annotations).

Progression of scenarios: **single-cell → multicell → supercell**, including modest
terrain.

> **Status (2026-09-02): Phase 3 in progress.** Phases 0–2 are complete: CM1 is
> built, benchmarked and bitwise-reproducible; the netCDF → VDB/web pipeline runs
> end to end; two single-cell scenario packages and a supercell run exist; the
> Storm Diorama web viewer plays them with selectable layers and a radar plan view.
> Phase 3 (supercell · seed variation · multicell) is at the multicell task, whose
> blocker and proposed fix are in
> [`docs/plan-science-hurdles-2026-09-02.md`](docs/plan-science-hurdles-2026-09-02.md).
> One-line-per-phase table: [`CLAUDE.md`](CLAUDE.md#status--phasing); full record:
> [`docs/STATUS.md`](docs/STATUS.md).

## Core principles

1. **Physics through simulation.** Any parameter affecting storm development (CAPE,
   shear, moisture, terrain, seed) acts through the CM1 simulation — never scripted
   with empirical if-this-then-that rules. Diagnostic quantities (radar dBZ, lightning
   flash rate) are computed from simulated fields via published parameterizations,
   never fed back into the simulation, and are labeled as diagnostics in the UI.
2. **Legibility over photorealism.** The app teaches *why* storms form: annotations,
   comparisons, and honest "forecast → outcome" panels beat pretty rain.
3. **UE is a dumb player** — and so is the web viewer. All science and derived
   quantities are computed in the pipeline (including skew-T / hodograph plots and
   lightning event lists). The players only render scenario packages.
4. **Wall-clock matters.** Iterate coarse, render final once.

## Architecture

```
scenario config (JSON)  ── sim/scenarios/<name>.json, the single source of truth
  → generated CM1 deck (+ generated input_sounding for isnd=7 scenarios)
  → CM1               (WSL2 Ubuntu, headless, MPI np=8)
  → netCDF            (WSL ext4, never /mnt/*)
  → Python pipeline   (derived fields, linear-Z dBZ, updraft w, composite reflectivity,
                       regridding, decimation, VDB + web bricks)
  → scenario package  (VDB sequence + web bricks + manifests; plots/event lists later)
  → players           Storm Diorama (web, TS + WebGL2) today; UE5 app deferred
```

## Layout

| Path         | Purpose |
|--------------|---------|
| `sim/`       | Scenario configs, the CM1 deck template + generator inputs, the generic runner, CM1 fork patches, probe configs |
| `pipeline/`  | Python post-processor: `cm1post/` (contract, scenario, deck, sounding, regrid, export writers) + CLIs + `tests/` |
| `scenarios/` | Finished scenario packages — in-tree, payload out of git history, only the manifests tracked (no LFS) |
| `diorama/`   | Storm Diorama web viewer (TypeScript + WebGL2, no engine) — the current player |
| `unreal/`    | UE5 playback project (deferred; empty) |
| `docs/`      | Science provenance, plans, decision records, per-task reports — index in `docs/README.md` |

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — project charter: principles, architecture, technical
  decisions, constraints, pinned versions, conventions, phase table, open owner calls.
- [`docs/README.md`](docs/README.md) — index of every document by kind (plans,
  decision records, task reports, method rules).
- [`docs/STATUS.md`](docs/STATUS.md) — the full per-task status log.
- [`docs/plan-science-hurdles-2026-09-02.md`](docs/plan-science-hurdles-2026-09-02.md)
  — the open scientific hurdles, ranked, and the proposed way through each.
- [`docs/advisor-review-2026-07-09.md`](docs/advisor-review-2026-07-09.md) — adversarial
  pressure-test of the original plan.

## Running the tests

Every gate reads only committed files (no CM1 output, no WSL, no network):

```bash
for t in pipeline/tests/test_*.py; do python3 "$t" | tail -1; done
```

## License

Licensed under the **Boyko Non-Commercial License v1.0 (BNCL-1.0)** — see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Use, modification, and redistribution are
permitted for **non-commercial purposes** only; commercial use requires a separate
license from the copyright holder. This is a source-available (not OSI open-source)
license.

CM1 itself is separately licensed by NCAR; this project distributes scenario outputs
and glue code, not CM1's source.
