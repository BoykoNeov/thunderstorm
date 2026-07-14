#!/bin/bash
# Rank-scaling benchmark: 1 km supercell deck, 300 large steps (timax=1800, dtl=6).
cd /home/boiko/thunderstorm/runs/bench
CELLSTEPS=$((120*120*40*300))
echo "cell-steps per run = $CELLSTEPS  (120x120x40 grid x 300 steps)"
printf "%-4s %-10s %-16s %-8s %-12s\n" np wall_s cellsteps/s exit normal_ranks
for np in 4 6 8 16; do
  rm -f cm1out*.nc
  s=$(date +%s.%N)
  mpirun --oversubscribe -np "$np" ./cm1.exe > "run_np${np}.out" 2>&1
  rc=$?
  e=$(date +%s.%N)
  w=$(echo "$e - $s" | bc)
  cps=$(echo "scale=0; $CELLSTEPS / $w" | bc)
  ok=$(grep -c 'terminated normally' "run_np${np}.out")
  printf "%-4s %-10.2f %-16s %-8s %-12s\n" "$np" "$w" "$cps" "$rc" "$ok"
done
echo "SCALING_DONE"
