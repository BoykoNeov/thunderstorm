"""Read one CM1 frame and build the rendered channel stack.

This is the ONLY place CM1 variable names are turned into render channels. The
bbox sweep and the exporter both go through `build_channels`, so the active
region they see can never diverge (a divergence would silently clip the box).
"""
import glob
import os

import numpy as np
from netCDF4 import Dataset

from . import contract


def frame_files(run_dir):
    """Sorted per-frame netCDF paths. Excludes cm1out_stats.nc (not a frame)."""
    return sorted(
        f for f in glob.glob(os.path.join(run_dir, "cm1out_*.nc"))
        if "stats" not in os.path.basename(f)
    )


def read_grid(path):
    """CM1 scalar-grid axes in METRES (the file stores km)."""
    with Dataset(path) as nc:
        return (np.asarray(nc.variables["xh"][:], dtype="f8") * 1000.0,
                np.asarray(nc.variables["yh"][:], dtype="f8") * 1000.0,
                np.asarray(nc.variables["zh"][:], dtype="f8") * 1000.0)


def build_channels(path):
    """dict channel -> float32 (nz, ny, nx) on the CM1 grid, plus storm time (s).

    Mixing-ratio channels are summed over their source fields (see
    contract.SOURCE_FIELDS); dbz is the CM1/NSSL diagnostic, passed through.

    Channel identity is FORMAT CONTRACT, not per-scenario -- this function needs no
    Scenario, which is exactly the split docs/phase2-plan-2026-07-20.md §4 draws.
    """
    out = {}
    with Dataset(path) as nc:
        t = float(nc.variables["time"][0])
        for ch in contract.CHANNELS:
            srcs = contract.SOURCE_FIELDS[ch]
            acc = None
            for s in srcs:
                v = np.asarray(nc.variables[s][0], dtype="f4")  # (z, y, x)
                acc = v if acc is None else acc + v
            out[ch] = acc
    return out, t


def active_mask(channels):
    """Union of per-channel active voxels at the LOCKED thresholds.

    This is exactly the set of voxels that will allocate in the VDB, so the
    padded box must contain it for every frame.
    """
    total = None
    for ch, arr in channels.items():
        m = arr > contract.THRESHOLDS[ch]
        total = m if total is None else (total | m)
    return total
