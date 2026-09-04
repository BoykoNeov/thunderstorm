#!/usr/bin/env python3
"""Phase 3 T5s section 5.2 -- score the CAPPED SINGLE-CELL CONTROL.

    python3 sim/probes/score_capped.py

Scores the two capped members against `t5s_neutral_pc` -- the UNCAPPED member of the
pair, same isnd=7 path, byte-identical deck, so the cap is the only variable.

The criterion is section 5.2's, pre-registered before either member ran and sharpened
before either produced output. Nothing here is chosen after the fact; every threshold
is imported from `classify_t5.py`/`births_t5s.py` or is one of T5 section 7.5's own
published numbers.

  INITIATION (one-sided, T5 section 7.5's own "that is convection, not speckle"
  numbers): peak w >= 15 m/s and peak cref >= 49 dBZ at some frame.

  SINGLENESS, primary: strictly fewer births after t = 70 min than t5s_neutral_pc.
  SINGLENESS, secondary: updraft-component count <= the uncapped run's in EVERY
  frame after t = 70 min, and strictly fewer in at least one.

`births_t5s.py` is section 4.2's RETIRED instrument, used here deliberately and for
the one job the retirement did not touch -- see section 5.2 for the argument. Both
runs are scored by the identical instrument, so a shared bias cancels and only the
difference is read.
"""
import os
import sys

import numpy as np
import netCDF4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify_t5 as C          # noqa: E402
import births_t5s as B           # noqa: E402

UNCAPPED = "t5s_neutral_pc"
CAPPED = ["t5s_capped_dt3", "t5s_capped_dt6"]

# T5 section 7.5, verbatim: "peak w 15-32 m/s and 49-56 dBZ -- that is convection,
# not speckle". Reused, not invented.
W_CONVECTION_MS = 15.0
DBZ_CONVECTION = 49.0
T_SECONDARY_MIN = 70.0           # T5 section 7.5's own onset time


def peaks(name, runs=C.DEFAULT_RUNS):
    """Peak w and peak cref over the whole run (cref is not in frame_metrics)."""
    import glob
    files = sorted(glob.glob(os.path.join(runs, name, "cm1out_0*.nc")))
    if not files:
        raise SystemExit(f"{name}: no cm1out_*.nc")
    pw = pd = -1e30
    tw = td = None
    for f in files:
        d = netCDF4.Dataset(f)
        t = float(d.variables["time"][0]) / 60.0
        w = float(np.max(np.asarray(d.variables["winterp"][0], dtype=float)))
        cz = float(np.max(np.asarray(d.variables["cref"][0], dtype=float)))
        d.close()
        if w > pw:
            pw, tw = w, t
        if cz > pd:
            pd, td = cz, t
    return dict(peak_w=pw, peak_w_t_min=tw, peak_cref=pd, peak_cref_t_min=td,
                n_frames=len(files))


def updrafts_after(name, runs=C.DEFAULT_RUNS):
    """(t_min, n_updrafts) per frame with t > T_SECONDARY_MIN, classify_t5's own
    component definition (column-max w >= W_UPDRAFT, area >= W_MIN_AREA_KM2)."""
    r = C.run_metrics(name, runs)
    return [(f["t_min"], f["n_updrafts"]) for f in r["frames"]
            if f["t_min"] > T_SECONDARY_MIN]


def births_after(name, runs=C.DEFAULT_RUNS):
    """Secondary-convection events after the window opens.

    CONFIRMED **plus CENSORED** births, and the reason is section 4.2's own finding:
    a birth late in a 2 h run cannot meet BIRTH_PERSIST_MIN before the run ends, so
    it is right-censored, and PC's ring showed up there -- "0 confirmed" was a
    NON-EXERCISE, not a negative. Counting confirmed births alone would reproduce
    that vacuity exactly. Both components are reported separately as well as summed.

    This choice was fixed by scoring the UNCAPPED reference alone, while the capped
    members were still integrating and had produced no output -- see section 5.2.
    """
    r = B.births(name, runs)
    conf = [b for b in r["births"] if b["t_min"] > T_SECONDARY_MIN]
    cens = [b for b in r["censored_births"] if b["t_min"] > T_SECONDARY_MIN]
    return len(conf) + len(cens), len(conf), len(cens), r


def main():
    runs = C.DEFAULT_RUNS
    print("Phase 3 T5s section 5.2 -- capped single-cell control")
    print(f"  reference (uncapped): {UNCAPPED}")
    print(f"  initiation floor    : peak w >= {W_CONVECTION_MS:g} m/s AND "
          f"peak cref >= {DBZ_CONVECTION:g} dBZ   (T5 section 7.5's own numbers)")
    print(f"  secondary window    : t > {T_SECONDARY_MIN:g} min   (T5 section 7.5)")
    print("=" * 78)

    ref_pk = peaks(UNCAPPED, runs)
    ref_up = updrafts_after(UNCAPPED, runs)
    ref_nb, ref_bc, ref_bx = births_after(UNCAPPED, runs)[:3]
    print(f"\n{UNCAPPED} (UNCAPPED reference)")
    print(f"  peak w    {ref_pk['peak_w']:7.2f} m/s at t={ref_pk['peak_w_t_min']:.0f} min"
          f"   peak cref {ref_pk['peak_cref']:6.2f} dBZ at "
          f"t={ref_pk['peak_cref_t_min']:.0f} min   ({ref_pk['n_frames']} frames)")
    print(f"  births after t={T_SECONDARY_MIN:g} min: {ref_nb} ({ref_bc} confirmed + {ref_bx} censored)")
    print("  updrafts/frame after: " + " ".join(f"{t:.0f}:{n}" for t, n in ref_up))

    verdicts = []
    for name in CAPPED:
        pk = peaks(name, runs)
        up = updrafts_after(name, runs)
        nb, bc, bx = births_after(name, runs)[:3]
        init = pk["peak_w"] >= W_CONVECTION_MS and pk["peak_cref"] >= DBZ_CONVECTION

        aligned = [t for t, _ in up] == [t for t, _ in ref_up]
        le_all = aligned and all(n <= rn for (_, n), (_, rn) in zip(up, ref_up))
        lt_any = aligned and any(n < rn for (_, n), (_, rn) in zip(up, ref_up))
        single_primary = nb < ref_nb
        single_secondary = le_all and lt_any

        print(f"\n{name}")
        print(f"  peak w    {pk['peak_w']:7.2f} m/s at t={pk['peak_w_t_min']:.0f} min"
              f"   peak cref {pk['peak_cref']:6.2f} dBZ at "
              f"t={pk['peak_cref_t_min']:.0f} min   ({pk['n_frames']} frames)")
        print(f"  INITIATION      : {'PASS' if init else 'FAIL'}")
        print(f"  births after t={T_SECONDARY_MIN:g} min: {nb} "
              f"({bc} confirmed + {bx} censored)  vs uncapped {ref_nb} "
              f"({ref_bc}+{ref_bx})   -> primary singleness "
              f"{'PASS' if single_primary else 'FAIL'}")
        if not aligned:
            print("  frame sets NOT aligned -- the per-frame comparison is void")
        print("  updrafts/frame after: " + " ".join(f"{t:.0f}:{n}" for t, n in up))
        print("  paired (capped vs uncapped): " + " ".join(
            f"{t:.0f}:{n}/{rn}" for (t, n), (_, rn) in zip(up, ref_up)))
        print(f"  secondary singleness: <= everywhere {le_all}, "
              f"< somewhere {lt_any} -> {'PASS' if single_secondary else 'FAIL'}")
        verdicts.append((name, init, single_primary, single_secondary))

    print("\n" + "=" * 78)
    for name, init, p1, p2 in verdicts:
        print(f"{name}: initiation {'PASS' if init else 'FAIL'}   "
              f"singleness primary {'PASS' if p1 else 'FAIL'}   "
              f"secondary {'PASS' if p2 else 'FAIL'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
