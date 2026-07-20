"""Resample CM1 fields onto the fixed export box.

This run is FLAT (no terrain), so there is no terrain-following surface to undo:
CM1's zh levels are verified uniform (stretch_z=0 -> 500 m exactly), making this a
plain regular-grid -> regular-grid resample. Terrain scenarios (Phase 3) will need
a real terrain-to-Cartesian step here; this module is where it lands.

Interpolation is LINEAR, deliberately. Cubic (e.g. scipy.ndimage.map_coordinates'
default order=3) overshoots at sharp echo edges and manufactures NEGATIVE mixing
ratios -- spurious water that no simulation produced. Linear cannot overshoot, and
we clamp at 0 anyway as a belt-and-braces guard.
"""
import numpy as np
from scipy.interpolate import RegularGridInterpolator


def export_axes(sc):
    """Voxel-centre coordinates (metres, CM1 world) of the export grid."""
    ox, oy, oz = sc.origin_m
    xs = ox + np.arange(sc.nx) * sc.export_voxel_m
    ys = oy + np.arange(sc.ny) * sc.export_voxel_m
    zs = oz + np.arange(sc.nz) * sc.export_voxel_m
    return xs, ys, zs


def build_query(sc, cm1_x, cm1_y, cm1_z):
    """Precompute the (N,3) query points once -- identical for every frame.

    Query z is CLAMPED to the lowest CM1 scalar level rather than left to
    fill_value=0: the export box starts at 125 m but CM1's first scalar level is
    at 250 m, and zeroing that slab would carve a hollow layer under the storm.
    Clamping extends the lowest level down to the surface, which is what a
    below-first-level sample physically is.
    """
    xs, ys, zs = export_axes(sc)
    zq = np.clip(zs, cm1_z[0], cm1_z[-1])
    # Index order must match the field array's (z, y, x).
    Z, Y, X = np.meshgrid(zq, ys, xs, indexing="ij")
    return np.stack([Z.ravel(), Y.ravel(), X.ravel()], axis=-1)


def resample(sc, field, cm1_x, cm1_y, cm1_z, query):
    """Trilinear-resample one (nz,ny,nx) CM1 field onto the export box."""
    interp = RegularGridInterpolator(
        (cm1_z, cm1_y, cm1_x), field.astype("f8"),
        method="linear", bounds_error=False, fill_value=0.0,
    )
    out = interp(query).reshape(sc.nz, sc.ny, sc.nx)
    # Guard: linear cannot overshoot, but a fill_value edge or a negative in the
    # source would propagate. Mixing ratios and dBZ are both >= 0 by definition.
    np.clip(out, 0.0, None, out=out)
    return np.ascontiguousarray(out, dtype="<f4")
