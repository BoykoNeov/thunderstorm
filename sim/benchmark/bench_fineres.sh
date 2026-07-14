#!/bin/bash
# Fine-resolution rank scaling, timed with CM1's own "Total time" (integration clock).
# 300 large steps each; cells = nx*ny*nz.
run_one () {   # $1=dir  $2=cells  $3=np
  cd "$1"
  rm -f cm1out*.nc
  mpirun --oversubscribe -np "$3" ./cm1.exe > "run_np$3.out" 2>&1
  tt=$(grep 'Total time:' "run_np$3.out" | awk '{print $3}')
  ok=$(grep -c 'terminated normally' "run_np$3.out")
  cps=$(echo "scale=0; $2 * 300 / $tt" | bc 2>/dev/null)
  printf "%-40s np=%-3s Total_time=%-10s cellsteps/s=%-10s normal=%s\n" \
         "$1" "$3" "$tt" "$cps" "$ok"
}
echo "=== 500 m : 240x240x40, dtl=3, 300 steps, cells=2304000 ==="
run_one /home/boiko/thunderstorm/runs/bench500 2304000 6
run_one /home/boiko/thunderstorm/runs/bench500 2304000 8
run_one /home/boiko/thunderstorm/runs/bench500 2304000 16
echo "=== 333 m : 360x360x40, dtl=2, 300 steps, cells=5184000 ==="
run_one /home/boiko/thunderstorm/runs/bench333 5184000 8
run_one /home/boiko/thunderstorm/runs/bench333 5184000 16
echo FINERES_DONE
