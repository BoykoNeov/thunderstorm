#!/bin/bash
# Same-rank reproducibility: run the 1 km deck twice at 8 ranks, compare fields.
cd /home/boiko/thunderstorm/runs/bench
rm -f cm1out*.nc repro1.nc repro2.nc
mpirun --oversubscribe -np 8 ./cm1.exe > repro1.out 2>&1
mv cm1out.nc repro1.nc
mpirun --oversubscribe -np 8 ./cm1.exe > repro2.out 2>&1
mv cm1out.nc repro2.nc
echo "--- field comparison (run1 vs run2, same 8-rank decomposition) ---"
python3 repro_compare.py repro1.nc repro2.nc
echo REPRO_DONE
