#!/bin/bash
# Batch 1: reproducibility, then fine-resolution rank scaling. Sequential (no overlap).
echo "===== REPRODUCIBILITY (1 km, np=8, run twice, full-field compare) ====="
bash /home/boiko/thunderstorm/runs/bench/repro.sh
echo
echo "===== FINE-RESOLUTION RANK SCALING ====="
bash /home/boiko/thunderstorm/runs/bench_fineres.sh
echo ALL_BATCH1_DONE
