# Phase 0 — CM1 build provenance

Record of the CM1 build used for Phase 0. Keep current; every scenario package
must be able to cite the exact binary that produced it (charter: reproducibility).

## Version & source

- **CM1 release:** `cm1r21.1` (released 2024-03-24 — current release as of 2026-07-14)
- **Source tarball:** https://www2.mmm.ucar.edu/people/bryan/cm1/cm1r21.1.tar.gz
  (345,874,148 bytes; no registration required)
- **Extracted to (WSL ext4):** `/home/boiko/thunderstorm/build/cm1r21.1`

## Toolchain (WSL2 Ubuntu 24.04.4 LTS)

- gfortran 13.2.0 (`4:13.2.0-7ubuntu1`)
- Open MPI 4.1.6 (`4.1.6-7ubuntu2`) — `mpif90`
- netCDF C `libnetcdf.so.19` + Fortran `libnetcdff.so.7`
  (apt: `libnetcdf-dev`, `libnetcdff-dev`, `netcdf-bin`)
- Installed via `apt-get install gfortran make libopenmpi-dev openmpi-bin
  libnetcdf-dev libnetcdff-dev netcdf-bin`

## Build configuration (`src/Makefile`)

Parallelization: **MPI (distributed memory)**, GNU compiler section. NOT OpenMP.

- `FC = mpif90`
- `OPTS = -ffree-form -ffree-line-length-none -O2 -finline-functions -fallow-argument-mismatch`
- `CPP = cpp -C -P -traditional -Wno-invalid-pp-token -ffreestanding`
- `DM = -DMPI`

netCDF section (paths from `nf-config`; Ubuntu multiarch layout):

- `OUTPUTINC = -I/usr/include`
- `OUTPUTLIB = -L/usr/lib/x86_64-linux-gnu`
- `OUTPUTOPT = -DNETCDF -DNCFPLUS`
- `LINKOPTS  = -lnetcdf -lnetcdff`

Single precision is CM1's default (not changed). Decomposition: `nodex`/`nodey`
are **auto-determined** in cm1r21 (src/param.F: "cm1r20: nodex and nodey are
determined automatically"); MPI rank count is set at `mpirun -np N`. `nx=ny=120`
divides cleanly by 2/3/4/6/8 → 4/6/8-rank benchmarks all decompose without remainder.

## Binary

- **`run/cm1.exe` sha256 = `5da2c2aa49b9f226cedb5c833219d915dca71c4f328923e47cdbf596bab016bd`**
- `ldd` confirms dynamic linkage of `libnetcdff.so.7`, `libnetcdf.so.19`,
  `libmpi_mpifh.so.40`, `libmpi.so.40`.
- `run/onefile.F` archive retained alongside the binary (Bryan's recommended
  per-build code record).

## Smoke test (build validation gate — passed)

- Config: canonical `run/config_files/supercell` deck, shortened to `timax=12.0`,
  `tapfrq=6.0`, switched to `output_format=2` (netCDF), `output_filetype=2`.
- Run: `mpirun -np 4 ./cm1.exe` — all 4 ranks "Program terminated normally", exit 0.
- Output: valid netCDF frames `cm1out_000001..3.nc` (t=0/6/12 s) + `cm1out_stats.nc`.
  `ncdump -h` shows dims `time`(unlimited)/`zh`/`yh`/`xh`/`zf` and fields
  `th, prs, qv, dbz, uinterp, vinterp, winterp, w` with `(time,z,y,x)` shape.
- The `IEEE_UNDERFLOW_FLAG`/`IEEE_DENORMAL` notes at STOP are harmless informational
  messages from gfortran, not errors.
- Working dir: `/home/boiko/thunderstorm/runs/smoke`.

## Notes for downstream

- CM1 netCDF `output_filetype`: `1` = single file all times (`cm1out.nc`),
  `2` = one file per output time (`cm1out_NNNNNN.nc`), `3` = per-node-per-time.
- The canonical supercell deck uses **ptype=5 (Morrison)**, not production
  **NSSL ptype=27**. Kept as-is for validation-vs-reference; NSSL is a later
  production-config change (charter), not part of the WK validation baseline.
