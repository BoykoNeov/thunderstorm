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
| `export_scenario.py` | CLI driver — `bbox` (verify the padded box) and `export` (write the sequence). |
| `cm1post/config.py` | **The export contract.** Channel map, thresholds, crop box, resolution, origin. Every number is load-bearing. |
| `cm1post/fields.py` | CM1 variables → render channels. The *only* place CM1 names appear. |
| `cm1post/regrid.py` | Resample CM1 grid → fixed export box. |
| `cm1post/densevol.py` | `.densevol` writer (the handoff `dense2vdb` consumes). |
| `cm1post/manifest.py` | Scenario-package manifest — the contract UE reads. |
| `vdbwriter/` | C++ `dense2vdb` + `vdb_inspect`. See its own README. |

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
