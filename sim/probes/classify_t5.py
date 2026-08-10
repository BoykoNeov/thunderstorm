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

WHAT THE SC CONTROL CAN AND CANNOT DO

Criterion 1's threshold is `0.25 x median(SC mature max|uh|)` and SC is scored
against it too -- so at least half of SC's own frames are at or above its own
median, which is four times the threshold. SC therefore classifies SUPERCELL by
ARITHMETIC, on any data, including an empty domain. That is not a bug and the rule
is not being changed to fix it (that would be post-hoc), but it means SC's job is
to SET THE SCALE, not to be an independent check: the live half of the abort
condition is PC. `--only sc,pc` prints the absolute SC median and the SC/PC ratio
so a reader can see the scale separation is measured rather than assumed.
"""
import argparse
import glob
import json
import os

import netCDF4
import numpy as np
from scipy import ndimage

DEFAULT_RUNS = "/home/boiko/thunderstorm/runs"
PROBES = ["t5probe_sc", "t5probe_pc", "t5probe_a", "t5probe_b", "t5probe_c"]

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


def frame_metrics(path):
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
        cref >= DBZ_CELL, xh, yh, cell_km2, DBZ_MIN_AREA_KM2)

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

    # M6 -- containment + drift (validity check, docs section 5)
    m.update(_containment(cref >= DBZ_CELL, xh, yh, "cell"))
    m.update(_containment(np.abs(w).max(axis=0) >= W_UPDRAFT, xh, yh, "w"))
    m["cell_centroid_x_km"], m["cell_centroid_y_km"] = _centroid(
        cref >= DBZ_CELL, xh, yh)
    return m


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


def _boundary_components(mask, xh, yh, cell_km2, min_area_km2):
    """Components whose centroid lies within BOUNDARY_KM of any open wall."""
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
        if min(x - xh[0], xh[-1] - x, y - yh[0], yh[-1] - y) <= BOUNDARY_KM:
            near += 1
    return near


def _containment(mask, xh, yh, tag):
    """Clearance (km) from the mask to each open boundary."""
    if not mask.any():
        return {f"{tag}_clearance_km": None, f"{tag}_extent_km": None}
    jj, ii = np.nonzero(mask)
    x0, x1 = xh[ii.min()], xh[ii.max()]
    y0, y1 = yh[jj.min()], yh[jj.max()]
    clear = min(x0 - xh[0], xh[-1] - x1, y0 - yh[0], yh[-1] - y1)
    return {f"{tag}_clearance_km": round(float(clear), 2),
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
    return {"name": name, "n_frames": len(files),
            "declared_motion": _declared_motion(run_dir),
            "frames": [frame_metrics(f) for f in files]}


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
            json.dump(data, f, indent=1)
        print(f"wrote {args.json}")

    for name, d in data.items():
        print(f"\n=== {name}  ({d['n_frames']} frames, "
              f"declared umove/vmove {d['declared_motion']}) ===")
        print(f"{'t_min':>6} {'max|uh|':>9} {'cells':>5} {'bdry':>4} "
              f"{'updrafts':>8} {'max_w':>7} {'min_w':>7} {'w@(x,y)km':>14} "
              f"{'echoC(x,y)':>14} {'cold_km2':>9} {'minTh':>6} "
              f"{'clearW':>7} {'clearC':>7}")
        for f in d["frames"]:
            loc = f"({f['max_w_x_km']:.0f},{f['max_w_y_km']:.0f})"
            cen = ("-" if f["cell_centroid_x_km"] is None
                   else f"({f['cell_centroid_x_km']:.0f},{f['cell_centroid_y_km']:.0f})")
            print(f"{f['t_min']:6.0f} {f['max_abs_uh']:9.1f} {f['n_cells']:5d} "
                  f"{f['n_boundary_cells']:4d} "
                  f"{f['n_updrafts']:8d} {f['max_w']:7.1f} {f['min_w']:7.1f} "
                  f"{loc:>14} {cen:>14} {f['coldpool_area_km2']:9.0f} "
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

    for name, d in data.items():
        label, ev = classify(d, sc_uh_median)
        dr = drift_fit(d)
        print(f"\n{name}: {label}" + ("   [VOID -- section 5]" if dr["void"] else ""))
        for k, v in ev.items():
            print(f"    {k:<28} {v}")
        if dr["void"]:
            print(f"    {'void_why':<28} {dr['void_why']}")


if __name__ == "__main__":
    main()
