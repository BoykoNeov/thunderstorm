#!/usr/bin/env python3
"""Phase 0 WK supercell validation analysis.
Extracts updraft-max evolution, detects storm splitting (left/right movers),
and checks mid-level rotation (mesocyclone). Produces summary + figures.
"""
import netCDF4, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import ndimage

RUN = '/home/boiko/thunderstorm/runs/validation'
OUT = '/mnt/m/claud_projects/temp/phase0_validation'
import os; os.makedirs(OUT, exist_ok=True)

# --- 1. Updraft-max time series (from high-freq stats file) ---
st = netCDF4.Dataset(f'{RUN}/cm1out_stats.nc')
t_st = st.variables['time'][:] / 60.0            # minutes
wmax = st.variables['wmax'][:]
zwmax = st.variables['zwmax'][:]
ipk = int(np.argmax(wmax))
print("=== Updraft evolution (cm1out_stats.nc, 60 s cadence) ===")
print(f"Peak wmax = {wmax[ipk]:.1f} m/s at t = {t_st[ipk]:.1f} min, "
      f"height = {zwmax[ipk]:.0f} m AGL")
print(f"wmax at t=30/60/90/120 min: "
      + ", ".join(f"{np.interp(m, t_st, wmax):.1f}" for m in (30,60,90,120)) + " m/s")

# --- 2. Per-frame 3D analysis (split + rotation) ---
d = netCDF4.Dataset(f'{RUN}/cm1out.nc')
t = d.variables['time'][:] / 60.0
zh = d.variables['zh'][:]
xh = d.variables['xh'][:]; yh = d.variables['yh'][:]
kmid = int(np.argmin(np.abs(zh - 5.0)))
print(f"\n=== Per-frame analysis (cm1out.nc) — mid-level = {zh[kmid]:.2f} km ===")
print(f"{'t(min)':>7} {'wmax_col':>9} {'#cores':>6} {'sep(km)':>8} {'max|zvort|_mid':>14}")
split_t = None
frames = []
for it in range(len(t)):
    wcol = np.max(d.variables['winterp'][it, :, :, :], axis=0)   # column-max w
    mask = wcol > 5.0
    lab, n = ndimage.label(mask)
    cores = []
    for l in range(1, n + 1):
        cm = lab == l
        if cm.sum() >= 6 and wcol[cm].max() > 15.0:
            cy, cx = ndimage.center_of_mass(cm)
            cores.append((float(wcol[cm].max()),
                          float(yh[int(round(cy))]), float(xh[int(round(cx))])))
    cores.sort(reverse=True)
    sep = 0.0
    if len(cores) >= 2:
        (_, y1, x1), (_, y2, x2) = cores[0], cores[1]
        sep = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5   # xh/yh already in km
    zvmid = float(np.max(np.abs(d.variables['zvort'][it, kmid, :, :])))
    print(f"{t[it]:7.0f} {wcol.max():9.1f} {len(cores):6d} {sep:8.1f} {zvmid:14.4f}")
    if split_t is None and len(cores) >= 2 and sep > 10.0:
        split_t = t[it]
    frames.append((t[it], wcol))
print(f"\nStorm split (>=2 cores, sep>10 km) first at t = "
      + (f"{split_t:.0f} min" if split_t else "NOT detected"))

# --- 3. Figures ---
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(t_st, wmax, lw=1.5)
ax.axvline(split_t, color='r', ls='--', lw=1, label=f'split ~{split_t:.0f} min') if split_t else None
ax.set_xlabel('time (min)'); ax.set_ylabel('domain max w (m/s)')
ax.set_title('WK supercell — updraft max evolution (1 km, cm1r21.1)')
ax.grid(alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f'{OUT}/wmax_evolution.png', dpi=120)

ncol = min(len(frames), 9)
fig2, axs = plt.subplots(3, 3, figsize=(11, 10))
X, Y = np.meshgrid(xh, yh)   # already km
for i, axx in enumerate(axs.flat):
    if i >= ncol:
        axx.axis('off'); continue
    tt, wcol = frames[i]
    pc = axx.pcolormesh(X, Y, wcol, cmap='inferno', vmin=0, vmax=40, shading='auto')
    axx.set_title(f't = {tt:.0f} min', fontsize=9)
    axx.set_aspect('equal')
fig2.suptitle('Column-max updraft w (m/s) — left/right split visible as two cores')
fig2.colorbar(pc, ax=axs, shrink=0.6, label='w (m/s)')
fig2.savefig(f'{OUT}/updraft_frames.png', dpi=110)
print(f"\nFigures written to {OUT}/")
