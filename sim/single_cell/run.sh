#!/usr/bin/env bash
# Run the Phase 1 single-cell scenario in WSL Ubuntu.
#
# Output (netCDF) is written to WSL ext4 under runs/ — NEVER through /mnt/*
# (charter data policy: the 9P bridge is slow and raw output is large/disposable).
# Only a finished scenario package is ever copied out to M: later, by the pipeline.
#
# Usage (from Windows):  wsl -d Ubuntu -- bash /mnt/m/claud_projects/thunderstorm/sim/single_cell/run.sh
# Usage (inside WSL):    bash run.sh
set -euo pipefail

# Resolve this script's own directory (works whether invoked from /mnt or ext4).
SELFDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CM1_EXE="/home/boiko/thunderstorm/runs/cm1.exe"   # validated cm1r21.1 binary (see docs/phase0-cm1-build.md)
RUNDIR="/home/boiko/thunderstorm/runs/singlecell" # ext4 — raw output lives here
NRANKS=8                                           # locked by Phase 0 benchmark gate

if [[ ! -x "$CM1_EXE" ]]; then
  echo "ERROR: cm1.exe not found at $CM1_EXE" >&2
  exit 1
fi

mkdir -p "$RUNDIR"
cp "$CM1_EXE" "$RUNDIR/cm1.exe"
cp "$SELFDIR/namelist.input" "$RUNDIR/namelist.input"
cd "$RUNDIR"

# Reproducibility provenance (charter Conventions: binary hash, rank count, decomposition).
{
  echo "scenario         : single_cell (Phase 1 plumbing)"
  echo "cm1_binary_sha256: $(sha256sum cm1.exe | awk '{print $1}')"
  echo "nranks           : $NRANKS"
  echo "grid             : nx=160 ny=160 nz=40  dx=dy=500 m  ztop=18 km"
  echo "microphysics     : NSSL 2-moment ptype=27 (true hail)"
  echo "shear/motion     : iwnd=0 (zero shear), imove=0 (stationary)"
  echo "init             : iinit=1 warm bubble (init3d.F defaults: 10 km / 1.4 km / +1 K at center)"
  echo "random_seed      : none (irandp=0 — deterministic)"
  echo "openmpi          : $(mpirun --version 2>/dev/null | head -1)"
} | tee run_meta.txt

rm -f cm1out*.nc cm1out.nc

echo "=== launching CM1: mpirun -np $NRANKS ./cm1.exe ==="
time mpirun -np "$NRANKS" ./cm1.exe > cm1.out 2>&1
echo "=== CM1 finished; tail of cm1.out ==="
tail -n 20 cm1.out
echo "=== output files ==="
ls -lh cm1out*.nc 2>/dev/null | tail -5 || ls -lh *.nc 2>/dev/null | tail -5
echo SINGLECELL_DONE
