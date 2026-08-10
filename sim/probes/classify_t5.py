#!/usr/bin/env python3
"""Phase 3 T5 -- apply the PRE-REGISTERED classifier to the 1 km probe runs.

    python3 sim/probes/classify_t5.py --only sc,pc      # controls first (do this first)
    python3 sim/probes/classify_t5.py                   # all five
    python3 sim/probes/classify_t5.py --metrics-only    # per-frame table, no labels

WHAT THIS IS

`docs/phase3-t5-multicell.md` sections 3 and 5 fix the metrics, the decision rule,
the controls and the abort condition. That file was committed (de40eb1, 5ab8097)
BEFORE the five probe runs existed. This script is the implementation of that rule
and nothing else: no threshold here may be moved to make a candidate come out a
particular way. If a threshold turns out to be wrong, the correction goes on the
page next to the original -- that is what the doc's header says and it is binding.

THREE THINGS CHANGED FROM THE SCRATCH DRAFT, ALL BEFORE ANY RESULT WAS READ

The draft this grew from lived in a temp dir and had been smoke-tested against a
T4 run (that smoke test is what produced the doc's section 6.2 correction). Three
defects were found while promoting it into the repo, and every one of them is a
case of the CODE disagreeing with the pre-registration -- so fixing them is
doc-faithfulness, not tuning. All three were fixed before the script was ever run
against a T5 probe:

 1. crit3 counted FRAMES-times-cadence and called it minutes; the doc says the
    echo must be non-zero "across >= 60 min", which is a SPAN. A run that flickers
    on and off would have passed the count and failed the span.
 2. crit3 iterated every frame; the doc's section 3.2 preamble scopes the whole
    rule to t >= 40 min. Including the bubble phase is lenient toward MULTICELL --
    an error in the direction of the answer being tested.
 3. Section 5's drift report ("the probe reports the drift rate and the implied
    correct motion") was not implemented at all. It is now (see `drift_fit`). This
    matters most for B and C, whose `umove` is a mean-wind ESTIMATE for a
    cold-pool-driven system, and a storm drifting out of the window depresses
    M1-M3 and can masquerade as "not a supercell".

The twelve pre-registered constants below were checked one by one against
sections 3.1/3.2 and all twelve match the doc.

ONE NUMBER THE PRE-REGISTRATION DID NOT FIX

Section 5 says a drifting candidate's classification is "declared void and
re-run" but never says how close to the wall is too close. That constant is fixed
HERE, before any result: the same 15 km used by the section 6.2 boundary
descriptor. Stated openly because a criterion invented after seeing a marginal
number is worthless.

WHAT THE SC CONTROL CAN AND CANNOT DO -- AND WHAT CHANGED AT SECTION 12

Criterion 1's threshold is `0.25 x median(SC mature max|uh|)` and SC is scored
against it too -- so at least half of SC's own frames are at or above its own
median, which is four times the threshold. SC therefore classifies SUPERCELL by
ARITHMETIC, on any data, including an empty domain. That is not a bug and the rule
is not being changed to fix it (that would be post-hoc), but it means SC's job is
to SET THE SCALE, not to be an independent check: the live half of the abort
condition is PC. `--only sc,pc` prints the absolute SC median and the SC/PC ratio
so a reader can see the scale separation is measured rather than assumed.

That paragraph describes `classify` and `classify_v2`, and it is why section 11.4
went looking: criterion 1 turned out to be a MEDIAN COMPARISON with no temporal
content at all (k_flip == candidate_median / SC_median to 1e-12 on all six runs).
`classify_v3` -- the live rule from section 12 -- replaces it with rotation
PERSISTENCE and takes NO `sc_uh_median` argument at all. That absence is the point:
with no control normalisation there is no self-reference, so SC's SUPERCELL label
is no longer forced and BOTH halves of the abort condition are live for the first
time since section 3. The magnitude floor `classify_v3` does use is a NOISE GATE
set an order of magnitude below every run's rotation (section 12.3), precisely so
it cannot smuggle the median test back in.
"""
import argparse
import glob
import json
import os

import netCDF4
import numpy as np
from scipy import ndimage

DEFAULT_RUNS = "/home/boiko/thunderstorm/runs"
PROBES = ["t5probe_sc", "t5probe_pc", "t5probe_a", "t5probe_b", "t5probe_c",
          "t5probe_c2"]

# --- pre-registered constants (section 3.1) ---------------------------------
DBZ_CELL = 40.0          # composite reflectivity threshold for a "cell"
DBZ_MIN_AREA_KM2 = 10.0  # reject specks
W_UPDRAFT = 10.0         # column-max w threshold for an "updraft"
W_MIN_AREA_KM2 = 4.0
COLDPOOL_K = -2.0        # surface thpert threshold
MATURE_MIN = 40.0        # ignore frames before this (still a bubble)

# --- pre-registered decision rule (section 3.2) -----------------------------
UH_FRACTION_OF_CONTROL = 0.25   # "even a quarter as strong as the known supercell"
UH_FRAC_FRAMES = 0.5            # "less than half its mature life"
MIN_SIMULTANEOUS_UPDRAFTS = 3
MIN_SIMULTANEOUS_CELLS = 2
MIN_FRAMES_WITH_2_CELLS = 5
MIN_SYSTEM_MINUTES = 60.0

# --- section 5 / 6.2 ---------------------------------------------------------
BOUNDARY_KM = 15.0       # "near an open wall", for the 6.2 descriptor AND for the
                         # section-5 void criterion (see docstring)

# --- section 8: criterion 2' (organisation), re-pre-registered 2026-08-10 ----
# The count-based criterion 2 was RETIRED after the PC control classified
# MULTICELL: PC's four >=40 dBZ components had identical areas and identical peaks
# at (+-5,+-5) -- one axisymmetric gust-front ring quantised by a square grid, not
# four cells (section 7.3). `classify` below still implements the retired rule and
# is kept callable so section 7's numbers stay reproducible; `classify_v2` is the
# live one.
R_FLOOR = 0.5            # area-weighted circular resultant: "at least half-coherent"
E_FLOOR = 2.0            # mask elongation: "at least twice as long as wide"
MIN_QUALIFYING_FRAMES = MIN_FRAMES_WITH_2_CELLS   # 5 -- reused, not reinvented
R_BAND = 0.10            # section 8.6 two-sided INDETERMINATE band
E_BAND_FACTOR = 1.20     # ditto, multiplicative: 2.00/1.2 = 1.67 under, 2.40 over

# --- section 12: criterion 1' (persistence), re-pre-registered 2026-08-10 ----
# The median-magnitude criterion 1 was RETIRED after section 11.4 measured what it
# actually computes: with UH_FRAC_FRAMES=0.5 and an odd frame count, "rotating for
# less than half its mature life" IS the median, so criterion 1 is a scalar
# magnitude ratio with zero temporal content (1 frame at 1e6 = not a supercell;
# 17 flat frames at 200 = supercell). `classify_v2` still implements it and stays
# callable so sections 9 and 11 remain reproducible; `classify_v3` is the live one.
#
# UH_FLOOR IS A NOISE GATE, NOT A ROTATION CRITERION, and that is load-bearing
# (section 12.3). Section 11.4's medians are known -- A 1132, SC 679, B 350, C 272,
# C2 197, PC 22 -- so ANY floor in the 150-400 band would reproduce criterion 1's
# median comparison with a new constant and a citation stapled on, including the
# respectable dimensional construction (zeta 1e-2 * w 10 * 3 km ~ 300). 10.0 is
# 19.7x below the LOWEST candidate median and 2.2x below the single-cell control's,
# so every run clears it and PC must be rejected by PERSISTENCE, not by magnitude.
# It may rise only inside the noise-gate band (< 50) and only on the record.
UH_FLOOR = 10.0          # m2/s2 -- see above; NOT a mesocyclone threshold
UH_MIN_AREA_KM2 = W_MIN_AREA_KM2   # 4.0 -- reused, not reinvented (section 8.1)
LINK_KM = 7.5            # max centre displacement per 5-min frame = 25 m/s
T_PERSIST_MIN = 30.0     # > one ordinary cell's lifetime (Byers & Braham 1949)
T_BAND_MIN = 5.0         # section 8.6 two-sided band, quantised to one frame
FLOOR_SWEEP = (5.0, 10.0, 25.0, 50.0, 100.0, 200.0)   # reported diagnostic


def open_sides(run_dir):
    """Which lateral boundaries are OPEN, read from the run's own config.

    Section 5's containment check and section 6.2's boundary descriptor both ask
    "is the storm leaving the window". A PERIODIC boundary is not a window: there
    is nothing to leave and nothing to lose. Candidate C's line necessarily spans
    the domain in y (iinit=8 has no y-extent parameter at all -- the geometry is
    hardcoded in init3d.F), so with open y walls it can never satisfy containment
    and with periodic y walls the question does not arise. Applying a criterion
    written for a compact storm to a periodic direction is what voided C in
    section 9.5; this reads the boundary type instead of assuming it.

    CM1: 1 = periodic, 2 = open-radiative, 3/4 = rigid wall. Absent keys default
    to the template's value, 2 -- so a run that predates this function is treated
    exactly as before.
    """
    try:
        with open(os.path.join(run_dir, "scenario.json")) as f:
            nml = json.load(f)["sim"]["namelist"]
    except (OSError, KeyError, ValueError):
        nml = {}
    return {"x": int(nml.get("wbc", 2)) == 2 or int(nml.get("ebc", 2)) == 2,
            "y": int(nml.get("sbc", 2)) == 2 or int(nml.get("nbc", 2)) == 2}


def periodic_sides(run_dir):
    """Which lateral boundaries are PERIODIC, read from the run's own config.

    The mirror of `open_sides`, and it exists for the same reason: section 9.5
    voided candidate C by applying a compact-storm criterion to a direction that
    has no walls. Section 12.6 is the third instance of that error class, now in
    the chain statistic -- a rotation centre near y_min reappearing near y_max is
    a naive ~180 km jump that breaks a chain which never physically broke, and it
    breaks it TOWARD the answer being sought.

    CM1: 1 = periodic, 2 = open-radiative, 3/4 = rigid wall. CM1 requires the two
    sides of an axis to agree, so either key answers for the axis; both are read
    and an axis counts as periodic only if BOTH say so. Absent keys default to the
    template's 2, so a run predating this function is treated exactly as before.
    """
    try:
        with open(os.path.join(run_dir, "scenario.json")) as f:
            nml = json.load(f)["sim"]["namelist"]
    except (OSError, KeyError, ValueError):
        nml = {}
    return {"x": int(nml.get("wbc", 2)) == 1 and int(nml.get("ebc", 2)) == 1,
            "y": int(nml.get("sbc", 2)) == 1 and int(nml.get("nbc", 2)) == 1}


def _period(coord):
    """The wrap length of a uniformly spaced coordinate vector, in its own units.

    xh[-1] - xh[0] is one cell SHORT of the period: the point after xh[-1] is
    xh[0], not xh[-1]. Getting this wrong puts a one-cell seam in every wrapped
    distance.
    """
    return float(coord[-1] - coord[0]) + float(coord[1] - coord[0])


def wrap_delta(d, period, periodic):
    """Minimum-image displacement: the shortest way round, if there is a way round."""
    if not periodic:
        return d
    return d - period * np.round(d / period)


def label_periodic(mask, periodic):
    """8-connectivity labelling that closes the seam on periodic axes.

    `ndimage.label` is not wrap-aware, so a feature straddling the seam comes back
    as two components. Labels touching across a seam are merged with union-find and
    the result is renumbered 1..n so it drops into the same call sites as
    `ndimage.label`.
    """
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n <= 1:
        return lab, n

    parent = list(range(n + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    def stitch(edge_a, edge_b):
        # 8-connectivity across the seam: index i on one edge touches i-1, i, i+1
        for shift in (-1, 0, 1):
            other = np.roll(edge_b, shift)
            sel = (edge_a > 0) & (other > 0)
            for u, v in zip(edge_a[sel], other[sel]):
                union(int(u), int(v))

    if periodic.get("y"):
        stitch(lab[0, :], lab[-1, :])
    if periodic.get("x"):
        stitch(lab[:, 0], lab[:, -1])

    roots = np.array([find(i) for i in range(n + 1)])
    uniq = np.unique(roots[1:])
    remap = np.zeros(n + 1, dtype=int)
    for new, old in enumerate(uniq, start=1):
        remap[roots == old] = new
    remap[0] = 0
    return remap[lab], int(len(uniq))


def wrapped_centroid(vals, coord, periodic):
    """Mean position of 1-D coordinates, circular where the axis wraps.

    A seam-straddling component's arithmetic mean lands in the middle of the
    domain, nowhere near the feature. The circular mean is the only honest answer
    on a periodic axis; it is also exactly the arithmetic mean when the points are
    compact, so nothing is lost where the axis does not wrap.

    The result is folded back into the axis's OWN range rather than left in
    [0, period): a centroid reported outside the coordinates it was computed from
    is a trap for every downstream reader, and P2 is a reported descriptor.
    """
    vals = np.asarray(vals, dtype=float)
    if not periodic:
        return float(vals.mean())
    period = _period(coord)
    ang = 2.0 * np.pi * vals / period
    m = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) / (2.0 * np.pi) * period
    lo = float(coord[0]) - 0.5 * float(coord[1] - coord[0])   # left cell edge
    return float(lo + (m - lo) % period)


def rotation_centres(uh, xh, yh, cell_km2, floor, periodic):
    """Section 12.4 -- signed rotation centres for one frame.

    Cyclonic (uh >= +floor) and anticyclonic (uh <= -floor) are labelled
    SEPARATELY, not as |uh|. A splitting storm puts the two side by side, and under
    abs() an adjacent couplet merges into one component whose centroid sits BETWEEN
    the movers -- an artifact in exactly the case that decides the SC control.

    MEASURED CAVEAT (section 12.11): CM1's `uh` is non-negative -- min == 0.0 in
    all 50 control frames -- so on THIS output the anticyclonic branch is always
    empty and the split is inactive. It is kept because it is correct, costs
    nothing, and is the difference between an assumption that is checked (`min_uh`
    is recorded per frame) and one that is merely believed. The consequence that
    does bite is scientific, not numerical: a LEFT-moving supercell carries no
    signal in this field at all, for P1 exactly as for M1.
    """
    out = []
    for sign, mask in ((+1, uh >= floor), (-1, uh <= -floor)):
        if not mask.any():
            continue
        lab, n = label_periodic(mask, periodic)
        if n == 0:
            continue
        idx = np.arange(1, n + 1)
        sizes = ndimage.sum(mask, lab, index=idx) * cell_km2
        for c in idx[sizes >= UH_MIN_AREA_KM2]:
            jj, ii = np.nonzero(lab == c)
            out.append({
                "sign": sign,
                "x_km": wrapped_centroid(xh[ii], xh, periodic["x"]),
                "y_km": wrapped_centroid(yh[jj], yh, periodic["y"]),
                "area_km2": round(float(len(ii) * cell_km2), 2),
                "peak": round(float(np.max(np.abs(uh[jj, ii]))), 1),
            })
    return out


def chain_stats(nodes, times, xh, yh, periodic, link_km=LINK_KM, max_gap=1):
    """Section 12.4 -- P1, the longest same-sign displacement-limited chain.

    A LINKER, NOT A TRACKER. T4 section 5.2's argmax tracker hops to whatever is
    brightest and so cannot fail to produce a track; this refuses to hop, and a
    broken chain IS the measurement. Longest path through the frame-ordered DAG by
    dynamic programming -- each node keeps the earliest start time that reaches it.

    `max_gap=1` links consecutive frames only (the pre-registered gate). `max_gap=2`
    tolerates one missing frame and is reported as a DIAGNOSTIC; its displacement
    budget scales with the gap, since a centre absent for a frame had twice as long
    to move.
    """
    px, py = _period(xh), _period(yh)
    best = [[float(t)] * len(cs) for t, cs in zip(times, nodes)]   # earliest start
    back = [[None] * len(cs) for cs in nodes]

    for i in range(1, len(nodes)):
        for ci, c in enumerate(nodes[i]):
            for gap in range(1, max_gap + 1):
                j = i - gap
                if j < 0:
                    break
                for pj, p in enumerate(nodes[j]):
                    if p["sign"] != c["sign"]:
                        continue
                    dx = wrap_delta(c["x_km"] - p["x_km"], px, periodic["x"])
                    dy = wrap_delta(c["y_km"] - p["y_km"], py, periodic["y"])
                    if float(np.hypot(dx, dy)) > link_km * gap:
                        continue
                    if best[j][pj] < best[i][ci]:
                        best[i][ci] = best[j][pj]
                        back[i][ci] = (j, pj)

    # The member lists are in the DEFAULT too, not only on the success path: a
    # consumer of a broken chain should get an empty list, not a KeyError, and a
    # stale list from a previous call is the shape of bug section 13.8 records.
    out = {"p1_min": 0.0, "p1_net_km": None, "p1_path_km": None,
           "p1_sign": None, "p1_start_min": None, "p1_end_min": None,
           "p1_frames": 0, "p1_steps_km": [], "p1_areas_km2": [], "p1_peaks": []}
    bi = bc = None
    bdur = -1.0
    for i, row in enumerate(best):
        for ci, start in enumerate(row):
            if times[i] - start > bdur:
                bdur, bi, bc = times[i] - start, i, ci
    if bi is None or bdur <= 0:
        return out

    path, cur = [], (bi, bc)
    while cur is not None:
        path.append(cur)
        cur = back[cur[0]][cur[1]]
    path.reverse()
    pts = [nodes[i][c] for i, c in path]

    steps = []
    for a, b in zip(pts, pts[1:]):
        dx = wrap_delta(b["x_km"] - a["x_km"], px, periodic["x"])
        dy = wrap_delta(b["y_km"] - a["y_km"], py, periodic["y"])
        steps.append(float(np.hypot(dx, dy)))
    ndx = wrap_delta(pts[-1]["x_km"] - pts[0]["x_km"], px, periodic["x"])
    ndy = wrap_delta(pts[-1]["y_km"] - pts[0]["y_km"], py, periodic["y"])

    out.update({"p1_min": round(float(bdur), 1),
                "p1_net_km": round(float(np.hypot(ndx, ndy)), 2),
                "p1_path_km": round(sum(steps), 2),
                "p1_sign": pts[0]["sign"],
                "p1_start_min": round(float(times[path[0][0]]), 1),
                "p1_end_min": round(float(times[bi]), 1),
                "p1_frames": len(path),
                # Members of the WINNING path, so a descriptor of "one feature or a
                # walk threading distinct cells" reads the chain the DP actually
                # found. Re-walking it greedily outside this function produced a
                # 26 km step -- larger than LINK_KM, i.e. not a chain at all: a
                # reconstruction artifact of exactly T3's kind, reported as data.
                "p1_steps_km": [round(s, 2) for s in steps],
                "p1_areas_km2": [c["area_km2"] for c in pts],
                "p1_peaks": [c["peak"] for c in pts]})
    return out


def frame_metrics(path, opens=None, periodic=None):
    opens = opens if opens is not None else {"x": True, "y": True}
    periodic = periodic if periodic is not None else {"x": False, "y": False}
    d = netCDF4.Dataset(path)
    t = float(d.variables["time"][0])
    xh = np.asarray(d.variables["xh"][:], dtype=float)   # km
    yh = np.asarray(d.variables["yh"][:], dtype=float)
    cell_km2 = float((xh[1] - xh[0]) * (yh[1] - yh[0]))

    uh = np.asarray(d.variables["uh"][0], dtype=float)
    cref = np.asarray(d.variables["cref"][0], dtype=float)
    w = np.asarray(d.variables["winterp"][0], dtype=float)   # (z, y, x)
    thpert_sfc = np.asarray(d.variables["thpert"][0, 0], dtype=float)
    d.close()

    m = {"t_s": t, "t_min": t / 60.0}

    # M1 -- sustained mid-level rotation (frame-invariant; see docs 3.1)
    m["max_abs_uh"] = float(np.max(np.abs(uh)))

    # Section 12.11: CM1 writes a NON-NEGATIVE uh (measured, min == 0.0 exactly in
    # all 50 control frames), so section 3.1's stated reason for max|.| -- "the
    # anticyclonic mover has negative UH" -- does not hold for this output. abs()
    # is an identity here and no published number moves, but the assumption is
    # recorded per frame rather than assumed, so a future run that DOES carry
    # negative UH is visible instead of silently reinterpreting the signed split.
    m["min_uh"] = float(np.min(uh))

    # M2 -- simultaneous cell count (>=40 dBZ composite reflectivity components)
    m["n_cells"], m["cell_area_km2"] = _components(
        cref >= DBZ_CELL, cell_km2, DBZ_MIN_AREA_KM2)

    # M2b -- ADDED after the smoke test (docs section 6.2), a DESCRIPTOR, not a
    # change to the decision rule: how many of those cells sit near an open
    # boundary. Domain-wide initial noise (irandp=1) grows spurious cells there
    # in this low-CIN sounding, and a count that includes them is right about
    # the number and wrong about the storm. Every T5 probe runs irandp=0 so this
    # should read 0 throughout -- which is exactly why it is worth printing.
    m["n_boundary_cells"] = _boundary_components(
        cref >= DBZ_CELL, xh, yh, cell_km2, DBZ_MIN_AREA_KM2, opens)

    # M3 -- simultaneous updraft count (column-max w components) + their peaks
    colmax_w = w.max(axis=0)
    m["n_updrafts"], _ = _components(
        colmax_w >= W_UPDRAFT, cell_km2, W_MIN_AREA_KM2)
    m["updraft_peaks"] = _component_peaks(
        colmax_w >= W_UPDRAFT, colmax_w, cell_km2, W_MIN_AREA_KM2)

    # M4 -- peak-w magnitude AND location (descriptor only, not a gate)
    kz, jy, ix = np.unravel_index(int(np.argmax(w)), w.shape)
    m["max_w"] = float(w[kz, jy, ix])
    m["max_w_x_km"] = float(xh[ix])
    m["max_w_y_km"] = float(yh[jy])
    m["min_w"] = float(np.min(w))

    # M5 -- cold pool (descriptor)
    cold = thpert_sfc <= COLDPOOL_K
    m["coldpool_area_km2"] = float(cold.sum() * cell_km2)
    m["min_thpert_sfc"] = float(np.min(thpert_sfc))

    # M6 -- containment + drift (validity check, docs section 5), measured against
    # the OPEN boundaries only
    m.update(_containment(cref >= DBZ_CELL, xh, yh, "cell", opens))
    m.update(_containment(np.abs(w).max(axis=0) >= W_UPDRAFT, xh, yh, "w", opens))
    m["cell_centroid_x_km"], m["cell_centroid_y_km"] = _centroid(
        cref >= DBZ_CELL, xh, yh)

    # O1 / O2 -- organisation (docs section 8), computed per frame, gated per run
    m.update(organisation(colmax_w, cref, xh, yh, cell_km2, periodic))

    # P1 -- section 12: signed rotation centres, per frame. The CHAIN is a run-level
    # statistic (chain_stats); what a frame can supply is its centres. Computed at
    # every floor in the sweep so section 12.3's reported sensitivity costs no
    # second pass over 25 netCDF files.
    m["rot"] = {f"{fl:g}": rotation_centres(uh, xh, yh, cell_km2, fl, periodic)
                for fl in FLOOR_SWEEP}
    return m


# --- section 8: the organisation statistics ---------------------------------

def organisation(colmax_w, cref, xh, yh, cell_km2, periodic=None):
    """Flank coherence R and mask elongation E for one frame (docs section 8.2).

    A frame QUALIFIES when it has >=2 updraft components and a >=40 dBZ echo to
    anchor directions on. R is undefined without an independent anchor -- taking
    the components' own mean would force R == 0 by construction -- so the echo
    centroid is used and a frame with no echo does not qualify.

    SECTION 12.6: labelling, the anchor, the component centroids and the covariance
    are all wrap-aware. On a non-periodic run every one of these reduces EXACTLY to
    what it was, so sections 9 and 11 are bit-identical for SC/PC/A/B/C; only C2 can
    move, and section 13 records whether it did.

    The honest limit, because wrap-awareness does not manufacture one: a feature
    spanning the WHOLE periodic axis has no well-defined extent along it. The
    circular mean of a uniform ring is degenerate and its circular variance
    saturates. `org_wrap_span_frac` reports how much of a periodic axis the updraft
    mask occupies, so a saturated E is visible instead of being read as elongation.
    """
    periodic = periodic if periodic is not None else {"x": False, "y": False}
    out = {"org_ncomp": 0, "org_qualifies": False, "R": None, "E": None,
           "org_min_anchor_km": None, "org_wrap_span_frac": None}

    emask = cref >= DBZ_CELL
    umask = colmax_w >= W_UPDRAFT
    if not emask.any() or not umask.any():
        return out

    lab, n = label_periodic(umask, periodic)
    if n == 0:
        return out
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum(umask, lab, index=idx) * cell_km2
    keep = idx[sizes >= W_MIN_AREA_KM2]
    if len(keep) < 2:
        out["org_ncomp"] = int(len(keep))
        return out

    px, py = _period(xh), _period(yh)
    jj, ii = np.nonzero(emask)
    ax = wrapped_centroid(xh[ii], xh, periodic["x"])
    ay = wrapped_centroid(yh[jj], yh, periodic["y"])

    # O1 -- area-weighted circular resultant length about the echo centroid.
    #
    # NOTE the grid-snapped component centroid on a NON-periodic axis. It is a
    # half-cell imprecision and an exact mean would be better -- but replacing it
    # here would silently move the R values PUBLISHED in sections 9 and 11 for all
    # five open-boundary runs (measured: SC 0.4854 -> 0.4821, A 0.5064 -> 0.5211,
    # B 0.1924 -> 0.1744), post-scoring, in a round whose whole justification is
    # that it implements a pre-commitment. Section 12.6 promised exactly ONE
    # recomputation -- C2's E -- so this stays bit-for-bit as it was and the
    # imprecision is recorded in section 13 as a known defect for a future round.
    cents = ndimage.center_of_mass(umask, lab, index=keep)
    areas = ndimage.sum(umask, lab, index=keep) * cell_km2
    num = np.zeros(2)
    den = 0.0
    dists = []
    for c, (cy, cx), a in zip(keep, cents, areas):
        if periodic["x"] or periodic["y"]:
            cjj, cii = np.nonzero(lab == c)
            gx = (wrapped_centroid(xh[cii], xh, True) if periodic["x"]
                  else float(xh[int(round(cx))]))
            gy = (wrapped_centroid(yh[cjj], yh, True) if periodic["y"]
                  else float(yh[int(round(cy))]))
        else:
            gx, gy = float(xh[int(round(cx))]), float(yh[int(round(cy))])
        dvec = np.array([wrap_delta(gx - ax, px, periodic["x"]),
                         wrap_delta(gy - ay, py, periodic["y"])])
        dist = float(np.hypot(*dvec))
        dists.append(dist)
        if dist == 0.0:          # direction undefined: skipped, not counted as 0
            continue
        num += a * dvec / dist
        den += a

    out["org_ncomp"] = int(len(keep))
    out["org_qualifies"] = True
    out["org_min_anchor_km"] = round(min(dists), 2) if dists else None
    out["R"] = round(float(np.hypot(*num) / den), 4) if den else None

    # O2 -- elongation of the surviving mask's VOXELS, not of the component
    # centroids. From 3 centroid points the axis ratio is biased hard (median E
    # 3.72 under an isotropic null, 79.7% of triples clearing 2.0, docs 8.2); the
    # voxel covariance has n in the thousands and no such bias. Needs >=3
    # components for an elongation statement to mean anything.
    if len(keep) >= 3:
        kept = np.isin(lab, keep)
        jj2, ii2 = np.nonzero(kept)
        # Displacements from the mask's own (circular) mean, minimum-image on a
        # periodic axis -- otherwise a seam-straddling mask has an inflated
        # variance along that axis and reads as elongated purely from wrapping.
        mx = wrapped_centroid(xh[ii2], xh, periodic["x"])
        my = wrapped_centroid(yh[jj2], yh, periodic["y"])
        pts = np.stack([wrap_delta(xh[ii2] - mx, px, periodic["x"]),
                        wrap_delta(yh[jj2] - my, py, periodic["y"])], axis=1)
        pts = pts - pts.mean(axis=0)
        cov = (pts.T @ pts) / len(pts)
        ev = np.clip(np.linalg.eigvalsh(cov), 1e-12, None)
        out["E"] = round(float(np.sqrt(ev[1] / ev[0])), 3)
        span = []
        if periodic["x"]:
            span.append(len(np.unique(ii2)) / float(len(xh)))
        if periodic["y"]:
            span.append(len(np.unique(jj2)) / float(len(yh)))
        out["org_wrap_span_frac"] = round(max(span), 3) if span else None
    return out


def _components(mask, cell_km2, min_area_km2):
    """Connected components (8-connectivity) above a minimum area.

    ndimage.label deliberately, NOT an argmax tracker -- the argmax tracker is
    the tool that failed in T4 section 5.2.
    """
    if not mask.any():
        return 0, 0.0
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return 0, 0.0
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = sizes * cell_km2 >= min_area_km2
    return int(keep.sum()), float(sizes[keep].sum() * cell_km2)


def _component_peaks(mask, field, cell_km2, min_area_km2):
    if not mask.any():
        return []
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return []
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum(mask, lab, index=idx)
    peaks = ndimage.maximum(field, lab, index=idx)
    return sorted((round(float(p), 2) for p, s in zip(peaks, sizes)
                   if s * cell_km2 >= min_area_km2), reverse=True)


def _boundary_components(mask, xh, yh, cell_km2, min_area_km2, opens):
    """Components whose centroid lies within BOUNDARY_KM of any OPEN wall."""
    if not mask.any():
        return 0
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return 0
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum(mask, lab, index=idx)
    keep = idx[sizes * cell_km2 >= min_area_km2]
    if not len(keep):
        return 0
    near = 0
    for cy, cx in ndimage.center_of_mass(mask, lab, index=keep):
        x = xh[int(round(cx))]
        y = yh[int(round(cy))]
        d = []
        if opens["x"]:
            d += [x - xh[0], xh[-1] - x]
        if opens["y"]:
            d += [y - yh[0], yh[-1] - y]
        if d and min(d) <= BOUNDARY_KM:
            near += 1
    return near


def _containment(mask, xh, yh, tag, opens):
    """Clearance (km) from the mask to each OPEN boundary.

    None when the mask is empty OR when no boundary is open -- in the second case
    there is no containment question to answer, and reporting a number would
    invite the section 9.5 error in reverse.
    """
    if not mask.any():
        return {f"{tag}_clearance_km": None, f"{tag}_extent_km": None}
    jj, ii = np.nonzero(mask)
    x0, x1 = xh[ii.min()], xh[ii.max()]
    y0, y1 = yh[jj.min()], yh[jj.max()]
    d = []
    if opens["x"]:
        d += [x0 - xh[0], xh[-1] - x1]
    if opens["y"]:
        d += [y0 - yh[0], yh[-1] - y1]
    return {f"{tag}_clearance_km": round(float(min(d)), 2) if d else None,
            f"{tag}_extent_km": [round(float(v), 2) for v in (x0, x1, y0, y1)]}


def _centroid(mask, xh, yh):
    if not mask.any():
        return None, None
    jj, ii = np.nonzero(mask)
    return round(float(xh[ii].mean()), 2), round(float(yh[jj].mean()), 2)


def run_metrics(name, runs=DEFAULT_RUNS):
    run_dir = os.path.join(runs, name)
    files = sorted(glob.glob(os.path.join(run_dir, "cm1out_0*.nc")))
    if not files:
        raise SystemExit(f"{name}: no cm1out_*.nc in {run_dir}")
    opens = open_sides(run_dir)
    periodic = periodic_sides(run_dir)
    d0 = netCDF4.Dataset(files[0])
    xh = np.asarray(d0.variables["xh"][:], dtype=float)
    yh = np.asarray(d0.variables["yh"][:], dtype=float)
    d0.close()
    return {"name": name, "n_frames": len(files),
            "declared_motion": _declared_motion(run_dir),
            "open_sides": opens, "periodic_sides": periodic,
            "xh": xh, "yh": yh,
            "frames": [frame_metrics(f, opens, periodic) for f in files]}


def run_chain(run, floor=UH_FLOOR, link_km=LINK_KM, max_gap=1):
    """P1 over a run's MATURE frames (section 12.4).

    Scoped to t >= 40 min like every other part of the rule -- including the bubble
    phase would let a chain start before there is a storm, which is lenient toward
    the SUPERCELL side of criterion 1'.
    """
    fr = mature(run["frames"])
    key = f"{float(floor):g}"
    nodes = [f.get("rot", {}).get(key, []) for f in fr]
    times = [f["t_min"] for f in fr]
    return chain_stats(nodes, times, run["xh"], run["yh"],
                       run.get("periodic_sides", {"x": False, "y": False}),
                       link_km=link_km, max_gap=max_gap)


def _declared_motion(run_dir):
    """(umove, vmove) the run was actually given, read from its own config.

    Needed to turn a measured drift into an IMPLIED CORRECT MOTION rather than
    just a drift rate: the centroid moves in the domain frame, so the motion the
    storm wanted is what the run was given plus what it drifted.
    """
    try:
        with open(os.path.join(run_dir, "scenario.json")) as f:
            nml = json.load(f)["sim"]["namelist"]
        return (float(nml.get("umove", 0.0)), float(nml.get("vmove", 0.0)))
    except (OSError, KeyError, ValueError):
        return (None, None)


# --- section 5: drift and the void criterion --------------------------------

def drift_fit(run):
    """Least-squares drift of the >=40 dBZ centroid over the MATURE frames.

    Section 5 pre-registers that the probe "reports the drift rate and the
    implied correct motion" for a system heading toward a wall. `umove/vmove`
    for candidates B and C is a mean-0-6km-wind estimate, which the doc itself
    flags as a guess for a cold-pool-driven system.
    """
    fr = [f for f in mature(run["frames"]) if f["cell_centroid_x_km"] is not None]
    out = {"drift_u_ms": None, "drift_v_ms": None,
           "implied_umove": None, "implied_vmove": None,
           "min_cell_clearance_km": None, "min_w_clearance_km": None,
           "void": False, "void_why": None}

    clears = [f["cell_clearance_km"] for f in mature(run["frames"])
              if f["cell_clearance_km"] is not None]
    wclears = [f["w_clearance_km"] for f in mature(run["frames"])
               if f["w_clearance_km"] is not None]
    if clears:
        out["min_cell_clearance_km"] = round(min(clears), 2)
    if wclears:
        out["min_w_clearance_km"] = round(min(wclears), 2)

    if len(fr) >= 3:
        t = np.array([f["t_s"] for f in fr], dtype=float)
        x = np.array([f["cell_centroid_x_km"] for f in fr], dtype=float) * 1000.0
        y = np.array([f["cell_centroid_y_km"] for f in fr], dtype=float) * 1000.0
        du = float(np.polyfit(t, x, 1)[0])
        dv = float(np.polyfit(t, y, 1)[0])
        out["drift_u_ms"] = round(du, 2)
        out["drift_v_ms"] = round(dv, 2)
        um, vm = run["declared_motion"]
        if um is not None:
            out["implied_umove"] = round(um + du, 2)
            out["implied_vmove"] = round(vm + dv, 2)

    worst = [c for c in (out["min_cell_clearance_km"], out["min_w_clearance_km"])
             if c is not None]
    if worst and min(worst) < BOUNDARY_KM:
        out["void"] = True
        out["void_why"] = (f"clearance {min(worst):.2f} km < {BOUNDARY_KM:.0f} km "
                           f"in a mature frame -- section 5 voids this run")
    return out


# --- decision rule ----------------------------------------------------------

def mature(frames):
    return [f for f in frames if f["t_min"] >= MATURE_MIN]


def classify(cand, sc_uh_median):
    """The pre-registered rule, section 3.2. Returns (label, evidence)."""
    fr = mature(cand["frames"])
    if not fr:
        return "INDETERMINATE", {"why": "no mature frames"}

    thresh = UH_FRACTION_OF_CONTROL * sc_uh_median
    n_rot = sum(1 for f in fr if f["max_abs_uh"] >= thresh)
    frac_rot = n_rot / len(fr)
    crit1 = frac_rot < UH_FRAC_FRAMES                       # "not a supercell"

    max_updrafts = max(f["n_updrafts"] for f in fr)
    frames_2cells = sum(1 for f in fr if f["n_cells"] >= MIN_SIMULTANEOUS_CELLS)
    crit2 = (max_updrafts >= MIN_SIMULTANEOUS_UPDRAFTS
             or frames_2cells >= MIN_FRAMES_WITH_2_CELLS)   # "not a single cell"

    # crit3 -- "non-zero ACROSS >= 60 min": a SPAN, over the mature frames the
    # rule is scoped to. Both the span and the frame count are reported, but only
    # the span gates (see the docstring: the draft gated the count, which a
    # flickering echo would have passed).
    echo = [f for f in fr if f["n_cells"] >= 1]
    echo_span = (echo[-1]["t_min"] - echo[0]["t_min"]) if len(echo) >= 2 else 0.0
    crit3 = echo_span >= MIN_SYSTEM_MINUTES                  # "sustained system"

    ev = {
        "uh_threshold": round(thresh, 1),
        "frac_frames_rotating": round(frac_rot, 3),
        "max_simultaneous_updrafts": max_updrafts,
        "frames_with_2plus_cells": frames_2cells,
        "echo_span_min": round(echo_span, 1),
        "echo_frames_mature": len(echo),
        "crit1_not_supercell": crit1,
        "crit2_not_single_cell": crit2,
        "crit3_sustained_system": crit3,
    }

    if not crit1:
        return "SUPERCELL", ev          # rotation outvotes cell count, by design
    if crit1 and crit2 and crit3:
        return "MULTICELL", ev
    if crit1 and not crit2:
        return "SINGLE CELL", ev
    return "INDETERMINATE", ev


def classify_v2(cand, sc_uh_median):
    """The LIVE rule: section 3.2 with criterion 2 replaced by section 8's
    criterion 2' (organised multiplicity). Returns (label, evidence).

    Criterion 1 and criterion 3 are untouched, as are all six field thresholds --
    section 8.1. Criterion 1 is evaluated FIRST and rotation outvotes everything:
    a splitting supercell puts two movers on opposite flanks, so R ~ 0 and it would
    FAIL criterion 2'. It must never reach it (section 8.3).
    """
    fr = mature(cand["frames"])
    if not fr:
        return "INDETERMINATE", {"why": "no mature frames"}

    thresh = UH_FRACTION_OF_CONTROL * sc_uh_median
    frac_rot = sum(1 for f in fr if f["max_abs_uh"] >= thresh) / len(fr)
    crit1 = frac_rot < UH_FRAC_FRAMES

    qual = [f for f in fr if f.get("org_qualifies") and f.get("R") is not None]
    rs = [f["R"] for f in qual]
    es = [f["E"] for f in qual if f.get("E") is not None]
    r_med = float(np.median(rs)) if rs else None
    e_med = float(np.median(es)) if es else None

    # Section 8.6: the floors carry a two-sided band. "Organised" means a statistic
    # clears its floor DECISIVELY (past the upper band edge); a statistic sitting
    # inside the band is uncertainty, not evidence, in either direction. The band
    # is per-statistic and criterion 2' is an OR, so a decisive R is not made
    # uncertain by an E that happens to sit near its own floor.
    enough = len(qual) >= MIN_QUALIFYING_FRAMES
    organised = ((r_med is not None and r_med >= R_FLOOR + R_BAND)
                 or (e_med is not None and e_med >= E_FLOOR * E_BAND_FACTOR))
    crit2p = enough and organised

    echo = [f for f in fr if f["n_cells"] >= 1]
    echo_span = (echo[-1]["t_min"] - echo[0]["t_min"]) if len(echo) >= 2 else 0.0
    crit3 = echo_span >= MIN_SYSTEM_MINUTES

    # Section 8.6: a two-sided band around each floor is INDETERMINATE, not a
    # result. The under-side exists for candidate B (weak shear, plausible landing
    # zone R ~ 0.3-0.5); a one-sided band is a thumb on the scale.
    near = []
    if r_med is not None and R_FLOOR - R_BAND <= r_med < R_FLOOR + R_BAND:
        near.append(f"R={r_med:.3f} within {R_BAND} of the {R_FLOOR} floor")
    if e_med is not None and (E_FLOOR / E_BAND_FACTOR <= e_med
                              < E_FLOOR * E_BAND_FACTOR):
        near.append(f"E={e_med:.2f} within x{E_BAND_FACTOR} of the {E_FLOOR} floor")

    ev = {
        "uh_threshold": round(thresh, 1),
        "frac_frames_rotating": round(frac_rot, 3),
        "qualifying_frames": len(qual),
        "median_R": None if r_med is None else round(r_med, 4),
        "median_E": None if e_med is None else round(e_med, 3),
        "R_range": [round(min(rs), 4), round(max(rs), 4)] if rs else None,
        "E_range": [round(min(es), 3), round(max(es), 3)] if es else None,
        "echo_span_min": round(echo_span, 1),
        "crit1_not_supercell": crit1,
        "crit2p_organised_multiplicity": crit2p,
        "crit2p_enough_frames": enough,
        "crit2p_organised": organised,
        "crit3_sustained_system": crit3,
        "near_floor": near or None,
    }

    if not crit1:
        return "SUPERCELL", ev          # rotation outvotes organisation, by design
    if near and enough and not organised:
        return "INDETERMINATE", ev      # section 8.6, before any label is banked
    if crit2p and crit3:
        return "MULTICELL", ev
    if not crit2p:
        return "SINGLE CELL", ev
    return "INDETERMINATE", ev


def classify_v3(cand, floor=UH_FLOOR):
    """The LIVE rule: section 8's criterion 2', with criterion 1 replaced by
    section 12's criterion 1' (rotation PERSISTENCE). Returns (label, evidence).

    Criterion 2', criterion 3, the mature window and all six field thresholds are
    untouched (section 12.2). Criterion 1' is still evaluated FIRST and rotation
    still outvotes organisation: a splitting supercell has R ~ 0 and would FAIL
    criterion 2', so it must never reach it (section 8.3).

    NOTE the signature: no `sc_uh_median`. That absence IS section 11.6's
    constraint 2 -- no control normalisation, so nothing here can be a
    candidate/control ratio, and SC's label is no longer arithmetically forced.
    """
    fr = mature(cand["frames"])
    if not fr:
        return "INDETERMINATE", {"why": "no mature frames"}

    ch = run_chain(cand, floor=floor)
    gap = run_chain(cand, floor=floor, max_gap=2)
    p1 = ch["p1_min"]

    # Section 12.5's two-sided band, quantised to one frame. A candidate landing
    # just under the floor is not a MULTICELL result to be banked, and one landing
    # just over is not a SUPERCELL result either.
    persists = p1 >= T_PERSIST_MIN + T_BAND_MIN     # banks "supercell"
    crit1p = p1 <= T_PERSIST_MIN - T_BAND_MIN       # banks "not a supercell"

    qual = [f for f in fr if f.get("org_qualifies") and f.get("R") is not None]
    rs = [f["R"] for f in qual]
    es = [f["E"] for f in qual if f.get("E") is not None]
    r_med = float(np.median(rs)) if rs else None
    e_med = float(np.median(es)) if es else None
    enough = len(qual) >= MIN_QUALIFYING_FRAMES
    organised = ((r_med is not None and r_med >= R_FLOOR + R_BAND)
                 or (e_med is not None and e_med >= E_FLOOR * E_BAND_FACTOR))
    crit2p = enough and organised

    echo = [f for f in fr if f["n_cells"] >= 1]
    echo_span = (echo[-1]["t_min"] - echo[0]["t_min"]) if len(echo) >= 2 else 0.0
    crit3 = echo_span >= MIN_SYSTEM_MINUTES

    near = []
    if not persists and not crit1p:
        near.append(f"P1={p1:.0f} min inside the {T_BAND_MIN:.0f}-min band "
                    f"around T_PERSIST={T_PERSIST_MIN:.0f}")
    if r_med is not None and R_FLOOR - R_BAND <= r_med < R_FLOOR + R_BAND:
        near.append(f"R={r_med:.3f} within {R_BAND} of the {R_FLOOR} floor")
    if e_med is not None and (E_FLOOR / E_BAND_FACTOR <= e_med
                              < E_FLOOR * E_BAND_FACTOR):
        near.append(f"E={e_med:.2f} within x{E_BAND_FACTOR} of the {E_FLOOR} floor")

    ev = {
        "uh_floor": floor,
        "P1_chain_min": p1,
        "P1_chain_min_1gap": gap["p1_min"],
        "P1_sign": ch["p1_sign"],
        "P1_window": [ch["p1_start_min"], ch["p1_end_min"]],
        "P2_net_km": ch["p1_net_km"],
        "P2_path_km": ch["p1_path_km"],
        "qualifying_frames": len(qual),
        "median_R": None if r_med is None else round(r_med, 4),
        "median_E": None if e_med is None else round(e_med, 3),
        "echo_span_min": round(echo_span, 1),
        "crit1p_not_supercell": crit1p,
        "crit2p_organised_multiplicity": crit2p,
        "crit3_sustained_system": crit3,
        "near_band": near or None,
    }

    if persists:
        return "SUPERCELL", ev          # rotation outvotes organisation, by design
    if not crit1p:
        return "INDETERMINATE", ev      # section 12.5's band, before a label is banked
    if near and enough and not organised:
        return "INDETERMINATE", ev      # section 8.6's band, unchanged
    if crit2p and crit3:
        return "MULTICELL", ev
    if not crit2p:
        return "SINGLE CELL", ev
    return "INDETERMINATE", ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=DEFAULT_RUNS)
    ap.add_argument("--only", help="comma-separated suffixes, e.g. sc,pc")
    ap.add_argument("--metrics-only", action="store_true")
    ap.add_argument("--json", help="write full metrics here")
    args = ap.parse_args()

    names = PROBES
    if args.only:
        want = [s.strip() for s in args.only.split(",")]
        names = [f"t5probe_{s}" for s in want]

    data = {}
    for name in names:
        try:
            data[name] = run_metrics(name, args.runs)
        except SystemExit as e:
            print(f"!! {e}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump({k: dict(v, xh=list(v["xh"]), yh=list(v["yh"]))
                       for k, v in data.items()}, f, indent=1)
        print(f"wrote {args.json}")

    for name, d in data.items():
        print(f"\n=== {name}  ({d['n_frames']} frames, "
              f"declared umove/vmove {d['declared_motion']}, "
              f"open sides {'x' if d['open_sides']['x'] else ''}"
              f"{'y' if d['open_sides']['y'] else ''} ) ===")
        print(f"{'t_min':>6} {'max|uh|':>9} {'cells':>5} {'bdry':>4} "
              f"{'updrafts':>8} {'max_w':>7} {'min_w':>7} {'w@(x,y)km':>14} "
              f"{'echoC(x,y)':>14} {'R':>6} {'E':>6} {'anch':>5} "
              f"{'cold_km2':>9} {'minTh':>6} {'clearW':>7} {'clearC':>7}")
        for f in d["frames"]:
            loc = f"({f['max_w_x_km']:.0f},{f['max_w_y_km']:.0f})"
            cen = ("-" if f["cell_centroid_x_km"] is None
                   else f"({f['cell_centroid_x_km']:.0f},{f['cell_centroid_y_km']:.0f})")
            rr = "-" if f.get("R") is None else f"{f['R']:.3f}"
            ee = "-" if f.get("E") is None else f"{f['E']:.2f}"
            an = "-" if f.get("org_min_anchor_km") is None else f"{f['org_min_anchor_km']:.1f}"
            print(f"{f['t_min']:6.0f} {f['max_abs_uh']:9.1f} {f['n_cells']:5d} "
                  f"{f['n_boundary_cells']:4d} "
                  f"{f['n_updrafts']:8d} {f['max_w']:7.1f} {f['min_w']:7.1f} "
                  f"{loc:>14} {cen:>14} {rr:>6} {ee:>6} {an:>5} "
                  f"{f['coldpool_area_km2']:9.0f} "
                  f"{f['min_thpert_sfc']:6.1f} "
                  f"{str(f['w_clearance_km']):>7} {str(f['cell_clearance_km']):>7}")

        bdry = sum(f["n_boundary_cells"] for f in d["frames"])
        print(f"  section 6.2 descriptor: boundary-cell frames total = {bdry} "
              f"(expected 0 at irandp=0)")
        dr = drift_fit(d)
        print(f"  section 5 drift: u={dr['drift_u_ms']} v={dr['drift_v_ms']} m/s "
              f"-> implied umove/vmove {dr['implied_umove']}/{dr['implied_vmove']}"
              f"   min clearance cell={dr['min_cell_clearance_km']} "
              f"w={dr['min_w_clearance_km']} km")
        if dr["void"]:
            print(f"  !! VOID: {dr['void_why']}")

    if args.metrics_only or "t5probe_sc" not in data:
        return

    sc_fr = mature(data["t5probe_sc"]["frames"])
    sc_uh_median = float(np.median([f["max_abs_uh"] for f in sc_fr]))
    print("\n=== decision rule (docs section 3.2) ===")
    print(f"control SC median mature max|uh| = {sc_uh_median:.1f} m2/s2  "
          f"-> criterion-1 threshold {UH_FRACTION_OF_CONTROL * sc_uh_median:.1f}")
    if "t5probe_pc" in data:
        pc_fr = mature(data["t5probe_pc"]["frames"])
        pc_med = float(np.median([f["max_abs_uh"] for f in pc_fr]))
        print(f"control PC median mature max|uh| = {pc_med:.1f} m2/s2  "
              f"-> SC/PC ratio = {sc_uh_median / pc_med:.1f}x"
              if pc_med else f"control PC median mature max|uh| = {pc_med:.1f}")
        print("NOTE: SC's own label is arithmetically forced (see docstring); the "
              "live half of the abort condition is PC.")

    print(f"floors (section 8.2): R >= {R_FLOOR}, E >= {E_FLOOR}, "
          f">= {MIN_QUALIFYING_FRAMES} qualifying frames")
    print(f"criterion 1' (section 12): UH_FLOOR={UH_FLOOR} (NOISE GATE -- 19.7x below "
          f"the lowest candidate median), LINK_KM={LINK_KM}/frame, "
          f"T_PERSIST={T_PERSIST_MIN} +-{T_BAND_MIN} min")

    # Section 12.3's floor sweep -- a REPORTED diagnostic, not a hidden sensitivity.
    print("\n=== section 12.3 floor sweep: P1 (min) vs UH_FLOOR ===")
    print(f"{'run':<14}" + "".join(f"{fl:>8g}" for fl in FLOOR_SWEEP)
          + "   (T_PERSIST band 25 / 35)")
    for name, d in data.items():
        print(f"{name:<14}"
              + "".join(f"{run_chain(d, floor=fl)['p1_min']:>8.0f}"
                        for fl in FLOOR_SWEEP))

    for name, d in data.items():
        label, ev = classify_v3(d)
        v2, _ = classify_v2(d, sc_uh_median)
        old, _ = classify(d, sc_uh_median)
        dr = drift_fit(d)
        print(f"\n{name}: {label}" + ("   [VOID -- section 5]" if dr["void"] else "")
              + f"\n    (retired median rule said: {v2}; retired count rule: {old})")
        for k, v in ev.items():
            print(f"    {k:<32} {v}")
        # Section 12.5: the LINK_KM budget is reported against the measured drift,
        # so "the link radius covered the motion" is a number and not an assumption.
        if dr["drift_u_ms"] is not None:
            per_frame = np.hypot(dr["drift_u_ms"], dr["drift_v_ms"]) * 300.0 / 1000.0
            print(f"    {'drift vs LINK_KM budget':<32} "
                  f"{per_frame:.2f} km/frame of {LINK_KM} "
                  f"({100 * per_frame / LINK_KM:.0f}% of budget)")
        if dr["void"]:
            print(f"    {'void_why':<32} {dr['void_why']}")


if __name__ == "__main__":
    main()
