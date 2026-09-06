#!/usr/bin/env python3
"""Phase 3 T5s section 4.2a -- is a broken P1 at 500 m PHYSICS or FRAGMENTATION?

    python3 sim/probes/coarsen_test.py                 # gates, then both reductions
    python3 sim/probes/coarsen_test.py --gates-only    # instrument gates alone

PRE-REGISTERED in `docs/plan-science-hurdles-2026-09-02.md` section 4.2a, written
and committed while the 500 m run was still in flight and before any of its fields
were opened. Nothing in `classify_t5.py` is touched, and no threshold anywhere moves.

WHY THIS EXISTS. Section 4.2's branch (i) reads a broken P1 as "the rotation stopped
persisting". But P1 chains `uh` components that have first been filtered by
UH_MIN_AREA_KM2, and halving the grid spacing can break that chain with NO physical
change: one blob that cleared the area floor at 1 km can appear at 500 m as several
pieces that individually do not. That is this project's own twice-recorded lesson --
component counting measures fragmentation, not quantity (T5 section 13; T5s section
5.6, where it inverted outright: fewer components, four times the convection).

THE MOVE IS A DIFFERENT REDUCTION, NOT A MOVED THRESHOLD -- the section 5.6 move.
499.5 = 999/2 EXACTLY, so every 1 km cell is exactly four 500 m cells and the 500 m
fields can be block-reduced onto the 1 km grid, with the UNCHANGED classifier then run
on the result. The classifier is not modified and is not even aware: the reduced fields
are written as a derived run directory with the same file and variable layout CM1
produces, and `classify_t5.run_metrics` opens it like any other run.

TWO REDUCTIONS, BOTH REPORTED, NEITHER CHOSEN AFTER THE FACT:

  mean      -- the PRIMARY. The honest analogue of what a coarse grid can represent
               (a 1 km cell cannot hold the gaps between fragments) and the
               CONSERVATIVE direction, since averaging lowers peaks. `cref` is
               averaged in LINEAR Z, not in dB, matching the pipeline's own
               established convention (cm1post/regrid.py::resample_dbz_2d).
  extremum  -- the LENIENT bound: the extremum in the direction the feature lives
               (max for uh/cref/w, MIN for thpert, whose feature is the negative
               cold-pool perturbation -- a block-max there would delete the cold
               pool rather than preserve it).

IF THE TWO DISAGREE, THE COARSENING TEST IS INDETERMINATE AND NEITHER IS CHOSEN.
Picking the reduction that gives the cleaner answer is exactly the move the
pre-registration exists to prevent.

The reduced field is an APPROXIMATION to what CM1 would have computed at 1 km, not a
reconstruction of it. This is a direction test and claims nothing more.

THREE INSTRUMENT GATES run before any verdict is read (the section 5.5 pattern -- the
instrument proves itself on data whose answer is already known):

  G1  the reduced grid's xh/yh equal the 1 km reference run's, to float tolerance;
  G2  the same code path at block size 1 on the 1 km run is the IDENTITY, bitwise,
      on every frame metric the classifier computes;
  G3  block-mean conserves the whole-domain sum by construction, so block^2 times the
      reduced sum must equal the 500 m sum -- a non-zero residual means the reduction
      is wrong, not that the physics moved.
"""
import argparse
import glob
import os
import shutil
import sys

import numpy as np
import netCDF4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import classify_t5 as C  # noqa: E402

RUN_500M = "t5s_us15_500m"
RUN_1KM = "t5s_us15"
BLOCK = 2

# The classifier reads exactly these. Anything else CM1 wrote is not copied: a
# derived run directory that carried fields nobody reads would invite the belief
# that they had been reduced correctly too.
FIELDS_2D = ["uh", "cref"]
FIELDS_3D = ["winterp", "thpert"]


def _blocks(a, b):
    """Reshape trailing (y, x) into (y/b, b, x/b, b) for a block reduction."""
    if a.shape[-1] % b or a.shape[-2] % b:
        raise SystemExit(f"grid {a.shape} not divisible by block {b}")
    lead = a.shape[:-2]
    ny, nx = a.shape[-2] // b, a.shape[-1] // b
    return a.reshape(*lead, ny, b, nx, b)


def reduce_mean(a, b, name):
    if name == "cref":
        # dBZ is logarithmic: average in Z = 10^(dBZ/10), exactly as the pipeline
        # does (cm1post/regrid.py::resample_dbz_2d). 0 dBZ = Z 1.0 = no echo.
        z = np.power(10.0, a.astype("f8") / 10.0)
        z = _blocks(z, b).mean(axis=(-3, -1))
        np.clip(z, 1.0e-12, None, out=z)
        return np.clip(10.0 * np.log10(z), 0.0, None)
    return _blocks(a.astype("f8"), b).mean(axis=(-3, -1))


def reduce_extremum(a, b, name):
    blk = _blocks(a.astype("f8"), b)
    # thpert's feature is the NEGATIVE cold-pool perturbation. max would delete it.
    return blk.min(axis=(-3, -1)) if name == "thpert" else blk.max(axis=(-3, -1))


REDUCERS = {"mean": reduce_mean, "extremum": reduce_extremum}


def write_reduced(src_run, dst_run, block, mode, runs=C.DEFAULT_RUNS):
    """Write a derived run dir the unchanged classifier can open like any other."""
    src, dst = os.path.join(runs, src_run), os.path.join(runs, dst_run)
    files = sorted(glob.glob(os.path.join(src, "cm1out_0*.nc")))
    if not files:
        raise SystemExit(f"{src_run}: no cm1out_*.nc in {src}")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    # scenario.json carries the boundary types and declared motion the classifier
    # reads. It is copied VERBATIM: the reduction changes the grid, not the run.
    shutil.copy2(os.path.join(src, "scenario.json"), os.path.join(dst, "scenario.json"))
    red = REDUCERS[mode]
    sums = {}
    for f in files:
        d = netCDF4.Dataset(f)
        o = netCDF4.Dataset(os.path.join(dst, os.path.basename(f)), "w")
        o.createDimension("time", 1)
        o.createDimension("xh", len(d.dimensions["xh"]) // block)
        o.createDimension("yh", len(d.dimensions["yh"]) // block)
        o.createDimension("zh", len(d.dimensions["zh"]))
        v = o.createVariable("time", "f4", ("time",))
        v[:] = d.variables["time"][:]
        for ax in ("xh", "yh"):
            a = np.asarray(d.variables[ax][:], dtype="f8")
            # Coordinates are ALWAYS block-averaged, in both modes: a cell centre
            # is a coordinate, not a field, and the mean of the two 500 m centres
            # is the 1 km centre exactly.
            v = o.createVariable(ax, "f4", (ax,))
            v[:] = a.reshape(-1, block).mean(axis=1)
        v = o.createVariable("zh", "f4", ("zh",))
        v[:] = d.variables["zh"][:]
        for nm in FIELDS_2D:
            a = np.asarray(d.variables[nm][0], dtype="f8")
            r = red(a, block, nm)
            sums.setdefault(nm, []).append((float(a.sum()), float(r.sum())))
            o.createVariable(nm, "f4", ("time", "yh", "xh"))[0] = r
        for nm in FIELDS_3D:
            a = np.asarray(d.variables[nm][0], dtype="f8")
            r = red(a, block, nm)
            sums.setdefault(nm, []).append((float(a.sum()), float(r.sum())))
            o.createVariable(nm, "f4", ("time", "zh", "yh", "xh"))[0] = r
        o.close()
        d.close()
    return dst, len(files), sums


def gate_g1(reduced_run, ref_run, runs=C.DEFAULT_RUNS):
    def axes(name):
        f = sorted(glob.glob(os.path.join(runs, name, "cm1out_0*.nc")))[0]
        d = netCDF4.Dataset(f)
        a = (np.asarray(d.variables["xh"][:], dtype="f8"),
             np.asarray(d.variables["yh"][:], dtype="f8"))
        d.close()
        return a
    rx, ry = axes(reduced_run)
    fx, fy = axes(ref_run)
    if rx.shape != fx.shape or ry.shape != fy.shape:
        return False, f"shape {rx.shape}/{ry.shape} vs ref {fx.shape}/{fy.shape}"
    dx, dy = float(np.max(np.abs(rx - fx))), float(np.max(np.abs(ry - fy)))
    return (dx <= 1e-5 and dy <= 1e-5), f"max |dx| {dx:.3e} km, max |dy| {dy:.3e} km"


def gate_g2(ref_run, runs=C.DEFAULT_RUNS):
    """Block size 1 must be the IDENTITY on every metric the classifier computes."""
    dst = f"{ref_run}_block1"
    write_reduced(ref_run, dst, 1, "mean", runs=runs)
    a = C.run_metrics(ref_run, runs)
    b = C.run_metrics(dst, runs)
    diffs = []
    for fa, fb in zip(a["frames"], b["frames"]):
        for k, va in fa.items():
            vb = fb.get(k)
            if isinstance(va, float) and isinstance(vb, float):
                if not (np.isnan(va) and np.isnan(vb)) and va != vb:
                    diffs.append((fa["t_min"], k, va, vb))
            elif va != vb:
                diffs.append((fa["t_min"], k, va, vb))
    shutil.rmtree(os.path.join(runs, dst))
    return not diffs, (f"{len(a['frames'])} frames, {len(diffs)} metric differences"
                       + (f"; first {diffs[0]}" if diffs else ""))


def gate_g3(sums, block):
    """Block-MEAN conserves the sum: block^2 * reduced_sum == full_sum."""
    worst, where = 0.0, ""
    for nm, pairs in sums.items():
        if nm == "cref":
            continue  # averaged in linear Z, so the dB sum is not conserved by design
        for full, red in pairs:
            denom = abs(full) if abs(full) > 0 else 1.0
            r = abs(full - block * block * red) / denom
            if r > worst:
                worst, where = r, nm
    return worst <= 1e-12, f"worst relative residual {worst:.3e} ({where or 'n/a'})"


def report(name, runs=C.DEFAULT_RUNS):
    run = C.run_metrics(name, runs)
    label, ev = C.classify_v3(run)
    dr = C.drift_fit(run)
    return {"name": name, "label": label,
            "P1": ev.get("P1_chain_min", 0.0),
            "R": ev.get("median_R"), "E": ev.get("median_E"),
            "qual": ev.get("qualifying_frames"),
            "span": ev.get("echo_span_min"),
            "void": dr["void"], "void_why": dr.get("void_why"),
            "clear_cell": dr["min_cell_clearance_km"],
            "clear_w": dr["min_w_clearance_km"]}


def near_floor_frames(name, runs=C.DEFAULT_RUNS):
    """Mature frames whose largest surviving uh component is within 2x the floor.

    A supporting reading, NOT a criterion: if the chain break lands on a near-floor
    frame, that is the tell, independently of the coarsening test.
    """
    run = C.run_metrics(name, runs)
    out = []
    for f in C.mature(run["frames"]):
        areas = f.get("p1_areas_km2") or []
        if areas and max(areas) < 2.0 * C.UH_MIN_AREA_KM2:
            out.append((f["t_min"], round(max(areas), 1)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=C.DEFAULT_RUNS)
    ap.add_argument("--run", default=RUN_500M)
    ap.add_argument("--ref", default=RUN_1KM)
    ap.add_argument("--block", type=int, default=BLOCK)
    ap.add_argument("--gates-only", action="store_true")
    args = ap.parse_args()

    print(__doc__.split("\n")[0])
    print("=" * 88)

    print("\n--- G2: block size 1 on the reference run must be the identity ---")
    ok2, msg2 = gate_g2(args.ref, args.runs)
    print(f"  {'PASS' if ok2 else 'FAIL'}: {msg2}")

    reduced = {}
    gates = {"G2": ok2}
    for mode in ("mean", "extremum"):
        dst = f"{args.run}_coarse_{mode}"
        _, n, sums = write_reduced(args.run, dst, args.block, mode, runs=args.runs)
        print(f"\n--- {mode}: wrote {n} reduced frames to {dst} ---")
        ok1, msg1 = gate_g1(dst, args.ref, args.runs)
        print(f"  G1 grid identity vs {args.ref}: {'PASS' if ok1 else 'FAIL'} -- {msg1}")
        gates[f"G1/{mode}"] = ok1
        if mode == "mean":
            ok3, msg3 = gate_g3(sums, args.block)
            print(f"  G3 sum conservation            : "
                  f"{'PASS' if ok3 else 'FAIL'} -- {msg3}")
            gates["G3"] = ok3
        reduced[dst] = None

    if not all(gates.values()):
        print("\n!! AN INSTRUMENT GATE FAILED. No verdict is read. "
              "The reduction is wrong, not the physics.")
        return
    if args.gates_only:
        print("\ngates only -- stopping before any verdict is read.")
        return

    names = [args.ref, args.run] + list(reduced)
    results = {n: report(n, args.runs) for n in names}

    print("\n" + "=" * 88)
    print("CONTAINMENT FIRST (a void member is not scorable at any label)")
    for k in (args.ref, args.run):
        r = results[k]
        print(f"  {k:<28} clearance cell/w {r['clear_cell']} / {r['clear_w']} km"
              f"  -> {'VOID: ' + str(r['void_why']) if r['void'] else 'contained'}")

    print("\n" + "=" * 88)
    print(f"{'run':<28}{'label':>13}{'P1':>7}{'R':>8}{'E':>8}{'span':>7}")
    for k in names:
        r = results[k]
        rr = "-" if r["R"] is None else f"{r['R']:.3f}"
        ee = "-" if r["E"] is None else f"{r['E']:.3f}"
        print(f"{k:<28}{r['label']:>13}{r['P1']:>7g}{rr:>8}{ee:>8}{r['span']:>7}")

    print("\nsupporting reading -- mature frames whose largest uh component is within "
          f"2x the {C.UH_MIN_AREA_KM2} km2 floor:")
    for k in (args.ref, args.run):
        print(f"  {k:<28} {near_floor_frames(k, args.runs) or 'none'}")

    print("\nThe decision table is section 4.2a's, fixed before these numbers existed.")
    print("If mean and extremum disagree, the coarsening test is INDETERMINATE and "
          "neither is chosen.")


if __name__ == "__main__":
    main()
