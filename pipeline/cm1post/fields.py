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


def read_extra(path, name):
    """Read one WEB_EXTRA_FIELDS field -> float32 (nz, ny, nx).

    The second export path (Phase 2 T4, plan §7): CM1 vars that ship in the web
    rendition WITHOUT entering the frozen SVT channel map. Unlike `build_channels`
    these are passed through unsummed and unmodified -- `w` is a prognostic field,
    not a composite of source fields.
    """
    var = contract.WEB_EXTRA_FIELDS[name]["cm1_var"]
    with Dataset(path) as nc:
        return np.asarray(nc.variables[var][0], dtype="f4")  # (z, y, x)


def read_plan(path, name):
    """Read one WEB_PLAN_FIELDS field -> float32 (ny, nx).

    The 2D sibling of `read_extra` (Phase 2 T5). Passed through unmodified: `cref`
    is CM1's own composite-reflectivity diagnostic, and recomputing it here from the
    cropped `dbz` would quietly redefine a standard radar product.

    Note this field takes NO part in `active_mask` and therefore no part in sizing
    the bbox. It cannot: a plan field has no z, so it cannot mark a voxel active.
    It does not need to either -- cref > t at (x,y) holds exactly when some dbz > t
    exists in that column, so the box sized on the 3D dbz channel already contains
    every above-threshold cref cell by construction.
    """
    var = contract.WEB_PLAN_FIELDS[name]["cm1_var"]
    with Dataset(path) as nc:
        return np.asarray(nc.variables[var][0], dtype="f4")  # (y, x)


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
