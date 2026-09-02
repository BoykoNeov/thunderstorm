# pipeline/

Python post-processor: netCDF → derived fields → Cartesian regridding → decimation →
VDB sequence + surface-layer textures + skew-T/hodograph plots + lightning event lists
→ scenario package.

**Phase 1 scope (task 5, implemented):** the *volume* half — CM1 netCDF → VDB sequence
+ `manifest.json`. Surface-layer textures, MetPy plots and lightning event lists are
Phase 2/4; they attach to the same manifest.

## Layout

| Path | Role |
|---|---|
| `export_scenario.py` | CLI driver — `bbox` (measure/verify the padded box), `export` (VDB sequence + manifest), `export-web` (web bricks + web manifest). Takes `--scenario`. |
| `gen_deck.py` | Scenario JSON → CM1 `namelist.input` (template + overrides; `--verify` against a committed deck). |
| `gen_sounding.py` | Scenario JSON `sim.sounding` → CM1 `input_sounding` for `isnd=7`, plus the environment diagnostics JSON (CAPE/CIN/BRN/regime prediction). |
| `scenario_info.py` | Exposes config fields to `sim/run_scenario.sh` through the real loader (never grep). |
| `cm1post/contract.py` | **The package contract**, frozen per `format_version`: channel names/order, source fields, thresholds, SVT texture map, `WEB_FORMAT_VERSION`. |
| `cm1post/scenario.py` | Per-scenario config: run dir, export voxel, crop box (grid derived, never declared), `sim.namelist`, `sim.sounding`. |
| `cm1post/deck.py` | Deck generator: six key categories, line-anchored substitution, output-flag assertion, seed→`var7`, isnd=7⇔sounding coupling. |
| `cm1post/sounding.py` | Environment generator: WK82 thermodynamics, capped-mixed-layer CIN knob with CAPE held, tanh/linear winds, parcel CAPE/CIN, BRN + WK82 regime prediction, `input_sounding` writer/reader. Every formula cites its paper in the module docstring. |
| `cm1post/fields.py` | CM1 variables → render channels. The *only* place CM1 names appear. |
| `cm1post/regrid.py` | Resample CM1 grid → fixed export box (`resample` clips ≥0; `resample_signed` for `w`; `resample_dbz` in linear Z; `resample_dbz_2d` for `cref`). |
| `cm1post/densevol.py` | `.densevol` writer (the handoff `dense2vdb` consumes). |
| `cm1post/webvol.py` | Web bricks (`rgba`, `dbz`, `w`, `cref`) + `web_manifest.json`. |
| `cm1post/manifest.py` | Scenario-package manifest — the contract UE reads. |
| `vdbwriter/` | C++ `dense2vdb` + `vdb_inspect`. See its own README. |
| `tests/` | Gate scripts, one per task, each with negative controls; all read only committed files. |

## Usage (inside WSL)

```bash
export LD_LIBRARY_PATH=$HOME/micromamba/envs/vdb/lib   # for dense2vdb
cd /mnt/m/claud_projects/thunderstorm/pipeline

# 1. Verify the padded box still contains every frame (~50 s over 301 frames)
python3 export_scenario.py bbox --run /home/boiko/thunderstorm/runs/singlecell

# 2. Export the sequence (~3.5 s/frame)
python3 export_scenario.py export \
    --run /home/boiko/thunderstorm/runs/singlecell \
    --out /home/boiko/thunderstorm/scenario_out/single_cell_500m
```

Deps: system `python3` + `numpy`, `scipy`, `netCDF4` (analysis stack). The VDB write is
shelled out to `dense2vdb`, so the pipeline needs **no** OpenVDB Python binding — that
was the point of the C++ converter (see `vdbwriter/README.md`). It does still need the
env's **shared libraries** at export time, which is what the `LD_LIBRARY_PATH` above is
for: the `vdb` env is a runtime dependency, not build-time-only.

Exact versions both envs ran on: **`ENVIRONMENT.md`** (+ `env-vdb.yml`). Note there is
deliberately no `requirements.txt` — the reasoning is in that file.

## VDB writer implementation (DECIDED — 2026-07-14)

Path **#1** from the original candidate list: a standalone C++ dense-array → VDB
converter the Python pipeline shells out to. `pyopenvdb` was never adopted — stale PyPI
wheels, tedious source builds. Implementation + toolchain: `vdbwriter/README.md`
(conda-forge openvdb 13.0.0, userspace micromamba, no sudo). Validated end-to-end on
real CM1 frames in task 5.

## Coordinate/units contract

CM1 is SI / metres / z-up / right-handed; UE is centimetres / z-up / left-handed
(Y flip).

**The VDB carries CM1-native SI metres** — the shared linear transform's translation is
the true CM1 world coordinate of voxel (0,0,0)'s centre. The metres→centimetres and
Y-flip conversion is applied at **UE actor placement**, which is the single conversion
site (see `docs/phase1-task3-svt-import.md`). Nothing in this package converts units.

## Two invariants worth not breaking

1. **One threshold, shared code.** The padded bbox is sized to the active region *at the
   thresholds in `config.py`*. Export at a lower (more inclusive) threshold and
   condensate falls outside the box and is silently clipped. `bbox` and `export` both
   build channels through `fields.build_channels`, so they cannot drift apart — but if
   you change a threshold, **re-run `bbox`**. It is a gate, not a formality: the original
   40 km box in `docs/phase1-svt-budget.md` clipped the real storm.
2. **Linear interpolation only.** `regrid.py` uses `RegularGridInterpolator` (linear).
   Cubic resampling (`scipy.ndimage.map_coordinates`' default `order=3`) overshoots at
   sharp echo edges and manufactures **negative mixing ratios** — water no simulation
   produced. Output is clamped at 0 as a second guard.
