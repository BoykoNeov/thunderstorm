#!/usr/bin/env python3
"""Phase 3 T5s section 5.3 -- is a frame's updraft-component count ONE RING or N CELLS?

    python3 sim/probes/ring_test.py

Section 5.2's secondary singleness criterion compares `n_updrafts` frame by frame.
That number is a count of connected components of column-max `w`, and in an
AXISYMMETRIC configuration -- zero shear, a centred bubble, a square domain, which
is exactly what the capped control is -- an expanding gust-front ring is chopped
into arcs and counted as many "updrafts". Section 5.2 had already caught this shape
in the uncapped reference (8 births, all at 8.64 km, 18.08 m/s, 5.99 km2, identical
to the decimal). This script decides whether the capped members are the same thing.

PRE-REGISTERED in docs/plan-science-hurdles-2026-09-02.md section 5.3, written and
committed (2b1f11b) BEFORE this file existed, precisely because the "it is a ring,
so the criterion is void" reading is the comfortable one:

    RING   >= 75 % of a frame's components have a centroid radius within +-10 %
           of that frame's MEDIAN component radius. One annulus, cut into arcs.
    CELLS  fewer than 75 % do. Objects at genuinely different distances from the
           ignition point, which one expanding ring cannot produce.
    MIXED  otherwise -- ring members and residual reported SEPARATELY, and the
           residual (the components outside the +-10 % band) is the count section
           5.2's criterion should have used.

Nothing here is new physics or a new threshold: the mask, the area floor and the
connectivity are `classify_t5.py`'s own (`W_UPDRAFT`, `W_MIN_AREA_KM2`, 8-connected),
imported rather than restated, so this measures the same objects the criterion
counted and only asks how they are ARRANGED.
"""
import os
import sys
import glob

import numpy as np
import netCDF4
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify_t5 as C          # noqa: E402

# The three frames named in section 5.3 -- the reference's own ring for calibration,
# and the two frames where the capped counts are highest.
TARGETS = [
    ("t5s_neutral_pc", 120.0),
    ("t5s_capped_dt3", 105.0),
    ("t5s_capped_dt6", 95.0),
]

RADIUS_TOL = 0.10        # +-10 % of the median radius
RING_FRACTION = 0.75     # >= 75 % inside that band => RING


def frame_at(run_dir, t_min, tol_s=1.0):
    """The output file whose time stamp is t_min, by reading the stamps."""
    for f in sorted(glob.glob(os.path.join(run_dir, "cm1out_0*.nc"))):
        d = netCDF4.Dataset(f)
        t = float(d.variables["time"][0])
        d.close()
        if abs(t - t_min * 60.0) <= tol_s:
            return f
    raise SystemExit(f"{run_dir}: no frame at t={t_min} min")


def components(path):
    """Every updraft component of one frame: radius from the domain centre, area, peak w.

    Mask, area floor and connectivity are classify_t5's -- this is the same object
    set the criterion counted.
    """
    d = netCDF4.Dataset(path)
    xh = np.asarray(d.variables["xh"][:], dtype=float)      # km
    yh = np.asarray(d.variables["yh"][:], dtype=float)
    w = np.asarray(d.variables["winterp"][0], dtype=float)  # (z, y, x)
    d.close()

    cell_km2 = float((xh[1] - xh[0]) * (yh[1] - yh[0]))
    # The domain centre is measured, not assumed to be (0, 0).
    cx = 0.5 * (xh[0] + xh[-1])
    cy = 0.5 * (yh[0] + yh[-1])

    colmax = w.max(axis=0)
    mask = colmax >= C.W_UPDRAFT
    if not mask.any():
        return [], (cx, cy)
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    out = []
    for c in range(1, n + 1):
        jj, ii = np.nonzero(lab == c)            # (y, x)
        area = len(ii) * cell_km2
        if area < C.W_MIN_AREA_KM2:
            continue
        x = float(xh[ii].mean())
        y = float(yh[jj].mean())
        out.append({
            "r_km": float(np.hypot(x - cx, y - cy)),
            "x_km": x, "y_km": y,
            "area_km2": float(area),
            "peak_w": float(colmax[jj, ii].max()),
        })
    out.sort(key=lambda c: c["r_km"])
    return out, (cx, cy)


def verdict(comps):
    """Section 5.3's rule, applied exactly as written."""
    if not comps:
        return "EMPTY", 0.0, 0, 0
    r = np.array([c["r_km"] for c in comps])
    med = float(np.median(r))
    if med <= 0:
        return "DEGENERATE", med, 0, len(comps)
    inside = int(np.sum(np.abs(r - med) <= RADIUS_TOL * med))
    frac = inside / len(comps)
    if frac >= RING_FRACTION:
        return "RING", med, inside, len(comps) - inside
    return "CELLS", med, inside, len(comps) - inside


def main():
    runs = C.DEFAULT_RUNS
    print("Phase 3 T5s section 5.3 -- ring-or-cells test")
    print(f"  rule: RING if >= {RING_FRACTION:.0%} of components lie within "
          f"+-{RADIUS_TOL:.0%} of the median radius   (pre-registered)")
    print(f"  mask: column-max w >= {C.W_UPDRAFT} m/s, area >= {C.W_MIN_AREA_KM2} km2, "
          "8-connectivity  (classify_t5's own)")
    print("=" * 78)

    for name, t_min in TARGETS:
        path = frame_at(os.path.join(runs, name), t_min)
        comps, (cx, cy) = components(path)
        v, med, inside, outside = verdict(comps)
        print(f"\n{name}  t={t_min:.0f} min   {os.path.basename(path)}   "
              f"centre=({cx:.1f}, {cy:.1f}) km")
        print(f"  {len(comps)} components   median radius {med:.2f} km   "
              f"{inside} within +-{RADIUS_TOL:.0%}, {outside} outside   -> {v}")
        if comps:
            r = np.array([c["r_km"] for c in comps])
            a = np.array([c["area_km2"] for c in comps])
            p = np.array([c["peak_w"] for c in comps])
            print(f"  radius  min {r.min():7.2f}  max {r.max():7.2f}  "
                  f"spread/median {(r.max() - r.min()) / med:6.3f}")
            print(f"  area    min {a.min():7.2f}  max {a.max():7.2f}  "
                  f"CV {a.std() / a.mean():6.3f} km2")
            print(f"  peak w  min {p.min():7.2f}  max {p.max():7.2f}  "
                  f"CV {p.std() / p.mean():6.3f} m/s")
        for c in comps:
            band = "in " if abs(c["r_km"] - med) <= RADIUS_TOL * med else "OUT"
            print(f"    {band}  r {c['r_km']:7.2f} km   ({c['x_km']:8.2f},{c['y_km']:8.2f})   "
                  f"area {c['area_km2']:7.2f} km2   peak w {c['peak_w']:6.2f} m/s")

    # Section 5.3's logged oddity: all three peak w values sit at the undiluted
    # parcel ceiling. Report the HEIGHT of each run's global max, which is the one
    # thing that would explain it (a spike at or above the zd = 15 km damping layer).
    print("\n" + "=" * 78)
    print("logged (cannot move a one-sided initiation PASS): height of each run's peak w")
    for name, _ in TARGETS:
        best = None
        for f in sorted(glob.glob(os.path.join(runs, name, "cm1out_0*.nc"))):
            d = netCDF4.Dataset(f)
            w = np.asarray(d.variables["winterp"][0], dtype=float)
            zh = np.asarray(d.variables["zh"][:], dtype=float)
            t = float(d.variables["time"][0]) / 60.0
            d.close()
            k = int(np.unravel_index(np.argmax(w), w.shape)[0])
            if best is None or w.max() > best[0]:
                z = zh[k] if zh.ndim == 1 else float(np.asarray(zh).ravel()[k])
                best = (float(w.max()), float(z), t, k)
        print(f"  {name}: peak w {best[0]:.2f} m/s at z = {best[1]:.2f} km "
              f"(level {best[3]}) at t = {best[2]:.0f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
