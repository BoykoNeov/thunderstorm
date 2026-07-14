#!/usr/bin/env python3
"""Signed vertical vorticity at the two updraft cores -> counter-rotating pair?"""
import netCDF4, numpy as np
from scipy import ndimage

d = netCDF4.Dataset('/home/boiko/thunderstorm/runs/validation/cm1out.nc')
t = d.variables['time'][:] / 60.0
zh = d.variables['zh'][:]; xh = d.variables['xh'][:]; yh = d.variables['yh'][:]
kmid = int(np.argmin(np.abs(zh - 5.0)))
print(f"mid-level = {zh[kmid]:.2f} km")
print(f"{'t(min)':>6} | core A (y,x km, signed zvort) | core B (y,x km, signed zvort)")
for it in range(len(t)):
    if t[it] < 70:
        continue
    wcol = np.max(d.variables['winterp'][it, :, :, :], axis=0)
    zv = d.variables['zvort'][it, kmid, :, :]
    lab, n = ndimage.label(wcol > 5.0)
    cores = []
    for l in range(1, n + 1):
        cm = lab == l
        if cm.sum() >= 6 and wcol[cm].max() > 15.0:
            cy, cx = ndimage.center_of_mass(cm)
            iy, ix = int(round(cy)), int(round(cx))
            # strongest rotation feature in a +/-8 km (8-cell) box around the core
            r = 8
            y0, y1b = max(0, iy - r), min(zv.shape[0], iy + r + 1)
            x0, x1b = max(0, ix - r), min(zv.shape[1], ix + r + 1)
            box = zv[y0:y1b, x0:x1b]
            zpk = float(box.flat[np.argmax(np.abs(box))])  # signed, max |zvort|
            cores.append((float(wcol[cm].max()), yh[iy], xh[ix], zpk))
    cores.sort(reverse=True)
    if len(cores) >= 2:
        (_, ya, xa, za), (_, yb, xb, zb) = cores[0], cores[1]
        print(f"{t[it]:6.0f} | ({ya:+5.0f},{xa:+5.0f})  zv={za:+.4f}    | "
              f"({yb:+5.0f},{xb:+5.0f})  zv={zb:+.4f}   "
              f"-> {'OPPOSITE (counter-rotating pair)' if za*zb < 0 else 'same sign'}")
    elif cores:
        (_, ya, xa, za) = cores[0]
        print(f"{t[it]:6.0f} | ({ya:+5.0f},{xa:+5.0f})  zv={za:+.4f}    | (single core)")
