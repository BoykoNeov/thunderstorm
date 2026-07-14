#!/usr/bin/env python3
"""Domain-containment check for the flat/imove config.
Tracks the two dominant updraft cores (left/right movers) across the full 2 h
run and reports each core's distance to the nearest domain edge. Answers:
does the 120 km moving domain hold BOTH movers through the split, or does a
mover approach/exit the boundary (forcing a larger domain)?
"""
import netCDF4, numpy as np
from scipy import ndimage

RUN = '/home/boiko/thunderstorm/runs/validation'
d = netCDF4.Dataset(f'{RUN}/cm1out.nc')
t = d.variables['time'][:] / 60.0
xh = d.variables['xh'][:]; yh = d.variables['yh'][:]   # km, moving-frame
x0, x1 = float(xh.min()), float(xh.max())
y0, y1 = float(yh.min()), float(yh.max())
print(f"domain (moving frame): x[{x0:.1f},{x1:.1f}] y[{y0:.1f},{y1:.1f}] km "
      f"= {x1-x0:.0f} x {y1-y0:.0f} km")
print(f"{'t(min)':>7} {'#cores':>6} {'core1(x,y)':>16} {'edge1':>6} "
      f"{'core2(x,y)':>16} {'edge2':>6} {'sep':>6}")

def edge_dist(x, y):
    return min(x - x0, x1 - x, y - y0, y1 - y)

min_edge = 1e9; worst_t = None
for it in range(len(t)):
    wcol = np.max(d.variables['winterp'][it, :, :, :], axis=0)
    lab, n = ndimage.label(wcol > 5.0)
    cores = []
    for l in range(1, n + 1):
        cm = lab == l
        if cm.sum() >= 6 and wcol[cm].max() > 15.0:
            cy, cx = ndimage.center_of_mass(cm)
            cores.append((float(wcol[cm].max()),
                          float(xh[int(round(cx))]), float(yh[int(round(cy))])))
    cores.sort(reverse=True)
    def fmt(c):
        return f"({c[1]:6.1f},{c[2]:6.1f})", edge_dist(c[1], c[2])
    if len(cores) >= 2:
        s1, e1 = fmt(cores[0]); s2, e2 = fmt(cores[1])
        sep = ((cores[0][1]-cores[1][1])**2 + (cores[0][2]-cores[1][2])**2) ** 0.5
        me = min(e1, e2)
        if me < min_edge and t[it] > 20:   # ignore initial bubble
            min_edge = me; worst_t = t[it]
        print(f"{t[it]:7.0f} {len(cores):6d} {s1:>16} {e1:6.1f} {s2:>16} {e2:6.1f} {sep:6.1f}")
    elif len(cores) == 1:
        s1, e1 = fmt(cores[0])
        print(f"{t[it]:7.0f} {len(cores):6d} {s1:>16} {e1:6.1f} {'':>16} {'':>6} {'':>6}")
    else:
        print(f"{t[it]:7.0f} {0:6d}")
print(f"\nClosest either mover came to an edge (after t>20 min): "
      f"{min_edge:.1f} km at t={worst_t:.0f} min")
print("Rule of thumb: need >~10 km clearance (storm core half-width) to keep "
      "a mover fully in-domain.")
