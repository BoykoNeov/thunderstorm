# Thunderstorm Simulator

An education & outreach thunderstorm simulator. A **headless physics engine
([CM1](https://www2.mmm.ucar.edu/people/bryan/cm1/))** produces precomputed storm
scenarios; an **Unreal Engine 5** app plays them back with volumetric clouds,
lightning, rain/hail, selectable data layers, and teaching UI (sounding / indices
panels, annotations).

Progression of scenarios: **single-cell → multicell → supercell**, including modest
terrain.

> **Status: pre-implementation.** The architecture is designed and pressure-tested
> (see [`docs/`](docs/)); no simulation phase has started yet. This repository
> currently holds the project charter, science-provenance docs, and scaffolding.

## Core principles

1. **Physics through simulation.** Any parameter affecting storm development (CAPE,
   shear, moisture, terrain, seed) acts through the CM1 simulation — never scripted
   with empirical if-this-then-that rules. Diagnostic quantities (radar dBZ, lightning
   flash rate) are computed from simulated fields via published parameterizations,
   never fed back into the simulation, and are labeled as diagnostics in the UI.
2. **Legibility over photorealism.** The app teaches *why* storms form: annotations,
   comparisons, and honest "forecast → outcome" panels beat pretty rain.
3. **UE is a dumb player.** All science and derived quantities are computed in the
   pipeline (including skew-T / hodograph plots and lightning event lists). Unreal
   only renders scenario packages.
4. **Wall-clock matters.** Iterate coarse, render final once.

## Architecture

```
scenario config (JSON)
  → CM1               (WSL2 Ubuntu, headless)
  → netCDF            (WSL ext4)
  → Python pipeline   (xarray / MetPy: derived fields, regridding, decimation, VDB)
  → scenario package  (VDB sequence + surface textures + plots + event lists + manifest)
  → UE5 playback app  (Windows)
```

## Layout

| Path         | Purpose |
|--------------|---------|
| `sim/`       | Scenario configs, CM1 namelists, WSL run scripts |
| `pipeline/`  | Python post-processor (derived fields, regridding, VDB writing) |
| `scenarios/` | Finished scenario packages (versioned contract; multi-GB, out-of-repo/LFS) |
| `unreal/`    | UE5 playback project |
| `docs/`      | Science provenance (every parameterization cites its paper), reviews, decisions |

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — project charter: principles, architecture, technical
  decisions, constraints, and phasing.
- [`docs/advisor-review-2026-07-09.md`](docs/advisor-review-2026-07-09.md) — adversarial
  pressure-test of the plan (SVT limits, runtime budgets, moving-domain vs terrain
  incompatibility, VDB pipeline risk, and more).

## License

Licensed under the **Boyko Non-Commercial License v1.0 (BNCL-1.0)** — see
[`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Use, modification, and redistribution are
permitted for **non-commercial purposes** only; commercial use requires a separate
license from the copyright holder. This is a source-available (not OSI open-source)
license.

CM1 itself is separately licensed by NCAR; this project distributes scenario outputs
and glue code, not CM1's source.
