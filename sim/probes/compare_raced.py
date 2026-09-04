#!/usr/bin/env python3
"""Reproducibility check for the 2026-09-04 capped-control race.

Both capped members were first run TWICE concurrently in one persistent run
directory (plan section 5.2.1). Those runs are NOT the run of record -- the
clean re-run is -- and this script exists for exactly one purpose: to measure
whether the raced output nevertheless agrees with the clean output.

It should. Both copies ran the same config, the same forked binary, np=4 and
the same decomposition, which is the condition Phase 0 verified bitwise; the
aborting job died at 33 s having written no output but the contended frame-1
attempt, and both jobs' `rm -f cm1out*.nc` ran before either mpirun produced
anything. That is a prediction made in advance, not a licence to skip the test.

Agreement also settles the one hazard here that is physics rather than
bookkeeping: the second job's `cp input_sounding` racing the first job's read
of it at initialisation. Re-generating the sounding and matching its sha256
proves the file is right NOW, not what CM1 read at 09:49:28 -- but identical
fields from a clean run that certainly read a good sounding do prove it.

The comparison is on decoded variable arrays, via the Phase 0 gate's own
compare_files(); it is never on file bytes.

  python3 sim/probes/compare_raced.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "benchmark"))
from repro_compare import compare_files  # noqa: E402

RUNS = "/home/boiko/thunderstorm/runs"
MEMBERS = ["t5s_capped_dt3", "t5s_capped_dt6"]


def frames(d):
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if f.startswith("cm1out_0") and f.endswith(".nc"))


def main():
    overall_ok = True
    any_compared = False
    for m in MEMBERS:
        clean = os.path.join(RUNS, m)
        raced = os.path.join(RUNS, m + ".raced")
        fc, fr = frames(clean), frames(raced)
        common = [f for f in fc if f in fr]
        print(f"\n=== {m}")
        print(f"  clean frames : {len(fc)}")
        print(f"  raced frames : {len(fr)}"
              + ("   (the aborting job cost it the tail)" if len(fr) < len(fc) else ""))
        print(f"  comparable   : {len(common)}")
        if not common:
            print("  NOTHING TO COMPARE -- check the paths")
            overall_ok = False
            continue
        member_ok = True
        worst = 0.0
        for f in common:
            any_compared = True
            msgs = []
            ok, d, nvar = compare_files(os.path.join(clean, f),
                                        os.path.join(raced, f),
                                        report=msgs.append)
            if not ok:
                member_ok = False
                worst = max(worst, d)
                print(f"  {f}: DIFFERS over {nvar} vars, max|delta| = {d:g}")
                for line in msgs[:6]:
                    print("   " + line)
                if len(msgs) > 6:
                    print(f"    ... and {len(msgs) - 6} more variables")
        if member_ok:
            print(f"  ALL {len(common)} comparable frames agree bitwise on every shared variable.")
        else:
            print(f"  DISAGREES -- worst max|delta| over the member = {worst:g}")
            overall_ok = False

    print("\n" + "=" * 62)
    if not any_compared:
        print("VERDICT: no frames compared. The check did not run.")
        return 2
    if overall_ok:
        print("VERDICT: raced output reproduces the clean run exactly.")
        print("The prediction in plan section 5.2.1 holds: the interleaved cm1.out")
        print("was the whole of the damage, and the input_sounding read was clean.")
        return 0
    print("VERDICT: raced output does NOT reproduce the clean run.")
    print("The clean run remains the run of record regardless (section 5.2.1);")
    print("this says the contamination reached the fields. First thing to check")
    print("is a truncated input_sounding read at initialisation.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
