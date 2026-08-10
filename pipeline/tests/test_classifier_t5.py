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
import inspect
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

print("--- section 8: criterion 2' computed from real fields ---")

import numpy as np  # noqa: E402

NX = 121
KM = np.arange(NX, dtype=float) - NX // 2          # -60 .. +60 km, 1 km cells


def field(centres, radius_km=2.0, w=20.0, dbz=50.0, echo_at=None):
    # radius 2 km, not 3: at 3 the RING12 lobes (5.1 km apart) merge into a single
    # annulus and the fixture silently stops testing 12 components. Physically
    # right, pedagogically useless -- the same class of trap as T3's square grid.
    """Build (colmax_w, cref) with a blob at each centre, so `organisation` runs
    on the same arrays it will see from CM1 rather than on a mocked summary."""
    yy, xx = np.meshgrid(KM, KM, indexing="ij")
    cw = np.zeros((NX, NX))
    for cx, cy in centres:
        cw = np.maximum(cw, np.where((xx - cx) ** 2 + (yy - cy) ** 2
                                     <= radius_km ** 2, w, 0.0))
    cref = np.zeros((NX, NX))
    for cx, cy in (echo_at if echo_at is not None else centres):
        cref = np.maximum(cref, np.where((xx - cx) ** 2 + (yy - cy) ** 2
                                         <= radius_km ** 2, dbz, 0.0))
    return cw, cref


def org(centres, echo_at=None):
    cw, cref = field(centres, echo_at=echo_at)
    return C.organisation(cw, cref, KM, KM, 1.0)


# PC's actual geometry: four equal lobes of one ring, echo centred on the ring.
RING4 = [(-5, -5), (5, -5), (-5, 5), (5, 5)]
RING12 = RING4 + [(0, -6), (0, 6), (-6, 0), (6, 0),
                  (-9, -9), (9, -9), (-9, 9), (9, 9)]
LINE = [(-18, 0), (-9, 0), (0, 0), (9, 0), (18, 0)]
FLANK = [(0, 0), (9, 1), (11, -3), (13, 4)]

o4, o12 = org(RING4, echo_at=[(0, 0)]), org(RING12, echo_at=[(0, 0)])
check("ring4_has_no_flank_coherence", o4["R"] < 0.01, o4["R"])
check("ring4_is_not_elongated", o4["E"] < 1.1, o4["E"])
check("ring12_has_no_flank_coherence", o12["R"] < 0.01, o12["R"])
check("ring12_is_not_elongated", o12["E"] < 1.1, o12["E"])

oL = org(LINE, echo_at=[(0, 0)])
check("line_is_elongated_far_past_the_floor", oL["E"] >= C.E_FLOOR * 2, oL["E"])
check("line_has_no_flank_coherence_which_is_why_E_exists",
      oL["R"] < 0.05, oL["R"])

oF = org(FLANK, echo_at=[(0, 0)])
check("flank_cluster_is_coherent", oF["R"] >= C.R_FLOOR, oF["R"])

# Qualification rules.
check("one_component_does_not_qualify", not org([(0, 0)])["org_qualifies"])
check("no_echo_does_not_qualify",
      not C.organisation(field(RING4)[0], np.zeros((NX, NX)), KM, KM, 1.0)
      ["org_qualifies"])
o2 = org([(-9, 0), (9, 0)], echo_at=[(0, 0)])
check("two_components_qualify_but_carry_no_E",
      o2["org_qualifies"] and o2["E"] is None, o2["E"])

# The bias that moved O2 off centroid points (docs 8.2). Three points in general
# position give a wildly elongated 3-point ellipse; the mask says otherwise.
TRIPLE = [(0, 0), (7, 1), (3, 6)]
pts = np.array(TRIPLE, dtype=float)
d = pts - pts.mean(axis=0)
ev = np.linalg.eigvalsh((d.T @ d) / len(d))
check("centroid_point_ellipse_is_the_rejected_estimator",
      float(np.sqrt(ev[1] / ev[0])) > org(TRIPLE, echo_at=[(0, 0)])["E"],
      f"points={np.sqrt(ev[1] / ev[0]):.2f} mask={org(TRIPLE, echo_at=[(0, 0)])['E']:.2f}")
check("unorganised_triple_stays_under_the_E_floor",
      org(TRIPLE, echo_at=[(0, 0)])["E"] < C.E_FLOOR,
      org(TRIPLE, echo_at=[(0, 0)])["E"])

print("--- section 8: the rule, and the failure it was built to fix ---")


def orgframe(t_min, centres, uh=10.0, echo_at=None, cells=1):
    o = org(centres, echo_at=echo_at)
    f = frame(t_min, uh=uh, cells=cells, updrafts=o["org_ncomp"])
    f.update(o)
    return f


ring_run = [orgframe(t, RING4, echo_at=[(0, 0)]) if t >= 40 else orgframe(t, [(0, 0)])
            for t in TIMES]
line_run = [orgframe(t, LINE, echo_at=[(0, 0)]) if t >= 40 else orgframe(t, [(0, 0)])
            for t in TIMES]
flank_run = [orgframe(t, FLANK, echo_at=[(0, 0)]) if t >= 40 else orgframe(t, [(0, 0)])
             for t in TIMES]

check("ring_run_is_SINGLE_CELL_under_the_new_rule",
      C.classify_v2(run(ring_run), SC_MEDIAN)[0] == "SINGLE CELL",
      C.classify_v2(run(ring_run), SC_MEDIAN)[0])
# ...and this is the whole point of section 8: the SAME fixture under the retired
# count rule is the abort. A gate that only shows the fix passing does not show
# that it fixed anything.
check("control_ring_run_WAS_multicell_under_the_retired_count_rule",
      C.classify(run(ring_run), SC_MEDIAN)[0] == "MULTICELL",
      C.classify(run(ring_run), SC_MEDIAN)[0])

check("line_run_is_MULTICELL", C.classify_v2(run(line_run), SC_MEDIAN)[0] == "MULTICELL",
      C.classify_v2(run(line_run), SC_MEDIAN)[0])
check("flank_run_is_MULTICELL", C.classify_v2(run(flank_run), SC_MEDIAN)[0] == "MULTICELL",
      C.classify_v2(run(flank_run), SC_MEDIAN)[0])

# Rotation still outvotes organisation (section 8.3): a rotating LINE is a
# supercell, not a squall line, and must not be relabelled by its geometry.
rot_line = [dict(f, max_abs_uh=500.0) if f["t_min"] >= 40 else f for f in line_run]
check("rotation_still_outvotes_organisation",
      C.classify_v2(run(rot_line), SC_MEDIAN)[0] == "SUPERCELL",
      C.classify_v2(run(rot_line), SC_MEDIAN)[0])

# Sustained multiplicity: organised, but only in 4 frames.
brief = [orgframe(t, FLANK, echo_at=[(0, 0)]) if 60 <= t <= 75 else orgframe(t, [(0, 0)])
         for t in TIMES]
_, evb = C.classify_v2(run(brief), SC_MEDIAN)
check("four_organised_frames_are_not_enough",
      evb["qualifying_frames"] == 4 and not evb["crit2p_organised_multiplicity"],
      f"{evb['qualifying_frames']} {evb['crit2p_organised_multiplicity']}")

print("--- section 8.6: the two-sided uncertainty band ---")


def band_run(r_value):
    fr = []
    for t in TIMES:
        f = frame(t, uh=10.0, cells=1, updrafts=3)
        f.update({"org_qualifies": t >= 40, "org_ncomp": 3,
                  "R": r_value if t >= 40 else None, "E": 1.0,
                  "org_min_anchor_km": 5.0})
        fr.append(f)
    return run(fr)


check("just_over_the_R_floor_is_INDETERMINATE_not_multicell",
      C.classify_v2(band_run(0.55), SC_MEDIAN)[0] == "INDETERMINATE",
      C.classify_v2(band_run(0.55), SC_MEDIAN)[0])
check("just_under_the_R_floor_is_INDETERMINATE_not_single_cell",
      C.classify_v2(band_run(0.45), SC_MEDIAN)[0] == "INDETERMINATE",
      C.classify_v2(band_run(0.45), SC_MEDIAN)[0])
check("clearly_over_the_R_floor_is_MULTICELL",
      C.classify_v2(band_run(0.75), SC_MEDIAN)[0] == "MULTICELL",
      C.classify_v2(band_run(0.75), SC_MEDIAN)[0])
check("clearly_under_the_R_floor_is_SINGLE_CELL",
      C.classify_v2(band_run(0.15), SC_MEDIAN)[0] == "SINGLE CELL",
      C.classify_v2(band_run(0.15), SC_MEDIAN)[0])

print("--- section 10: containment measured against OPEN boundaries only ---")

XH = np.arange(-89.0, 90.0, 1.0)           # a 180 km domain, like the probes
BOTH = {"x": True, "y": True}
X_ONLY = {"x": True, "y": False}           # periodic y: the squall-line setup


def linemask():
    """A line spanning the full y extent, narrow in x -- candidate C's geometry."""
    m = np.zeros((len(XH), len(XH)), bool)
    m[:, 85:95] = True
    return m


c_both = C._containment(linemask(), XH, XH, "cell", BOTH)
c_xonly = C._containment(linemask(), XH, XH, "cell", X_ONLY)
check("domain_spanning_line_is_uncontained_with_open_y",
      c_both["cell_clearance_km"] == 0.0, c_both["cell_clearance_km"])
check("same_line_is_contained_when_y_is_periodic",
      c_xonly["cell_clearance_km"] > 80.0, c_xonly["cell_clearance_km"])
# The x-direction must STILL be checked -- periodic y is not a licence to ignore
# the direction the system actually propagates in.
wide = np.zeros((len(XH), len(XH)), bool)
wide[:, 2:178] = True
check("periodic_y_does_not_excuse_an_x_wall_touch",
      C._containment(wide, XH, XH, "cell", X_ONLY)["cell_clearance_km"] < 5.0,
      C._containment(wide, XH, XH, "cell", X_ONLY)["cell_clearance_km"])
# No open side at all: there is no containment question, and a number would be a
# section 9.5 error in reverse.
check("fully_periodic_domain_reports_no_clearance",
      C._containment(linemask(), XH, XH, "cell",
                     {"x": False, "y": False})["cell_clearance_km"] is None)

# The section 6.2 descriptor follows the same rule.
lab_mask = np.zeros((len(XH), len(XH)), bool)
lab_mask[3:9, 85:95] = True                # a blob hard against the y=-89 wall
check("boundary_descriptor_counts_a_cell_on_an_OPEN_wall",
      C._boundary_components(lab_mask, XH, XH, 1.0, 10.0, BOTH) == 1,
      C._boundary_components(lab_mask, XH, XH, 1.0, 10.0, BOTH))
check("boundary_descriptor_ignores_a_cell_on_a_PERIODIC_wall",
      C._boundary_components(lab_mask, XH, XH, 1.0, 10.0, X_ONLY) == 0,
      C._boundary_components(lab_mask, XH, XH, 1.0, 10.0, X_ONLY))

# Absent bc keys must behave exactly as before this change: open on all sides.
import json as _json  # noqa: E402
import tempfile  # noqa: E402

_tmp = tempfile.mkdtemp()
with open(os.path.join(_tmp, "scenario.json"), "w") as fh:
    _json.dump({"sim": {"namelist": {"nx": 10}}}, fh)
check("missing_bc_keys_default_to_open_both_ways",
      C.open_sides(_tmp) == {"x": True, "y": True}, C.open_sides(_tmp))
with open(os.path.join(_tmp, "scenario.json"), "w") as fh:
    _json.dump({"sim": {"namelist": {"sbc": 1, "nbc": 1}}}, fh)
check("periodic_sbc_nbc_are_read_as_a_closed_y",
      C.open_sides(_tmp) == {"x": True, "y": False}, C.open_sides(_tmp))

print("--- section 11.4: criterion 1 IS a median comparison ---")

# docs section 11.4 claims criterion 1 reduces to
#     median(candidate mature max|uh|) >= k * SC_median
# and that the pre-registration's "rotating for less than half its mature life"
# therefore supplies NO temporal robustness. That claim now sits in a doc; these
# gates put it under test, so the doc cannot drift from the code -- and so that
# whoever implements section 9.8's option (iii) has to consciously break them
# rather than silently inherit the defect.
#
# The measurement in section 11.4 used the six real 1 km probe runs (12 000
# comparisons, 0 disagreements). Those runs are not in git; this is the half that
# needs no data, which is the half that can be gated permanently.

def crit1_not_supercell(vals):
    """The rule as written: a FRACTION-of-frames test."""
    return C.classify(run([frame(t, uh=v) for t, v in zip(TIMES[8:], vals)]),
                      SC_MEDIAN)[1]["crit1_not_supercell"]


def median_rule(vals):
    """The scalar the fraction test is claimed to be equivalent to."""
    return float(np.median(vals)) < THRESH


_SERIES = {
    "flat_mild":        [200.0] * 17,
    "flat_below":       [50.0] * 17,
    "8_huge_spikes":    [2000.0] * 8 + [1.0] * 9,
    "9_huge_spikes":    [2000.0] * 9 + [1.0] * 8,
    "ramp":             list(np.linspace(0.0, 1600.0, 17)),
    "one_huge_spike":   [1e6] + [1.0] * 16,
    "one_deep_dropout": [2000.0] * 16 + [0.0],
}
_dis = [k for k, v in _SERIES.items() if crit1_not_supercell(v) != median_rule(v)]
check("crit1_is_exactly_the_median_comparison", not _dis, f"disagree: {_dis}")

# The two series that make the point: 8 identical huge frames is not enough and 9
# is, so the rule reads only which side of the middle the 9th value falls on.
check("eight_frames_of_violent_rotation_is_NOT_a_supercell",
      crit1_not_supercell(_SERIES["8_huge_spikes"]) is True)
check("nine_identical_frames_IS_a_supercell",
      crit1_not_supercell(_SERIES["9_huge_spikes"]) is False)
check("a_single_10e6_frame_is_NOT_a_supercell",
      crit1_not_supercell(_SERIES["one_huge_spike"]) is True)
check("uniformly_mild_rotation_IS_a_supercell",
      crit1_not_supercell(_SERIES["flat_mild"]) is False)

# Negative control: the equivalence is a property of UH_FRAC_FRAMES = 0.5, not a
# tautology of the code. Move the fraction off the median and the two rules must
# come apart -- otherwise the gate above would pass on any implementation.
_saved = C.UH_FRAC_FRAMES
C.UH_FRAC_FRAMES = 0.25
_dis25 = [k for k, v in _SERIES.items() if crit1_not_supercell(v) != median_rule(v)]
C.UH_FRAC_FRAMES = _saved
check("the_equivalence_BREAKS_at_a_non_median_fraction", _dis25,
      "no series separated the two rules at UH_FRAC_FRAMES=0.25 -- "
      "the equivalence gate is vacuous")

# And it is the FRACTION that carries the property, not the 0.25 magnitude: k
# rescales the threshold, so the equivalence must survive any k.
_ks = []
for _k in (0.1, 0.25, 0.5, 0.9, 1.5):
    _t = C.UH_FRACTION_OF_CONTROL
    C.UH_FRACTION_OF_CONTROL = _k
    THRESH = _k * SC_MEDIAN
    _ks += [k for k, v in _SERIES.items()
            if crit1_not_supercell(v) != median_rule(v)]
    C.UH_FRACTION_OF_CONTROL = _t
THRESH = C.UH_FRACTION_OF_CONTROL * SC_MEDIAN
check("the_equivalence_holds_at_every_k", not _ks, f"disagree: {_ks}")

# Both blocks above mutate module state (C.UH_FRAC_FRAMES, C.UH_FRACTION_OF_CONTROL
# and this file's THRESH) and restore it. Make the restore self-checking rather
# than order-dependent: without this, a gate added between the k-loop and its
# restore -- or added after a block that raised -- would silently score against
# k=1.5 and still print PASS.
check("module_state_is_restored_after_the_sensitivity_blocks",
      THRESH == 100.0 and C.UH_FRACTION_OF_CONTROL == 0.25
      and C.UH_FRAC_FRAMES == 0.5,
      f"THRESH={THRESH} k={C.UH_FRACTION_OF_CONTROL} "
      f"frac={C.UH_FRAC_FRAMES}")



# ---------------------------------------------------------------------------
# Section 12: criterion 1' -- rotation PERSISTENCE, and the machinery under it.
#
# Section 11.4 retired criterion 1 by MEASURING that it collapses to a median
# comparison. P1 is exposed to the identical suspicion -- "you moved k with extra
# steps" -- so the answer here has to be a test and not a paragraph. The blocks
# below are, in order: the signed-component gates, the wrap-aware geometry (each
# with a control that FAILS on the naive implementation, because a wrap fixture
# that passes either way tests nothing), the chain itself, classify_v3's wiring,
# and section 12.9's anti-collapse gate with its vacuity control.
# ---------------------------------------------------------------------------

OPEN2 = {"x": False, "y": False}
PERY = {"x": False, "y": True}


def uhfield(blobs, half=1):
    """A uh field with a (2*half+1)^2 block of the given value at each centre.

    3x3 = 9 km2 at 1 km cells, comfortably over UH_MIN_AREA_KM2 = 4.
    """
    a = np.zeros((NX, NX))
    for cx, cy, val in blobs:
        i = int(np.argmin(np.abs(KM - cx)))
        j = int(np.argmin(np.abs(KM - cy)))
        a[max(0, j - half):j + half + 1, max(0, i - half):i + half + 1] = val
    return a


# --- signed components: the couplet must not merge ---------------------------
# A splitting storm puts a cyclonic and an anticyclonic mesocyclone side by side.
# Under abs() the adjacent pair merges into ONE component whose centroid sits
# BETWEEN the movers -- an artifact in exactly the case that decides SC.
# The lobes must TOUCH or the control below cannot fire: at centres -2 / +2 the two
# 3x3 blocks leave a one-cell gap at x=0, abs() has nothing to merge, and the
# fixture silently stops testing the thing it exists for. Same class of trap as the
# RING12 radius above. Cyclonic at -2 (cols -3..-1), anticyclonic at +1 (cols 0..2).
couplet = uhfield([(-2, 0, +500.0), (1, 0, -500.0)])
cs = sorted(C.rotation_centres(couplet, KM, KM, 1.0, C.UH_FLOOR, OPEN2),
            key=lambda c: c["x_km"])
check("signed_couplet_gives_TWO_centres", len(cs) == 2, [c["sign"] for c in cs])
check("signed_couplet_carries_both_senses",
      sorted(c["sign"] for c in cs) == [-1, 1], [c["sign"] for c in cs])
check("signed_couplet_centres_sit_ON_the_movers",
      abs(cs[0]["x_km"] + 2.0) < 0.6 and abs(cs[1]["x_km"] - 1.0) < 0.6,
      [c["x_km"] for c in cs])
# The control that gives the gates above their meaning: |uh| really does merge the
# couplet, and the merged centroid lands BETWEEN the movers -- on neither of them.
_abs_lab, _abs_n = C.label_periodic(np.abs(couplet) >= C.UH_FLOOR, OPEN2)
check("CONTROL_abs_uh_merges_the_couplet_into_one", _abs_n == 1, _abs_n)
_abs_x = KM[np.nonzero(_abs_lab == 1)[1]].mean()
check("CONTROL_the_merged_centroid_sits_between_the_movers_on_neither",
      cs[0]["x_km"] < _abs_x < cs[1]["x_km"], _abs_x)

check("a_component_under_the_area_minimum_is_dropped",
      C.rotation_centres(uhfield([(0, 0, 500.0)], half=0), KM, KM, 1.0,
                         C.UH_FLOOR, OPEN2) == [])
check("rotation_below_the_floor_yields_no_centres",
      C.rotation_centres(uhfield([(0, 0, C.UH_FLOOR - 0.1)]), KM, KM, 1.0,
                         C.UH_FLOOR, OPEN2) == [])

# --- wrap-aware geometry, each with a failing naive control -------------------
check("period_is_one_cell_longer_than_the_coordinate_span",
      C._period(KM) == (KM[-1] - KM[0]) + 1.0, C._period(KM))
# The seam gotcha stated as a control: the naive span is short by exactly one cell,
# which puts a 1 km discontinuity in every wrapped distance.
check("CONTROL_the_naive_span_is_NOT_the_period",
      (KM[-1] - KM[0]) != C._period(KM))

PER = C._period(KM)
check("wrap_delta_takes_the_short_way_round",
      abs(C.wrap_delta(PER - 3.0, PER, True) - (-3.0)) < 1e-9,
      C.wrap_delta(PER - 3.0, PER, True))
check("CONTROL_naive_delta_reads_the_seam_as_a_domain_crossing",
      abs(C.wrap_delta(PER - 3.0, PER, False)) > 100.0)
check("wrap_delta_is_identity_well_inside_the_domain",
      C.wrap_delta(4.0, PER, True) == 4.0)

# A feature straddling the y seam: rows at the very top and the very bottom.
seam = np.zeros((NX, NX))
seam[:2, 58:63] = 500.0
seam[-2:, 58:63] = 500.0
_lab_p, _n_p = C.label_periodic(seam >= C.UH_FLOOR, PERY)
_lab_o, _n_o = C.label_periodic(seam >= C.UH_FLOOR, OPEN2)
check("periodic_labelling_closes_the_seam", _n_p == 1, _n_p)
check("CONTROL_open_labelling_splits_the_same_feature", _n_o == 2, _n_o)

_yy = np.nonzero(seam >= C.UH_FLOOR)[0]
_circ = C.wrapped_centroid(KM[_yy], KM, True)
_arith = C.wrapped_centroid(KM[_yy], KM, False)
check("circular_centroid_lands_ON_the_seam_feature",
      min(abs(_circ - KM[0]), abs(_circ - KM[-1]), abs(abs(_circ) - PER / 2)) < 2.0,
      _circ)
check("CONTROL_arithmetic_centroid_lands_in_mid_domain_instead",
      abs(_arith) < 1.0 and abs(_arith - _circ) > 50.0, (_arith, _circ))
check("circular_centroid_is_folded_into_the_axis_range",
      KM[0] - 0.5 <= _circ <= KM[-1] + 0.5, _circ)
check("circular_centroid_equals_the_arithmetic_one_away_from_the_seam",
      abs(C.wrapped_centroid(np.array([9.0, 11.0]), KM, True) - 10.0) < 1e-6,
      C.wrapped_centroid(np.array([9.0, 11.0]), KM, True))

# --- the chain ---------------------------------------------------------------
def centre(x, y, sign=1, area=9.0):
    return {"sign": sign, "x_km": float(x), "y_km": float(y),
            "area_km2": area, "peak": 500.0}


CH_T = list(range(40, 125, 5))          # 17 mature frames, the probes' own count


def chain(nodes, periodic=OPEN2, **kw):
    return C.chain_stats(nodes, CH_T, KM, KM, periodic, **kw)


steady = [[centre(0, 0)] for _ in CH_T]
check("a_steady_centre_chains_the_whole_window",
      chain(steady)["p1_min"] == CH_T[-1] - CH_T[0], chain(steady)["p1_min"])

telep = [[centre((i % 2) * 40.0, 0)] for i in range(len(CH_T))]
check("a_teleporting_centre_forms_no_chain", chain(telep)["p1_min"] == 0.0,
      chain(telep)["p1_min"])
# ...and the control that proves the LIMIT is what refuses it, not the fixture:
check("CONTROL_the_same_teleporting_centre_chains_at_a_huge_link_radius",
      chain(telep, link_km=1e4)["p1_min"] == CH_T[-1] - CH_T[0])

drifting = [[centre(7.0 * i, 0)] for i in range(len(CH_T))]      # 7 km/frame < 7.5
check("a_centre_drifting_inside_the_link_radius_still_chains",
      chain(drifting)["p1_min"] == CH_T[-1] - CH_T[0])
check("P2_reports_the_walk_a_chain_took",
      chain(drifting)["p1_net_km"] > 100.0
      and abs(chain(drifting)["p1_path_km"] - chain(drifting)["p1_net_km"]) < 1e-6)

flip = [[centre(0, 0, sign=+1 if i < 8 else -1)] for i in range(len(CH_T))]
check("a_sign_flip_breaks_the_chain_at_the_same_position",
      chain(flip)["p1_min"] < CH_T[-1] - CH_T[0], chain(flip)["p1_min"])

drop = [[centre(0, 0)] if i != 8 else [] for i in range(len(CH_T))]
check("a_one_frame_dropout_breaks_the_gated_no_gap_chain",
      chain(drop)["p1_min"] < CH_T[-1] - CH_T[0], chain(drop)["p1_min"])
check("the_one_gap_DIAGNOSTIC_bridges_that_same_dropout",
      chain(drop, max_gap=2)["p1_min"] == CH_T[-1] - CH_T[0],
      chain(drop, max_gap=2)["p1_min"])

# The chain must be able to pick the LONGEST of several, not the first it meets.
mixed = [[centre(0, 0)] if i < 3 else [centre(30, 30)] for i in range(len(CH_T))]
check("the_longest_chain_wins_not_the_earliest",
      chain(mixed)["p1_min"] == CH_T[-1] - CH_T[3], chain(mixed)["p1_min"])

# --- the wrap gate that matters: a chain crossing the y seam -----------------
# This is section 12.6's whole point, and C2 is the run it lands on. The naive
# reading is a ~121 km jump -- it breaks a chain that never physically broke, and
# it breaks it TOWARD crit1' being TRUE, i.e. toward the answer being sought.
_LO = float(KM[0]) - 0.5                 # the axis's left cell edge
seamwalk = [[centre(0, _LO + ((-36.0 - 3.0 * i - _LO) % PER))]
            for i in range(len(CH_T))]   # -3 km/frame, wrapping at mature frame 9
check("a_chain_crossing_the_PERIODIC_y_seam_survives",
      chain(seamwalk, periodic=PERY)["p1_min"] == CH_T[-1] - CH_T[0],
      chain(seamwalk, periodic=PERY)["p1_min"])
check("CONTROL_the_same_chain_BREAKS_when_y_is_treated_as_open",
      chain(seamwalk, periodic=OPEN2)["p1_min"] < CH_T[-1] - CH_T[0],
      chain(seamwalk, periodic=OPEN2)["p1_min"])

# --- classify_v3 wiring ------------------------------------------------------
def run3(frames, periodic=OPEN2):
    return {"name": "fixture", "n_frames": len(frames), "declared_motion": (0.0, 0.0),
            "open_sides": {"x": True, "y": True}, "periodic_sides": periodic,
            "xh": KM, "yh": KM, "frames": frames}


def v3frame(t_min, centres, rot, echo_at=None, cells=1):
    """A frame carrying BOTH section 8's organisation keys and section 12's centres."""
    f = orgframe(t_min, centres, echo_at=echo_at, cells=cells)
    f["rot"] = {f"{fl:g}": (rot if fl <= C.UH_FLOOR else [])
                for fl in C.FLOOR_SWEEP}
    return f


def v3run(centres, rot_at, echo_at=None, periodic=OPEN2):
    """`rot_at(i)` returns the rotation centres for mature frame index i."""
    fr = []
    for t in TIMES:
        if t < C.MATURE_MIN:
            fr.append(v3frame(t, [(0, 0)], []))
        else:
            i = (t - C.MATURE_MIN) // 5
            fr.append(v3frame(t, centres, rot_at(i), echo_at=echo_at, cells=1))
    return run3(fr, periodic=periodic)


ALWAYS = lambda i: [centre(0, 0)]                       # noqa: E731
NEVER = lambda i: [centre((i % 2) * 40.0, 0)]           # noqa: E731

# Rotation outvotes organisation -- section 8.3's ordering, re-gated for v3. A
# five-cell LINE with a persistent mesocyclone is a supercell, not a multicell.
check("persistent_rotation_outvotes_a_five_cell_line",
      C.classify_v3(v3run(LINE, ALWAYS, echo_at=[(0, 0)]))[0] == "SUPERCELL",
      C.classify_v3(v3run(LINE, ALWAYS, echo_at=[(0, 0)]))[1])
check("no_persistence_plus_an_organised_line_is_MULTICELL",
      C.classify_v3(v3run(LINE, NEVER, echo_at=[(0, 0)]))[0] == "MULTICELL",
      C.classify_v3(v3run(LINE, NEVER, echo_at=[(0, 0)]))[1])
check("no_persistence_plus_a_RING_is_SINGLE_CELL",
      C.classify_v3(v3run(RING4, NEVER, echo_at=[(0, 0)]))[0] == "SINGLE CELL",
      C.classify_v3(v3run(RING4, NEVER, echo_at=[(0, 0)]))[1])


def band_chain(minutes):
    """Rotation that persists for exactly `minutes`, then teleports away."""
    n = int(minutes // 5)
    return lambda i: [centre(0, 0)] if i <= n else [centre(40.0 * (i % 2), 40.0)]


check("P1_exactly_at_T_PERSIST_is_INDETERMINATE_not_a_label",
      C.classify_v3(v3run(LINE, band_chain(30), echo_at=[(0, 0)]))[0]
      == "INDETERMINATE",
      C.classify_v3(v3run(LINE, band_chain(30), echo_at=[(0, 0)]))[1]["P1_chain_min"])
check("P1_one_frame_over_the_band_banks_SUPERCELL",
      C.classify_v3(v3run(LINE, band_chain(35), echo_at=[(0, 0)]))[0] == "SUPERCELL",
      C.classify_v3(v3run(LINE, band_chain(35), echo_at=[(0, 0)]))[1]["P1_chain_min"])
check("P1_one_frame_under_the_band_proceeds_past_criterion_1p",
      C.classify_v3(v3run(LINE, band_chain(25), echo_at=[(0, 0)]))[0] == "MULTICELL",
      C.classify_v3(v3run(LINE, band_chain(25), echo_at=[(0, 0)]))[1]["P1_chain_min"])

# Section 11.6 constraint 2, gated STRUCTURALLY rather than promised in prose: the
# live rule cannot take a control median, so no candidate/control ratio can hide
# in it and SC's label cannot be arithmetically forced the way section 7.2 found.
_v3sig = inspect.signature(C.classify_v3).parameters
check("classify_v3_takes_NO_control_median_argument",
      "sc_uh_median" not in _v3sig and list(_v3sig) == ["cand", "floor"],
      list(_v3sig))
check("CONTROL_the_retired_rule_still_requires_one",
      "sc_uh_median" in inspect.signature(C.classify_v2).parameters)

# The floor is a NOISE GATE and the whole post-hoc defence rests on it staying one.
# Section 11.4's lowest candidate median is C2's 197.3; section 12.3 fixes the band
# at < 50. A future edit nudging UH_FLOOR up to a "principled" 300 would silently
# reinstate the median test with a citation stapled on -- this refuses it.
check("UH_FLOOR_stays_inside_the_declared_noise_gate_band",
      C.UH_FLOOR < 50.0 and C.UH_FLOOR <= 197.3 / 4.0, C.UH_FLOOR)
check("UH_MIN_AREA_is_the_reused_constant_not_a_new_one",
      C.UH_MIN_AREA_KM2 == C.W_MIN_AREA_KM2)

# --- section 12.6: organisation is wrap-aware too, and it must be a NO-OP ------
# Section 12.6 promised C2's banked E would be recomputed wrap-aware. That is only
# safe to do if the change cannot touch the runs already published in sections 9
# and 11 -- SC, PC, A, B and C are all fully open. So the FIRST gate is that
# nothing moves without a periodic axis.
for _name, _cent in (("ring4", RING4), ("line", LINE), ("flank", FLANK)):
    _cw, _cr = field(_cent, echo_at=[(0, 0)])
    _open = C.organisation(_cw, _cr, KM, KM, 1.0, OPEN2)
    _dflt = C.organisation(_cw, _cr, KM, KM, 1.0)
    check(f"organisation_is_unchanged_without_a_periodic_axis_{_name}",
          all(_open[k] == _dflt[k] for k in ("R", "E", "org_ncomp")),
          (_open, _dflt))

# The gate above is NOT enough on its own, and finding that out cost a real
# regression: the first wrap-aware draft replaced the grid-snapped component
# centroid with an exact mean, which moved R on all five OPEN runs (SC 0.4854 ->
# 0.4821, A 0.5064 -> 0.5211) -- and every fixture above still passed, because
# blobs on symmetric integer centres snap to themselves. Same defanging as T3's
# square grid and the couplet's one-cell gap. So the centroid is pinned directly,
# on components whose true mean is deliberately NOT on a grid point.
from scipy import ndimage as _nd  # noqa: E402


def _published_R(cw, cr, cents):
    """Section 8.2's R, recomputed INDEPENDENTLY from the given component centres.

    Deliberately a second implementation rather than a call into `organisation`:
    it pins the published formula (echo-centroid anchor, area-weighted unit
    vectors) so a refactor of the real one has something external to disagree with.
    """
    lab, n = _nd.label(cw >= C.W_UPDRAFT, structure=np.ones((3, 3)))
    keep = np.arange(1, n + 1)
    areas = _nd.sum(cw >= C.W_UPDRAFT, lab, index=keep)
    jj, ii = np.nonzero(cr >= C.DBZ_CELL)
    ax, ay = KM[ii].mean(), KM[jj].mean()
    num, den = np.zeros(2), 0.0
    for (gx, gy), a in zip(cents, areas):
        d = np.array([gx - ax, gy - ay])
        r = float(np.hypot(*d))
        if r == 0.0:
            continue
        num += a * d / r
        den += a
    return float(np.hypot(*num) / den)


_asym = [(-11.5, 3.5), (17.5, -8.5), (4.5, 21.5)]
_cw, _cr = field(_asym, radius_km=2.5, echo_at=[(0, 0)])
_lab, _n = _nd.label(_cw >= C.W_UPDRAFT, structure=np.ones((3, 3)))
_keep = np.arange(1, _n + 1)
_snap = [(float(KM[int(round(cx))]), float(KM[int(round(cy))]))
         for cy, cx in _nd.center_of_mass(_cw >= C.W_UPDRAFT, _lab, index=_keep)]
_exact = [(float(KM[np.nonzero(_lab == c)[1]].mean()),
           float(KM[np.nonzero(_lab == c)[0]].mean())) for c in _keep]
check("CONTROL_an_asymmetric_component_distinguishes_snap_from_exact_mean",
      any(abs(s[0] - e[0]) > 0.2 or abs(s[1] - e[1]) > 0.2
          for s, e in zip(_snap, _exact)), list(zip(_snap, _exact)))
_Rreal = C.organisation(_cw, _cr, KM, KM, 1.0, OPEN2)["R"]
check("organisation_still_uses_the_PUBLISHED_snapped_centroid_on_open_axes",
      abs(_Rreal - _published_R(_cw, _cr, _snap)) < 5e-5,
      (_Rreal, _published_R(_cw, _cr, _snap)))
check("CONTROL_the_exact_mean_would_have_given_a_DIFFERENT_R",
      abs(_published_R(_cw, _cr, _exact) - _published_R(_cw, _cr, _snap)) > 1e-4,
      (_published_R(_cw, _cr, _exact), _published_R(_cw, _cr, _snap)))

# A cluster with ONE member straddling the y seam. The two seam pieces must sit at
# +-60 -- one cell apart across the wrap -- or they never touch and the fixture
# stops testing the merge; and there must still be >=3 components in BOTH readings
# or E is None on one side and the control cannot compare. Without wrap-awareness
# the cluster's y-variance spans the whole domain: it reads as MORE elongated
# purely from wrapping, which is the artifact being gated.
_seamline = [(0, -60), (0, 60), (0, -50), (0, -40)]
_cw, _cr = field(_seamline, echo_at=[(0, 0)])
_o_per = C.organisation(_cw, _cr, KM, KM, 1.0, PERY)
_o_open = C.organisation(_cw, _cr, KM, KM, 1.0, OPEN2)
check("seam_line_is_ONE_feature_when_y_is_periodic",
      _o_per["org_ncomp"] < _o_open["org_ncomp"],
      (_o_per["org_ncomp"], _o_open["org_ncomp"]))
check("CONTROL_treating_the_same_seam_line_as_open_INFLATES_its_elongation",
      _o_open["E"] > _o_per["E"], (_o_open["E"], _o_per["E"]))
check("wrap_span_fraction_is_reported_on_a_periodic_axis",
      _o_per["org_wrap_span_frac"] is not None
      and _o_open["org_wrap_span_frac"] is None,
      (_o_per["org_wrap_span_frac"], _o_open["org_wrap_span_frac"]))

# The honest limit: a mask spanning the WHOLE periodic axis has no well-defined
# extent along it, so the span fraction must saturate and say so.
# Three columns, not one: a single column merges to ONE component and returns
# before E is ever computed, so the span would read None and the gate would test
# nothing. Each column fills the periodic y axis end to end.
_full = [(x, float(y)) for x in (-20.0, 0.0, 20.0) for y in KM[::2]]
_cw, _cr = field(_full, echo_at=[(0, 0)])
check("a_mask_filling_the_periodic_axis_reports_a_saturated_span",
      C.organisation(_cw, _cr, KM, KM, 1.0, PERY)["org_wrap_span_frac"] > 0.95,
      C.organisation(_cw, _cr, KM, KM, 1.0, PERY)["org_wrap_span_frac"])

# --- section 12.9: the anti-collapse gate ------------------------------------
# The suspicion P1 has to answer is the one section 11.4 proved about criterion 1:
# that the rule collapses to a magnitude comparison wearing a costume. So build
# series where chain duration and EVERY magnitude-only statistic disagree, in both
# directions, and make the disagreement the assertion.
LOUD = 10_000.0           # far above any real max|uh|
QUIET = C.UH_FLOOR + 0.5  # barely above the noise gate


def magnitude_says_supercell(val):
    """Any magnitude-only rule -- peak, median, mean -- reads only `val`."""
    return val >= C.UH_FLOOR * 10


loud_hopper = [[dict(centre((i % 2) * 40.0, 0), peak=LOUD)]
               for i in range(len(CH_T))]
quiet_rock = [[dict(centre(0, 0), peak=QUIET)] for i in range(len(CH_T))]

check("anti_collapse_LOUD_but_hopping_rotation_forms_no_chain",
      magnitude_says_supercell(LOUD) and chain(loud_hopper)["p1_min"] == 0.0,
      chain(loud_hopper)["p1_min"])
check("anti_collapse_QUIET_but_steady_rotation_chains_the_whole_window",
      not magnitude_says_supercell(QUIET)
      and chain(quiet_rock)["p1_min"] >= C.T_PERSIST_MIN + C.T_BAND_MIN,
      chain(quiet_rock)["p1_min"])

# The vacuity control, in the shape section 11.4's carried. Remove the displacement
# limit and the linker cannot refuse any hop: P1 collapses to "was there rotation
# above the floor in enough consecutive frames", the two rules AGREE again, and the
# disagreements above are therefore attributable to LINK_KM and not to the framing.
_diag = float(np.hypot(C._period(KM), C._period(KM)))
check("VACUITY_at_an_unbounded_link_radius_the_two_rules_agree_again",
      chain(loud_hopper, link_km=_diag)["p1_min"]
      == chain(quiet_rock, link_km=_diag)["p1_min"] == CH_T[-1] - CH_T[0],
      (chain(loud_hopper, link_km=_diag)["p1_min"],
       chain(quiet_rock, link_km=_diag)["p1_min"]))

# And the converse end: at a zero link radius a MOVING centre chains nothing, so
# both ends of the LINK_KM knob are pinned and neither extreme is where the real
# constant sits. (A stationary centre still chains at radius 0 -- its displacement
# is exactly zero -- which is correct, and is why this uses the drifting series.)
check("VACUITY_at_a_zero_link_radius_a_moving_centre_chains_nothing",
      chain(drifting, link_km=0.0)["p1_min"] == 0.0,
      chain(drifting, link_km=0.0)["p1_min"])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
