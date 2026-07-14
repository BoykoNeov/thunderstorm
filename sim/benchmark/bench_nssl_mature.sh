#!/bin/bash
# Mature 1 km NSSL (ptype=27) to 2 h: folds maturity AND scheme into one measured anchor.
# 120x120x40, dtl=6, timax=7200 -> 1200 steps, cells=576000, np=8 (production choice).
cd /home/boiko/thunderstorm/runs/bench_nssl_mature
rm -f cm1out*.nc
mpirun --oversubscribe -np 8 ./cm1.exe > run_np8.out 2>&1
tt=$(grep 'Total time:' run_np8.out | awk '{print $3}')
ok=$(grep -c 'terminated normally' run_np8.out)
cps=$(echo "scale=0; 576000 * 1200 / $tt" | bc 2>/dev/null)
printf "mature NSSL 1km np=8  Total_time=%-12s cellsteps/s=%-10s normal=%s\n" "$tt" "$cps" "$ok"
echo "(compare: mature 1km MORRISON validation = ~3.40M cellsteps/s)"
echo NSSL_MATURE_DONE
