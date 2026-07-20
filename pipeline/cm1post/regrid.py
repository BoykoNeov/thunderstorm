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


def resample_dbz(sc, field, cm1_x, cm1_y, cm1_z, query):
    """Resample the dBZ diagnostic in LINEAR reflectivity factor Z, not in dB.

    dBZ = 10*log10(Z) is a LOGARITHMIC quantity, so averaging it is not averaging
    reflectivity. Between neighbours at 20 and 40 dBZ the physically correct
    midpoint is 10*log10((1e2 + 1e4)/2) = 37.03 dBZ -- dominated by the strong
    return, as a radar volume actually is. Interpolating in dB gives 30.0 dBZ, a
    7 dB (5x in Z) underestimate that systematically hollows out echo cores and
    smears their edges. Phase 1 shipped the dB version knowingly (carried item
    #3); it becomes load-bearing in Phase 2, where the radar view is a deliverable.

    Because 10*log10 is CONCAVE, this transform can only ever RAISE the result:
    new >= old everywhere, with equality exactly at grid points and in flat
    regions. That inequality is the T3 gate (pipeline/tests/test_regrid_dbz.py).

    Floors: CM1's dbz is floored at 0 dBZ (Z = 1 mm^6/m^3), so fill_value=1.0 in
    Z-space is the same "no echo" that the generic resampler's fill_value=0.0
    means in dB -- and it keeps log10 off zero. The output is clipped at 0 dBZ to
    match `resample`, so the ONLY semantic change here is the interpolation space.
    """
    z_lin = np.power(10.0, field.astype("f8") / 10.0)
    interp = RegularGridInterpolator(
        (cm1_z, cm1_y, cm1_x), z_lin,
        method="linear", bounds_error=False, fill_value=1.0,
    )
    z_out = interp(query).reshape(sc.nz, sc.ny, sc.nx)
    np.clip(z_out, 1.0e-12, None, out=z_out)  # guard: log10 must not see 0
    out = 10.0 * np.log10(z_out)
    np.clip(out, 0.0, None, out=out)
    return np.ascontiguousarray(out, dtype="<f4")


def build_query_2d(sc):
    """Precompute the (N,2) HORIZONTAL query points -- identical for every frame.

    The 2D counterpart of `build_query` for plan products (contract.WEB_PLAN_FIELDS).
    No z clamp exists here because there is no z: a plan field has already been
    collapsed over the column by CM1.
    """
    xs, ys, _ = export_axes(sc)
    # Index order must match the field array's (y, x).
    Y, X = np.meshgrid(ys, xs, indexing="ij")
    return np.stack([Y.ravel(), X.ravel()], axis=-1)


def resample_dbz_2d(sc, field, cm1_x, cm1_y, query2d):
    """Resample a 2D dBZ PLAN field (composite reflectivity) in LINEAR Z.

    Deliberately a near-duplicate of `resample_dbz` rather than a shared core that
    both call. The dimensionality differs but the assumption -- dBZ is logarithmic
    and must be interpolated in Z = 10^(dBZ/10) -- is identical, and everything in
    the sibling's docstring about WHY applies verbatim. It is written out again
    because `resample_dbz` sits under a passing gate (test_regrid_dbz.py) that was
    the entire point of T3: refactoring validated code to share a core with new,
    ungated code puts the old gate's subject at risk to save nine lines. The
    codebase's taste is explicit entry points (`resample` / `resample_dbz` /
    `resample_signed`) precisely so a caller cannot land on the wrong assumption by
    default.

    The linear-Z space is also what makes the T5 invariant true: because the
    horizontal interpolation weights are shared across all z-levels and convex,
        max_z interp_xy(Z)  >=  interp_xy(max_z Z)  is FALSE,
        interp_xy(max_z Z)  >=  max_z interp_xy(Z)  is TRUE,
    i.e. resampled cref (max-then-interp) is >= the column max of the resampled 3D
    dbz (interp-then-max), never the reverse. That inequality holds ONLY in linear Z,
    so the gate that checks it doubles as a check that this function was used and
    not a dB interpolation (pipeline/tests/test_regrid_cref.py).
    """
    z_lin = np.power(10.0, field.astype("f8") / 10.0)
    interp = RegularGridInterpolator(
        (cm1_y, cm1_x), z_lin,
        method="linear", bounds_error=False, fill_value=1.0,  # 1.0 = 0 dBZ = no echo
    )
    z_out = interp(query2d).reshape(sc.ny, sc.nx)
    np.clip(z_out, 1.0e-12, None, out=z_out)  # guard: log10 must not see 0
    out = 10.0 * np.log10(z_out)
    np.clip(out, 0.0, None, out=out)
    return np.ascontiguousarray(out, dtype="<f4")


def resample_signed(sc, field, cm1_x, cm1_y, cm1_z, query):
    """Trilinear-resample a SIGNED field (vertical velocity w) onto the export box.

    A separate function from `resample` for one blunt reason: `resample` ends with
    `np.clip(out, 0.0, None)`. That clamp is correct there -- mixing ratios and dBZ
    are non-negative by definition and it guards against fill-value edges -- but on
    w it would silently DELETE EVERY DOWNDRAFT, zeroing the entire negative half of
    the field. The storm's downdrafts and cold pool are the physically interesting
    half; losing them would not crash anything, it would just quietly render a storm
    that only ever goes up. The same reasoning as T3's `resample_dbz`: the shared
    resampler encodes an assumption (non-negativity there, linearity here) that one
    field violates, so the field gets its own entry point rather than a flag that a
    future caller can forget to pass.

    Interpolation is LINEAR and in the field's own units -- unlike dBZ, w is already
    a linear physical quantity, so there is no transform to interpolate through.
    Linear also cannot overshoot, so a resampled w never exceeds the largest
    contributing w; the recorded wmin/wmax stay valid bounds after resampling.

    fill_value=0.0 is physical here rather than merely convenient: outside the CM1
    domain there is no vertical motion.
    """
    interp = RegularGridInterpolator(
        (cm1_z, cm1_y, cm1_x), field.astype("f8"),
        method="linear", bounds_error=False, fill_value=0.0,
    )
    out = interp(query).reshape(sc.nz, sc.ny, sc.nx)
    # Deliberately NO clip -- see above.
    return np.ascontiguousarray(out, dtype="<f4")


def resample(sc, field, cm1_x, cm1_y, cm1_z, query):
    """Trilinear-resample one (nz,ny,nx) CM1 field onto the export box.

    NON-NEGATIVE linear quantities only -- the mixing ratios. The dBZ diagnostic is
    logarithmic and must go through `resample_dbz`; interpolating it here would
    average dB. Signed fields (w) must go through `resample_signed`; the clip below
    would erase their negative half.
    """
    interp = RegularGridInterpolator(
        (cm1_z, cm1_y, cm1_x), field.astype("f8"),
        method="linear", bounds_error=False, fill_value=0.0,
    )
    out = interp(query).reshape(sc.nz, sc.ny, sc.nx)
    # Guard: linear cannot overshoot, but a fill_value edge or a negative in the
    # source would propagate. Mixing ratios and dBZ are both >= 0 by definition.
    np.clip(out, 0.0, None, out=out)
    return np.ascontiguousarray(out, dtype="<f4")
