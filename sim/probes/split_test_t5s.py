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


for name in ("t5s_us15", "t5s_us20", "t5s_us25", "t5probe_sc", "t5probe_a"):
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
    if len(seps) >= 3:
        sl = np.polyfit(np.array(ts) * 60.0, np.array(seps) * 1000.0, 1)[0]
        print(f"  --> {len(seps)} two-component frames; separation "
              f"{min(seps):.1f}-{max(seps):.1f} km, trend {sl:+.2f} m/s")
        print(f"      |dx| mean {np.mean(np.abs(dxs)):.1f} km, "
              f"|dy| mean {np.mean(np.abs(dys)):.1f} km  -> axis mostly "
              + ("ACROSS-shear (y, split-like)" if np.mean(np.abs(dys)) > np.mean(np.abs(dxs))
                 else "ALONG-shear (x)"))
    else:
        print(f"  --> only {len(seps)} two-component mature frames")
