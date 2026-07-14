# pipeline/

Python post-processor: netCDF → derived fields → Cartesian regridding → decimation →
VDB sequence + surface-layer textures + skew-T/hodograph plots + lightning event lists
→ scenario package.

## VDB writer implementation (decision pending)

`pyopenvdb` is the flakiest link in the pipeline (stale PyPI wheels; source builds are
tedious). Candidate implementations, in order of robustness:

1. **Standalone C++ dense-array → VDB converter** (~200 lines) that the Python pipeline
   shells out to — most robust; recommended.
2. Ubuntu `python3-openvdb` apt package inside WSL (pin distro Python to match).
3. conda-forge `openvdb`.

The chosen approach will be documented here once implemented. The scenario-package
format is a **versioned contract** — see `scenarios/`.

## Coordinate/units contract

CM1 is SI / meters / z-up / right-handed; UE is centimeters / z-up / left-handed
(Y flip). This conversion lives in **exactly one** pipeline module.

_Empty until Phase 1 (pipeline de-risking spike). Do not start a phase without
explicit go from the owner._
