#!/bin/bash
# 250 m production-candidate benchmark: 480x480x40, dtl=1.5, 300 steps, cells=9216000.
# np=8 (production choice) and np=16 (confirm the 8>16 crossover holds at finest res).
run_one () {   # $1=np
  cd /home/boiko/thunderstorm/runs/bench250
  rm -f cm1out*.nc
  mpirun --oversubscribe -np "$1" ./cm1.exe > "run_np$1.out" 2>&1
  tt=$(grep 'Total time:' "run_np$1.out" | awk '{print $3}')
  ok=$(grep -c 'terminated normally' "run_np$1.out")
  cps=$(echo "scale=0; 9216000 * 300 / $tt" | bc 2>/dev/null)
  printf "250 m  np=%-3s Total_time=%-12s cellsteps/s=%-10s normal=%s\n" "$1" "$tt" "$cps" "$ok"
}
echo "=== 250 m : 480x480x40, dtl=1.5, 300 steps, cells=9216000 ==="
run_one 8
run_one 16
echo BENCH250_DONE
