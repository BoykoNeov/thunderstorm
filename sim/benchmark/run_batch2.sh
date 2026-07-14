#!/bin/bash
# Batch 2: NSSL ptype=27 cost multiplier + binding check. Run AFTER batch 1.
echo "===== NSSL ptype=27 cost multiplier (1 km, 300 steps) vs Morrison ====="
cd /home/boiko/thunderstorm/runs/bench_nssl
rm -f cm1out*.nc; mpirun --oversubscribe -np 8  ./cm1.exe > run_np8.out  2>&1
rm -f cm1out*.nc; mpirun --oversubscribe -np 16 ./cm1.exe > run_np16.out 2>&1
echo "NSSL 1km np=8 :  $(grep 'Total time:' run_np8.out  | awk '{print $3}')  (Morrison was 44.47)"
echo "NSSL 1km np=16:  $(grep 'Total time:' run_np16.out | awk '{print $3}')  (Morrison was 35.12)"

echo "===== BINDING CHECK (500 m, np=8: pinned vs default) ====="
cd /home/boiko/thunderstorm/runs/bench500
rm -f cm1out*.nc
mpirun --bind-to core --map-by core -np 8 ./cm1.exe > run_np8_pinned.out 2>&1
echo "pinned exit=$?  Total_time=$(grep 'Total time:' run_np8_pinned.out | awk '{print $3}')"
echo "default np=8 was: $(grep 'Total time:' run_np8.out | awk '{print $3}')"
echo BATCH2_DONE
