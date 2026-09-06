"""Is t5s_us15's two-component echo a LINE or a SPLITTING PAIR?

T5 section 8.3: "a splitting supercell puts two movers on opposite flanks, so R ~ 0
and it would FAIL criterion 2' -- it must never reach it." Criterion 2' was designed
assuming criterion 1' screens splits out first. P1 is at its ceiling, so that screen
is gone, and us15's decisive verdict rests on exactly two >=40 dBZ components.

A SPLIT: two components that SEPARATE monotonically, on opposite flanks.
A LINE:  two components at roughly constant separation, no systematic divergence.

(The rotation-SIGN test is unavailable: H4 / T5 section 13.7 measured CM1's `uh` as
non-negative, so every rotation centre reads sign +1. Geometry is what is left.)
"""
import argparse
import os
import sys

import netCDF4
import numpy as np
from scipy import ndimage

sys.path.insert(0, "/mnt/m/claud_projects/thunderstorm/sim/probes")
import classify_t5 as C  # noqa: E402

RUNS = C.DEFAULT_RUNS


def echo_components(path):
    d = netCDF4.Dataset(path)
    xh = np.asarray(d.variables["xh"][:], float)
    yh = np.asarray(d.variables["yh"][:], float)
    cref = np.asarray(d.variables["cref"][0], float)
    t_min = float(d.variables["time"][0]) / 60.0
    d.close()
    cell_km2 = abs(xh[1] - xh[0]) * abs(yh[1] - yh[0])
    mask = cref >= C.DBZ_CELL
    out = []
    if mask.any():
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        idx = np.arange(1, n + 1)
        sizes = ndimage.sum(mask, lab, index=idx) * cell_km2
        for c in idx[sizes >= C.DBZ_MIN_AREA_KM2]:
            jj, ii = np.nonzero(lab == c)
            out.append((float(xh[ii].mean()), float(yh[jj].mean()),
                        float(len(ii) * cell_km2)))
    out.sort(key=lambda r: -r[2])
    return t_min, out


# --- 2026-09-06: run list parameterised so the SAME instrument can read the 500 m
# members and their block reductions. Two deliberate constraints:
#   * the default list is the published five, and `--summary` is OFF by default, so
#     invoked bare this script's stdout is BYTE-IDENTICAL to the pre-edit version.
#     That identity is the neutrality gate (docs plan section 4.2c gate N1) -- an
#     instrument is not allowed to be "improved" on its way to new data.
#   * nothing about the measurement changes: same DBZ_CELL, same DBZ_MIN_AREA_KM2,
#     same 3x3 connectivity, same MATURE_MIN window. In particular the connectivity
#     structure stays in GRID CELLS, which is exactly why the matched-resolution
#     block reductions -- not the raw 500 m run -- are the primary basis: at 500 m a
#     3x3 reaches 1 km where at 1 km it reaches 2 km, so a finer grid can cut one
#     echo into two for no physical reason. Re-tuning connectivity per resolution
#     would hide that confound instead of controlling for it.
DEFAULT_NAMES = ("t5s_us15", "t5s_us20", "t5s_us25", "t5probe_sc", "t5probe_a")

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--names", nargs="+", default=list(DEFAULT_NAMES),
                help="run directories under --runs (default: the published five)")
ap.add_argument("--runs", default=RUNS)
ap.add_argument("--summary", action="store_true",
                help="append one machine-readable SUMMARY line per run (off by "
                     "default so bare output stays byte-identical to the 1 km record)")
args = ap.parse_args()
RUNS = args.runs

for name in args.names:
    d = os.path.join(RUNS, name)
    files = sorted(f for f in os.listdir(d)
                   if f.startswith("cm1out_0") and f.endswith(".nc"))
    print(f"\n=== {name} ===")
    print(f"  {'t_min':>6} {'n':>2}  {'sep_km':>7} {'dx_km':>7} {'dy_km':>7}   "
          f"largest two centroids (x,y) km")
    seps, dxs, dys, ts = [], [], [], []
    for f in files:
        t, comps = echo_components(os.path.join(d, f))
        if t < C.MATURE_MIN:
            continue
        if len(comps) >= 2:
            (x1, y1, a1), (x2, y2, a2) = comps[0], comps[1]
            dx, dy = x2 - x1, y2 - y1
            sep = float(np.hypot(dx, dy))
            seps.append(sep); dxs.append(dx); dys.append(dy); ts.append(t)
            print(f"  {t:6.0f} {len(comps):2d}  {sep:7.2f} {dx:7.2f} {dy:7.2f}   "
                  f"({x1:7.1f},{y1:7.1f}) a={a1:6.0f} | ({x2:7.1f},{y2:7.1f}) a={a2:5.0f}")
        else:
            print(f"  {t:6.0f} {len(comps):2d}       -       -       -   "
                  + ("single component" if comps else "no echo"))
    slope = float("nan")
    if len(seps) >= 3:
        sl = np.polyfit(np.array(ts) * 60.0, np.array(seps) * 1000.0, 1)[0]
        slope = float(sl)
        print(f"  --> {len(seps)} two-component frames; separation "
              f"{min(seps):.1f}-{max(seps):.1f} km, trend {sl:+.2f} m/s")
        print(f"      |dx| mean {np.mean(np.abs(dxs)):.1f} km, "
              f"|dy| mean {np.mean(np.abs(dys)):.1f} km  -> axis mostly "
              + ("ACROSS-shear (y, split-like)" if np.mean(np.abs(dys)) > np.mean(np.abs(dxs))
                 else "ALONG-shear (x)"))
    else:
        print(f"  --> only {len(seps)} two-component mature frames")
    if args.summary:
        # `t_last3` is the count of two-component frames in the final three output
        # frames. It exists because us15's ONLY 1 km two-component frame is the LAST
        # frame -- a boundary-adjacent datum -- and section 4.2c fixes in advance how a
        # late-window-only signal scores, rather than deciding once the number is seen.
        late = sum(1 for t in ts if t >= 105.0)
        print(f"  SUMMARY {name} n2={len(seps)} trend_ms={slope:.3f} "
              f"absdx_km={(np.mean(np.abs(dxs)) if dxs else float('nan')):.2f} "
              f"absdy_km={(np.mean(np.abs(dys)) if dys else float('nan')):.2f} "
              f"t_last3={late} mature_frames_total={len(ts)}")
