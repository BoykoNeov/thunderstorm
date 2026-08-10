#!/usr/bin/env python3
"""Wiring gates for the Phase 3 T5 classifier (sim/probes/classify_t5.py).

    python3 pipeline/tests/test_classifier_t5.py

WHAT THIS IS FOR, AND WHAT IT IS DELIBERATELY NOT

The whole T5 conclusion rests on one function -- `classify()` -- implementing the
rule pre-registered in docs/phase3-t5-multicell.md section 3.2. The probe runs are
one-shots (five 1 km run dirs in WSL, none of them in git), so the MEASUREMENT can
never be a repeatable gate, exactly as in T3. What can be gated permanently is the
DECISION RULE's wiring, on synthetic frames small enough to live in this file.

These fixtures are hand-built so each branch is reached for the stated reason and
not by accident. The two that matter most:

  * `supercell_outvotes_cell_count` -- a fixture with FIVE simultaneous cells and
    strong rotation must come back SUPERCELL, because a splitting supercell shows
    two movers and section 3.2 says count must never outvote sustained rotation.
    If this ever flips, a supercell can be mislabelled the answer we were hunting.
  * `crit3_gates_the_SPAN_not_the_frame_count` -- the scratch draft counted frames
    and called them minutes. A flickering echo passes a count and fails a span,
    so this fixture flickers.

Run before the classifier is pointed at real data, and it was.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "sim", "probes"))

import classify_t5 as C  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def frame(t_min, uh=0.0, cells=0, updrafts=0, clearance=50.0, centroid=(0.0, 0.0)):
    """One synthetic frame carrying only the keys the decision rule reads."""
    return {
        "t_s": t_min * 60.0, "t_min": float(t_min),
        "max_abs_uh": float(uh),
        "n_cells": int(cells), "n_updrafts": int(updrafts),
        "cell_clearance_km": clearance, "w_clearance_km": clearance,
        "cell_centroid_x_km": centroid[0], "cell_centroid_y_km": centroid[1],
    }


def run(frames, motion=(0.0, 0.0)):
    return {"name": "fixture", "n_frames": len(frames),
            "declared_motion": motion, "frames": frames}


# The control scale every fixture is scored against: a "known supercell" whose
# mature max|uh| is 400, so criterion 1's threshold is 100.
SC_MEDIAN = 400.0
THRESH = C.UH_FRACTION_OF_CONTROL * SC_MEDIAN
TIMES = list(range(0, 125, 5))          # the probes' own cadence: 25 frames, 5 min


def label(frames):
    return C.classify(run(frames), SC_MEDIAN)[0]


print("--- the four branches of section 3.2 ---")

check("threshold_is_a_quarter_of_the_control", THRESH == 100.0, THRESH)

# SUPERCELL: rotating in every mature frame, one cell.
sup = [frame(t, uh=(500 if t >= 40 else 0), cells=1, updrafts=1) for t in TIMES]
check("supercell_branch", label(sup) == "SUPERCELL", label(sup))

# MULTICELL: no rotation worth the name, three updrafts at once, echo spanning
# the full mature window.
mul = [frame(t, uh=(20 if t >= 40 else 0), cells=(2 if t >= 40 else 0),
             updrafts=(3 if t >= 40 else 0)) for t in TIMES]
check("multicell_branch", label(mul) == "MULTICELL", label(mul))

# SINGLE CELL: no rotation, never more than one cell or two updrafts.
sing = [frame(t, uh=10, cells=1, updrafts=1) for t in TIMES]
check("single_cell_branch", label(sing) == "SINGLE CELL", label(sing))

# INDETERMINATE: multiple cells, but the system does not outlive 60 min.
ind = [frame(t, uh=10, cells=(2 if 40 <= t <= 70 else 0),
             updrafts=(3 if 40 <= t <= 70 else 0)) for t in TIMES]
check("indeterminate_branch", label(ind) == "INDETERMINATE", label(ind))

print("--- the two failure modes the branches must not have ---")

# A splitting supercell legitimately shows several cells. Rotation must win.
split = [frame(t, uh=(500 if t >= 40 else 0), cells=5, updrafts=5) for t in TIMES]
check("supercell_outvotes_cell_count", label(split) == "SUPERCELL", label(split))

# Flicker: an echo present in 13 mature frames but spanning only 25 min. The
# frame-count reading of crit3 would have passed this (13 x 5 = 65 "minutes").
flick = [frame(t, uh=10, cells=(2 if 40 <= t <= 65 else 0),
               updrafts=(3 if 40 <= t <= 65 else 0)) for t in TIMES]
_, ev = C.classify(run(flick), SC_MEDIAN)
check("crit3_gates_the_SPAN_not_the_frame_count",
      ev["echo_span_min"] == 25.0 and not ev["crit3_sustained_system"],
      f"span={ev['echo_span_min']} crit3={ev['crit3_sustained_system']}")

print("--- scoping: the rule starts at t = 40 min ---")

# Everything interesting happens during the bubble phase and stops. Counting the
# early frames would call this MULTICELL; the doc scopes the rule to mature ones.
early = [frame(t, uh=10, cells=(3 if t < 40 else 0),
               updrafts=(4 if t < 40 else 0)) for t in TIMES]
check("bubble_phase_does_not_count", label(early) == "SINGLE CELL", label(early))

# Rotation before t=40 must not make it a supercell either.
early_rot = [frame(t, uh=(900 if t < 40 else 10), cells=1, updrafts=1)
             for t in TIMES]
check("bubble_phase_rotation_does_not_count",
      label(early_rot) == "SINGLE CELL", label(early_rot))

print("--- criterion 2's two independent arms ---")

# Arm A alone: 3 simultaneous updrafts in a SINGLE frame is enough.
armA = [frame(t, uh=10, cells=1, updrafts=(3 if t == 60 else 1)) for t in TIMES]
check("crit2_arm_updraft_count_alone", label(armA) == "MULTICELL", label(armA))

# Arm B alone: 2 cells in 5 frames is enough, with updrafts never reaching 3.
armB = [frame(t, uh=10, cells=(2 if 60 <= t <= 80 else 1), updrafts=2)
        for t in TIMES]
_, evB = C.classify(run(armB), SC_MEDIAN)
check("crit2_arm_cell_frames_alone",
      evB["frames_with_2plus_cells"] == 5 and label(armB) == "MULTICELL",
      f"{evB['frames_with_2plus_cells']} {label(armB)}")

# ... and one frame short of it is not.
armB4 = [frame(t, uh=10, cells=(2 if 60 <= t <= 75 else 1), updrafts=2)
         for t in TIMES]
check("crit2_arm_cell_frames_boundary", label(armB4) == "SINGLE CELL",
      label(armB4))

print("--- section 5: drift and the void criterion ---")

# A storm drifting east at a steady 10 m/s in a run declared umove=8 wanted 18.
moving = [frame(t, uh=10, cells=1, updrafts=1,
                centroid=(0.6 * (t - 40), 0.0)) for t in TIMES]   # 0.6 km/min
dr = C.drift_fit(run(moving, motion=(8.0, 0.0)))
check("drift_rate_recovered", abs(dr["drift_u_ms"] - 10.0) < 0.05, dr["drift_u_ms"])
check("implied_motion_is_declared_plus_drift",
      abs(dr["implied_umove"] - 18.0) < 0.05, dr["implied_umove"])

# Clearance below 15 km in a mature frame voids the run...
near = [frame(t, uh=10, cells=1, updrafts=1, clearance=(9.0 if t == 100 else 50.0))
        for t in TIMES]
check("void_fires_on_a_close_wall", C.drift_fit(run(near))["void"])

# ...but the same clearance during the bubble phase does not (the rule is scoped).
near_early = [frame(t, uh=10, cells=1, updrafts=1,
                    clearance=(9.0 if t == 20 else 50.0)) for t in TIMES]
check("void_does_not_fire_before_maturity",
      not C.drift_fit(run(near_early))["void"])

# A comfortably contained run must not be voided -- otherwise "void" says nothing.
check("void_silent_on_a_contained_run", not C.drift_fit(run(sing))["void"])

print("--- controls: what SC can and cannot tell us ---")

# Pre-registration honesty check, from the docstring: SC is scored against a
# threshold derived from SC's own median, so it classifies SUPERCELL on ANY data.
# This gate exists so that fact stays visible in the test output rather than being
# discovered while reading results.
for tag, uh_series in (("flat", [7.0] * len(TIMES)),
                       ("tiny", [0.01] * len(TIMES)),
                       ("wild", [float(i * i) for i in range(len(TIMES))])):
    fake_sc = [frame(t, uh=u, cells=1, updrafts=1) for t, u in zip(TIMES, uh_series)]
    med = sorted(f["max_abs_uh"] for f in C.mature(fake_sc))
    med = med[len(med) // 2] if len(med) % 2 else (med[len(med) // 2 - 1]
                                                   + med[len(med) // 2]) / 2
    lab = C.classify(run(fake_sc), med)[0]
    check(f"SC_label_is_arithmetically_forced_{tag}", lab == "SUPERCELL", lab)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
