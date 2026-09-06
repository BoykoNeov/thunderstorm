"""Does block-reduction MERGE components, and if so by what mechanism?

Plan section 4.2c made the block reductions the PRIMARY basis, on the reasoning that
matched resolution controls the grid-cell connectivity reach. The 500 m read shows
something that reasoning did not anticipate: `t5s_us20_500m` resolves a mirrored
two-component pair at t = 90 min (287 km^2 each, 15.4 km apart) and BOTH reductions of
it report a single component at that time.

Two mechanisms could do that, and they have opposite meanings:
  (a) MERGE  -- reduction raises the dBZ in the gap between the movers above the 40 dBZ
      threshold, connecting them. Block-mean is computed in LINEAR Z, which is
      peak-dominated, so a 2x2 block straddling a 45/35 dBZ boundary reads ~42.4 dBZ,
      not 40. If this is it, the reduction is BIASED TOWARD "no split" for a
      connected-component statistic, and 4.2c's primary basis is the wrong instrument
      for THIS test (it remains right for the field statistics E and R).
  (b) SHRINK -- reduction lowers peaks so each component falls under the 10 km^2 area
      floor and is rejected. Then the count drop is a sensitivity loss, not a merge.

Discriminator: total >=40 dBZ AREA. A merge conserves or grows it; a shrink destroys it.
"""
import netCDF4, numpy as np, os
from scipy import ndimage

R = "/home/boiko/thunderstorm/runs"
DBZ, FLOOR = 40.0, 10.0


def comps(run, t_want):
    fs = sorted(f for f in os.listdir(os.path.join(R, run))
                if f.startswith("cm1out_0") and f.endswith(".nc"))
    for f in fs:
        d = netCDF4.Dataset(os.path.join(R, run, f))
        t = float(d.variables["time"][0]) / 60.0
        if abs(t - t_want) > 0.6:
            d.close(); continue
        xh = np.asarray(d.variables["xh"][:], float)
        yh = np.asarray(d.variables["yh"][:], float)
        cref = np.asarray(d.variables["cref"][0], float)
        d.close()
        cell = abs(xh[1] - xh[0]) * abs(yh[1] - yh[0])
        m = cref >= DBZ
        lab, n = ndimage.label(m, structure=np.ones((3, 3)))
        keep, tot = [], 0.0
        for c in range(1, n + 1):
            a = float((lab == c).sum()) * cell
            if a >= FLOOR:
                jj, ii = np.nonzero(lab == c)
                keep.append((a, float(xh[ii].mean()), float(yh[jj].mean())))
                tot += a
        keep.sort(key=lambda r: -r[0])
        return dict(run=run, t=t, dx_km=abs(xh[1] - xh[0]), n_kept=len(keep),
                    area_kept=tot, area_all=float(m.sum()) * cell,
                    peak=float(cref.max()), comps=keep, cref=cref, xh=xh, yh=yh)
    return None


print("t = 90 min, the frame where the raw 500 m run splits and both reductions do not\n")
print(f"  {'run':38s}{'dx':>5}{'n':>3}{'area>=40 (km2)':>16}{'peak dBZ':>10}   components (area @ x,y)")
rows = {}
for run in ("t5s_us20_500m", "t5s_us20_500m_coarse_mean", "t5s_us20_500m_coarse_extremum"):
    r = comps(run, 90.0)
    rows[run] = r
    cs = " | ".join(f"{a:.0f} @ ({x:.1f},{y:.1f})" for a, x, y in r["comps"][:3])
    print(f"  {run:38s}{r['dx_km']*1000:5.0f}{r['n_kept']:3d}{r['area_kept']:16.0f}"
          f"{r['peak']:10.1f}   {cs}")

raw = rows["t5s_us20_500m"]
print("\n  total >=40 dBZ area INCLUDING sub-floor specks (the merge/shrink discriminator):")
for run, r in rows.items():
    print(f"    {run:38s} {r['area_all']:8.0f} km2   "
          f"({r['area_all'] / raw['area_all'] * 100:5.1f} % of raw 500 m)")

# The gap itself: dBZ sampled along y at the x of the raw pair, between the two centroids.
print("\n  dBZ along the line joining the two raw movers (x = -8.6 km), y = -8..+8 km:")
for run, r in rows.items():
    ix = int(np.argmin(np.abs(r["xh"] - (-8.6))))
    sel = (r["yh"] >= -8.0) & (r["yh"] <= 8.0)
    prof = r["cref"][sel, ix]
    ys = r["yh"][sel]
    below = int((prof < DBZ).sum())
    print(f"    {run:38s} min {prof.min():5.1f}  max {prof.max():5.1f}  "
          f"cells under 40 dBZ: {below:3d}/{len(prof):3d}"
          + ("   <- gap OPEN (separates)" if below else "   <- gap CLOSED (connects)"))
