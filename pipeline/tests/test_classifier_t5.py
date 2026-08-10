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

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
