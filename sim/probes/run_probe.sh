#!/usr/bin/env bash
# Phase 3 T5 -- run ONE 1 km probe. Throwaway; not a shipped scenario.
#
# sim/run_scenario.sh takes a scenario NAME out of sim/scenarios/ and is locked to
# np=8. Probe configs are NOT shippable scenarios and must not land in
# sim/scenarios/ (nothing there may be unexportable), and the probes run
# two-at-a-time at 4 ranks each per the charter's concurrency note. So this is a
# probe-local runner over sim/probes/configs/ -- but it still generates the deck
# with the PRODUCTION generator (pipeline/gen_deck.py), which is what makes the
# probe decks comparable to the shipped ones, and it still records the binary
# sha256 (T4: runs/cm1.exe is a SYMLINK into the build tree, so the pin cannot be
# assumed).
#
#   bash sim/probes/run_probe.sh sim/probes/configs/t5probe_c2.json 4
set -euo pipefail

CONFIG="$1"
NRANKS="${2:-4}"
REPO=/mnt/m/claud_projects/thunderstorm
CM1_EXE=/home/boiko/thunderstorm/runs/cm1.exe

NAME="$(basename "$CONFIG" .json)"
RUNDIR="/home/boiko/thunderstorm/runs/$NAME"

echo "=== $NAME: generating deck from $CONFIG ==="
DECK="$(mktemp)"
python3 "$REPO/pipeline/gen_deck.py" --scenario "$CONFIG" -o "$DECK"

mkdir -p "$RUNDIR"
cp "$CM1_EXE" "$RUNDIR/cm1.exe"
cp "$DECK" "$RUNDIR/namelist.input"
cp "$CONFIG" "$RUNDIR/scenario.json"
rm -f "$DECK"
cd "$RUNDIR"

{
  echo "probe            : $NAME"
  echo "cm1_binary_sha256: $(sha256sum cm1.exe | awk '{print $1}')"
  echo "nranks           : $NRANKS"
  echo "config           : $CONFIG"
  echo "pre-registration : docs/phase3-t5-multicell.md"
} | tee run_meta.txt

rm -f cm1out*.nc cm1out.nc
echo "=== $NAME: mpirun -np $NRANKS ./cm1.exe ==="
if time mpirun -np "$NRANKS" ./cm1.exe > cm1.out 2>&1; then
  echo "PROBE_OK $NAME" | tee "$RUNDIR/PROBE_STATUS"
else
  echo "PROBE_FAIL $NAME (exit $?)" | tee "$RUNDIR/PROBE_STATUS"
  tail -n 30 cm1.out
  exit 1
fi
ls cm1out*.nc | wc -l
