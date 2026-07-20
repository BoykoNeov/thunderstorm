#!/usr/bin/env python3
"""Plan-field gates for the composite-reflectivity export (Phase 2 T5).

    python3 pipeline/tests/test_regrid_cref.py

Same gate shape as T3 and T4: T5 adds output by design, so byte-identity is
unavailable and every gate has to be POSITIVE -- state what correct looks like and
fail when the transform is dropped.

T5's central invariant is the ORDERING one:

    resampled cref   =  interp_xy( max_z Z )     "max then interpolate"
    colmax of vol    =  max_z( interp_xy Z )     "interpolate then max"
    ==> cref >= colmax, NEVER the reverse.

It holds because the horizontal interpolation weights are shared across every z
level and are convex (non-negative, summing to 1), so the interpolated column
maximum is at least the maximum of the interpolated columns. Crucially it holds in
LINEAR Z, which is what makes `gate_cref_dominates_colmax` do double duty: it is
simultaneously the physical invariant and a detector for cref having been sent
through a dB interpolation instead of `regrid.resample_dbz_2d`.

The other load-bearing fact, measured rather than assumed (probe over all 301
frames of the Phase 1 run): CM1's `cref` is BITWISE identical to `dbz.max(axis=0)`,
worst |difference| = 0.000e+00, both sequence maxima 72.213715 dBZ. That identity
is what licenses reusing the dbz vmax, so one byte means one dBZ in both layers.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import contract, regrid, webvol  # noqa: E402

_results = []
THR = contract.THRESHOLDS["dbz"]


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


class FakeScenario:
    """Minimal stand-in -- regrid only reads nx/ny/nz off the scenario."""

    def __init__(self, nx, ny, nz):
        self.nx, self.ny, self.nz = nx, ny, nz


def dbz_to_z(d):
    return np.power(10.0, np.asarray(d, dtype="f8") / 10.0)


def z_to_dbz(z):
    return 10.0 * np.log10(z)


# --- the linear-Z gate (T3's argument, one rank down) ------------------------

def gate_midpoint_is_linear_z():
    """A 20/40 dBZ pair interpolates to 37.03 dBZ, not 30.

    Hand-computed: 10*log10((1e2 + 1e4)/2) = 37.0328... The gate pins the transform
    from BOTH sides rather than merely detecting its absence: it fails if the
    Z-transform is DROPPED (30.0, the dB average) and it fails if the return leg is
    forgotten (5050.0, a raw Z left in a field labelled dBZ -- the realistic
    half-applied mistake, and one an encoder that only clips at vmax would pass
    straight through).
    """
    sc = FakeScenario(1, 1, 1)
    ax = np.array([0.0, 1000.0])
    field = np.array([[20.0, 20.0], [40.0, 40.0]], dtype="f4")  # varies along y
    q = np.array([[500.0, 500.0]])  # (y, x)
    out = float(regrid.resample_dbz_2d(sc, field, ax, ax, q).ravel()[0])

    want = z_to_dbz((dbz_to_z(20.0) + dbz_to_z(40.0)) / 2.0)   # 37.0329
    in_db = 30.0
    no_return_leg = (dbz_to_z(20.0) + dbz_to_z(40.0)) / 2.0    # 5050.0, still in Z
    ok = (abs(out - want) < 1e-3 and abs(out - in_db) > 1.0
          and abs(out - no_return_leg) > 1.0)
    return ok, (f"(20, 40) dBZ at the midpoint -> {out:.4f}, want {want:.4f}; "
                f"dB-space would give {in_db:.1f}, and skipping the return leg "
                f"{no_return_leg:.1f}")


def gate_jensen_inequality():
    """Linear-Z resampling can only RAISE dBZ relative to dB-space resampling.

    10*log10 is concave, so the Z-space mean dominates the dB mean everywhere, with
    equality exactly at grid points and in flat regions. This is T3's whole-field
    replacement for byte-identity, restated for the 2D path.
    """
    rng = np.random.default_rng(5)
    sc = FakeScenario(23, 19, 1)
    ax_x = np.linspace(0.0, 8000.0, 9)
    ax_y = np.linspace(0.0, 8000.0, 11)
    field = rng.uniform(0.0, 70.0, size=(11, 9)).astype("f4")

    yq = np.linspace(100.0, 7900.0, sc.ny)
    xq = np.linspace(100.0, 7900.0, sc.nx)
    Y, X = np.meshgrid(yq, xq, indexing="ij")
    q = np.stack([Y.ravel(), X.ravel()], axis=-1)

    new = regrid.resample_dbz_2d(sc, field, ax_x, ax_y, q)

    # The dB-space resample this replaces (what a naive 2D path would have done).
    from scipy.interpolate import RegularGridInterpolator
    old = RegularGridInterpolator((ax_y, ax_x), field.astype("f8"), method="linear",
                                  bounds_error=False, fill_value=0.0)(q)
    old = np.clip(old.reshape(sc.ny, sc.nx), 0.0, None)

    diff = new - old
    ok = bool((diff >= -1e-4).all()) and float(diff.max()) > 1.0
    return ok, (f"new >= old everywhere (min diff {diff.min():+.2e} dB), and the "
                f"correction is real: peak {diff.max():+.3f} dB, mean "
                f"{diff.mean():+.3f} dB over {diff.size} cells")


def gate_no_inflation():
    """An interpolated Z never exceeds the largest contributing Z.

    This is why the borrowed dbz `vmax` stays a valid encoding bound after
    resampling, and why T5 -- like T3 -- cannot grow the bounding box.
    """
    rng = np.random.default_rng(6)
    sc = FakeScenario(31, 29, 1)
    ax_x = np.linspace(0.0, 8000.0, 9)
    ax_y = np.linspace(0.0, 8000.0, 9)
    field = rng.uniform(0.0, 65.0, size=(9, 9)).astype("f4")

    yq = np.linspace(50.0, 7950.0, sc.ny)
    xq = np.linspace(50.0, 7950.0, sc.nx)
    Y, X = np.meshgrid(yq, xq, indexing="ij")
    q = np.stack([Y.ravel(), X.ravel()], axis=-1)

    out = regrid.resample_dbz_2d(sc, field, ax_x, ax_y, q)
    ok = float(out.max()) <= float(field.max()) + 1e-4
    return ok, (f"resampled max {out.max():.4f} <= source max {field.max():.4f} dBZ "
                "-- the borrowed vmax remains a bound")


# --- the ordering invariant -------------------------------------------------

def gate_cref_dominates_colmax():
    """max-then-interp >= interp-then-max, on a field where they genuinely differ.

    The columns are built so the argmax LEVEL varies horizontally: at x=0 the peak
    sits on the upper level, at x=1 on the lower one. Interpolating each level and
    then taking the column max therefore samples a blend of a peak and a trough,
    while the true composite reflectivity blends the two peaks. A viewer using the
    3D layer's column max as if it were cref would UNDER-report the echo.
    """
    ax = np.array([0.0, 1000.0])
    q3 = np.array([[500.0, 500.0, 500.0]])       # (z, y, x)
    q2 = np.array([[500.0, 500.0]])              # (y, x)
    sc = FakeScenario(1, 1, 1)

    dbz = np.zeros((2, 2, 2), dtype="f4")
    dbz[1, :, 0] = 60.0   # upper level peaks at x=0
    dbz[0, :, 0] = 5.0
    dbz[0, :, 1] = 55.0   # lower level peaks at x=1
    dbz[1, :, 1] = 5.0

    cref_src = dbz.max(axis=0)                                    # what CM1 gives us
    cref = float(regrid.resample_dbz_2d(sc, cref_src, ax, ax, q2).ravel()[0])
    vol = regrid.resample_dbz(sc, dbz, ax, ax, ax, q3)
    colmax = float(vol.max(axis=0).ravel()[0])

    ok = cref >= colmax - 1e-4 and (cref - colmax) > 0.5
    return ok, (f"cref {cref:.4f} >= colmax(resampled dbz) {colmax:.4f} dBZ "
                f"(gap {cref-colmax:+.4f}) -- the ordering is not a tie here, so the "
                "gate has something to detect")


def gate_ordering_holds_on_random_fields():
    """The invariant is structural, not a property of one hand-built example."""
    rng = np.random.default_rng(7)
    sc = FakeScenario(13, 11, 6)
    ax_x = np.linspace(0.0, 6000.0, 7)
    ax_y = np.linspace(0.0, 6000.0, 8)
    ax_z = np.linspace(0.0, 6000.0, 6)
    dbz = rng.uniform(0.0, 70.0, size=(6, 8, 7)).astype("f4")

    zq = np.linspace(100.0, 5900.0, sc.nz)
    yq = np.linspace(100.0, 5900.0, sc.ny)
    xq = np.linspace(100.0, 5900.0, sc.nx)
    Z, Y, X = np.meshgrid(zq, yq, xq, indexing="ij")
    q3 = np.stack([Z.ravel(), Y.ravel(), X.ravel()], axis=-1)
    Y2, X2 = np.meshgrid(yq, xq, indexing="ij")
    q2 = np.stack([Y2.ravel(), X2.ravel()], axis=-1)

    cref = regrid.resample_dbz_2d(sc, dbz.max(axis=0), ax_x, ax_y, q2)
    colmax = regrid.resample_dbz(sc, dbz, ax_x, ax_y, ax_z, q3).max(axis=0)

    d = cref - colmax
    ok = bool((d >= -1e-3).all())
    return ok, (f"cref >= colmax at all {d.size} cells (worst {d.min():+.2e} dB, "
                f"largest genuine gap {d.max():+.3f} dB)")


# --- encoding gates ---------------------------------------------------------

def gate_shares_the_dbz_scale():
    """One byte means one dBZ in the plan view and the 3D layer.

    Deliberately NOT "encode twice and compare" -- that is a tautology that can only
    ever pass. The real claim is about the WIRING: the numbers the manifest publishes
    for the plan field must be the SAME numbers it publishes for dbz, because a
    reader builds its colour ramp from the manifest, not from this test. So the gate
    goes through `webvol.build_manifest` and compares what actually ships.

    If they ever diverge, the shared NWS colormap silently lies in one of the views:
    the same colour would mean two different dBZ.
    """
    vmax = 72.213715  # the measured sequence max (cref and dbz agree by identity)
    qmax = {c: 1.0e-2 for c in contract.CHANNELS}
    qmax["dbz"] = vmax
    doc = webvol.build_manifest(_FakeScenarioForManifest(), [], qmax,
                                observed={"w": {"min": -1.0, "max": 1.0},
                                          "cref": {"min": 0.0, "max": vmax}})

    plan = doc["plan_fields"]["cref"]
    dbz = doc["dbz"]
    same = (plan["threshold"] == dbz["threshold"] and plan["vmax"] == dbz["vmax"]
            and plan["encoding"] == dbz["encoding"])

    # And the published numbers must be the ones the encoder was actually given.
    vals = np.linspace(0.0, vmax, 501).astype("f4")
    codes = webvol.encode_linear_u8(vals, plan["threshold"], plan["vmax"])
    ok = same and int(codes[0]) == 0 and int(codes[-1]) == 255
    return ok, (f"manifest publishes threshold {plan['threshold']} / vmax "
                f"{plan['vmax']:.6f} / {plan['encoding']} for BOTH cref and dbz; "
                f"encoding by those published values maps 0 dBZ -> {int(codes[0])} "
                f"and vmax -> {int(codes[-1])}")


class _FakeScenarioForManifest:
    """Just enough Scenario for build_manifest's grid block."""
    name, run_dir = "gate", "/dev/null"
    nx, ny, nz = 8, 8, 4
    export_voxel_m = 250.0
    origin_m = (0.0, 0.0, 0.0)


def gate_below_threshold_is_zero():
    """Sub-threshold echo encodes to 0 -- the 'no echo' sentinel, not weak echo.

    A plan view is read as a map of where the storm IS, so the code that means
    'nothing here' has to be unambiguous.
    """
    vals = np.array([0.0, THR - 0.1, THR, THR + 0.1, 60.0], dtype="f4")
    v = webvol.encode_linear_u8(vals, THR, 72.0)
    ok = list(v[:3]) == [0, 0, 0] and v[3] > 0 and v[4] > v[3]
    return ok, f"{list(vals)} dBZ -> codes {list(int(x) for x in v)}"


# --- negative controls ------------------------------------------------------

def negative_controls():
    """Each gate must reject an implementation T5 actually considered."""
    print("\nnegative controls -- the gates must reject the rejected designs")

    def control(name, ok_if_rejected, detail):
        _results.append(ok_if_rejected)
        print(f"  {'PASS' if ok_if_rejected else 'FAIL'}  fires on: {name}\n"
              f"          {detail}")

    sc = FakeScenario(1, 1, 1)
    ax = np.array([0.0, 1000.0])
    q2 = np.array([[500.0, 500.0]])

    # 1. Resampling cref in dB -- the T3 mistake, repeated one rank down.
    from scipy.interpolate import RegularGridInterpolator
    field = np.array([[20.0, 20.0], [40.0, 40.0]], dtype="f4")
    in_db = float(RegularGridInterpolator((ax, ax), field.astype("f8"),
                                          method="linear")(q2)[0])
    right = float(regrid.resample_dbz_2d(sc, field, ax, ax, q2).ravel()[0])
    control("interpolating the plan field in dB instead of linear Z",
            abs(in_db - right) > 1.0,
            f"dB-space gives {in_db:.2f} dBZ where linear Z gives {right:.2f} -- a "
            f"{right-in_db:.2f} dB hollowing-out of exactly the echo cores a radar "
            "view exists to show")

    # 2. Using colmax of the exported volume AS cref -- the rejected option (b).
    #    It is not merely different, it is biased LOW, and always in the same
    #    direction, so it would systematically under-report echo intensity.
    dbz = np.zeros((2, 2, 2), dtype="f4")
    dbz[1, :, 0] = 60.0
    dbz[0, :, 0] = 5.0
    dbz[0, :, 1] = 55.0
    dbz[1, :, 1] = 5.0
    q3 = np.array([[500.0, 500.0, 500.0]])
    cref = float(regrid.resample_dbz_2d(sc, dbz.max(axis=0), ax, ax, q2).ravel()[0])
    colmax = float(regrid.resample_dbz(sc, dbz, ax, ax, ax, q3).max(axis=0).ravel()[0])
    control("substituting colmax(exported volume) for CM1's cref",
            (cref - colmax) > 0.5,
            f"colmax gives {colmax:.2f} dBZ vs the true composite {cref:.2f} -- "
            f"{cref-colmax:.2f} dB low, and biased in one direction, because the "
            "argmax level varies horizontally")

    # 3. A separately fitted per-field vmax -- the pattern qmax uses for the mixing
    #    ratios, which is exactly wrong here: it would decouple the two dBZ views.
    a = webvol.encode_linear_u8(np.array([40.0], dtype="f4"), THR, 72.213715)
    b = webvol.encode_linear_u8(np.array([40.0], dtype="f4"), THR, 60.0)
    control("fitting the plan field its own vmax instead of sharing dbz's",
            int(a[0]) != int(b[0]),
            f"40 dBZ -> code {int(a[0])} on the shared scale but {int(b[0])} on a "
            "separately fitted one -- same dBZ, two colours, one colormap")

    # 4. Routing cref through the generic (non-log) resampler.
    generic = float(RegularGridInterpolator((ax, ax), field.astype("f8"),
                                            method="linear")(q2)[0])
    control("the generic resampler treats dBZ as if it were linear",
            abs(generic - right) > 1.0,
            f"{generic:.2f} vs {right:.2f} dBZ -- same failure as (1), stated at the "
            "call site a future caller is most likely to reach for")

    # 5. gate_shares_the_dbz_scale reads the manifest rather than comparing two
    #    identical calls, so it has to be shown it can actually FAIL. Break the
    #    contract wiring and confirm the published numbers diverge.
    vmax = 72.213715
    qmax = {c: 1.0e-2 for c in contract.CHANNELS}
    qmax["dbz"] = vmax
    obs = {"w": {"min": -1.0, "max": 1.0}, "cref": {"min": 0.0, "max": vmax}}
    spec = contract.WEB_PLAN_FIELDS["cref"]
    saved = spec["vmax_from"]
    try:
        spec["vmax_from"] = "cloud"          # borrow the WRONG channel's max
        broken = webvol.build_manifest(_FakeScenarioForManifest(), [], qmax,
                                       observed=obs)
    finally:
        spec["vmax_from"] = saved
    bad = broken["plan_fields"]["cref"]["vmax"]
    good = webvol.build_manifest(_FakeScenarioForManifest(), [], qmax,
                                 observed=obs)["plan_fields"]["cref"]["vmax"]
    control("the plan field wired to the wrong channel's vmax",
            bad != good and good == vmax,
            f"vmax_from='cloud' publishes {bad} instead of {good:.6f} -- the scale "
            "gate reads the manifest precisely so this is visible; restored to "
            f"'{saved}' afterwards")


def main():
    print("T5 plan-field gates -- regrid.resample_dbz_2d + shared dBZ encoding")
    print(f"  shared threshold {THR} dBZ; vmax borrowed from the dbz channel")
    print("  measured: CM1 cref == dbz.max(axis=0) BITWISE over all 301 frames\n")

    print("linear-Z resampling -- T3's argument, one rank down")
    check("a 20/40 dBZ pair lands on 37.03, not 30", gate_midpoint_is_linear_z)
    check("Jensen: linear-Z can only raise dBZ vs dB-space", gate_jensen_inequality)
    check("interpolation never inflates above the source max", gate_no_inflation)

    print("\nthe ordering invariant -- cref is max-then-interp")
    check("cref >= colmax(resampled volume) on a built case", gate_cref_dominates_colmax)
    check("...and on random fields, i.e. structurally", gate_ordering_holds_on_random_fields)

    print("\nencoding -- shared with the 3D dbz layer, deliberately")
    check("one byte means one dBZ in both views", gate_shares_the_dbz_scale)
    check("below-threshold encodes to the 0 'no echo' sentinel", gate_below_threshold_is_zero)

    negative_controls()

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
