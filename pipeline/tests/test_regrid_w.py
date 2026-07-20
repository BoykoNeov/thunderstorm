#!/usr/bin/env python3
"""Signed-field gates for the updraft export (Phase 2 T4).

    python3 pipeline/tests/test_regrid_w.py

T3 established the shape of these gates: when a change is SUPPOSED to alter output,
byte-identity is unavailable and the gate must be POSITIVE -- it has to state what
correct looks like and fail when the transform is dropped.

T4's failure mode is quieter than T3's. Routing `w` through the generic
`regrid.resample` does not crash, does not warn, and produces a perfectly plausible
volume: it just clips every downdraft to zero, rendering a storm whose air only ever
goes up. Nothing downstream would notice. So the load-bearing gate here is
`gate_negative_survives`: a purely-negative field must come back negative.

The encoding gates pin the other T4 decision -- code 128 decodes to EXACTLY zero, so
the updraft/downdraft boundary is exact rather than landing wherever an affine fit
happened to round it.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import contract, regrid, webvol  # noqa: E402

_results = []
SCALE = contract.W_ENCODE_SCALE_M_S


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


def tiny_grid():
    """A 2x2x2 CM1 cell with a query point at its exact centre."""
    ax = np.array([0.0, 1000.0])
    sc = FakeScenario(1, 1, 1)
    query = np.array([[500.0, 500.0, 500.0]])  # (z, y, x)
    return sc, ax, query


# --- the load-bearing gate --------------------------------------------------

def gate_negative_survives():
    """A purely-negative field must resample to negative values, not zeros.

    This is the anti-regression against `w` being routed through `regrid.resample`,
    whose clip at 0 would erase the entire downdraft half of the storm silently.
    """
    sc, ax, query = tiny_grid()
    field = np.full((2, 2, 2), -12.5, dtype="f4")
    out = regrid.resample_signed(sc, field, ax, ax, ax, query)
    ok = np.allclose(out, -12.5)

    # And demonstrate the failure it guards against, so the gate is not merely
    # asserting that today's code does what today's code does.
    clipped = regrid.resample(sc, field, ax, ax, ax, query)
    guarded = np.allclose(clipped, 0.0)
    return ok and guarded, (
        f"signed resample -> {out.ravel()[0]:+.3f} (correct); the generic resample "
        f"gives {clipped.ravel()[0]:+.3f} -- which is the bug this gate exists for")


def gate_mixed_sign_midpoint():
    """A +/- pair interpolates to its true linear midpoint, sign included."""
    sc, ax, query = tiny_grid()
    field = np.zeros((2, 2, 2), dtype="f4")
    field[0] = -20.0   # lower z plane
    field[1] = +40.0   # upper z plane
    out = float(regrid.resample_signed(sc, field, ax, ax, ax, query).ravel()[0])
    want = 10.0
    return abs(out - want) < 1e-4, (
        f"(-20, +40) at the midpoint -> {out:+.4f}, want {want:+.4f} "
        "(linear in the field's own units -- w needs no transform, unlike dBZ)")


def gate_no_overshoot():
    """Linear interpolation cannot exceed the contributing values, either way.

    This is what keeps the manifest's observed_min/observed_max valid AFTER
    resampling, exactly as no-inflation does for the dBZ qmax bound in T3.
    """
    rng = np.random.default_rng(4)
    sc = FakeScenario(7, 5, 3)
    ax_x = np.linspace(0.0, 6000.0, 9)
    ax_y = np.linspace(0.0, 6000.0, 8)
    ax_z = np.linspace(0.0, 6000.0, 7)
    field = rng.uniform(-30.0, 50.0, size=(7, 8, 9)).astype("f4")

    zq = np.linspace(200.0, 5800.0, sc.nz)
    yq = np.linspace(200.0, 5800.0, sc.ny)
    xq = np.linspace(200.0, 5800.0, sc.nx)
    Z, Y, X = np.meshgrid(zq, yq, xq, indexing="ij")
    query = np.stack([Z.ravel(), Y.ravel(), X.ravel()], axis=-1)

    out = regrid.resample_signed(sc, field, ax_x, ax_y, ax_z, query)
    ok = out.min() >= field.min() - 1e-4 and out.max() <= field.max() + 1e-4
    return ok, (f"resampled [{out.min():+.3f}, {out.max():+.3f}] within source "
                f"[{field.min():+.3f}, {field.max():+.3f}]")


# --- encoding gates ---------------------------------------------------------

def gate_zero_is_exact():
    """w = 0 encodes to code 128 and decodes back to EXACTLY 0.0.

    The reason the encoding is symmetric-about-128 instead of an affine fit over the
    observed range: the sign boundary is the feature a viewer reads off this field.
    """
    v = webvol.encode_signed_u8(np.zeros((4,), dtype="f4"), SCALE)
    back = webvol.decode_signed_u8(v, SCALE)
    ok = np.all(v == 128) and np.all(back == 0.0)
    return ok, f"0.0 -> code {int(v[0])} -> {back[0]:+.17g}"


def gate_roundtrip_within_quantum():
    """Round-trip error never exceeds half a code, on both signs."""
    w = np.linspace(-SCALE, SCALE, 4001).astype("f4")
    back = webvol.decode_signed_u8(webvol.encode_signed_u8(w, SCALE), SCALE)
    err = np.abs(back - w).max()
    quantum = SCALE / 127.0
    ok = err <= quantum / 2 + 1e-6
    return ok, (f"max round-trip error {err:.4f} m/s <= half-quantum "
                f"{quantum/2:.4f} ({quantum:.4f} m/s per code)")


def gate_sign_is_preserved():
    """Every strictly-positive w encodes above 128 and every negative below it.

    A quantization that let a weak downdraft cross to code 129 would paint false
    updraft in the exact place teaching cares about most -- the boundary.
    """
    w = np.concatenate([np.linspace(-SCALE, -0.05, 2000),
                        np.linspace(0.05, SCALE, 2000)]).astype("f4")
    v = webvol.encode_signed_u8(w, SCALE)
    neg_ok = np.all(v[w < 0] <= 128)
    pos_ok = np.all(v[w > 0] >= 128)
    strict = np.all(v[w <= -0.4] < 128) and np.all(v[w >= 0.4] > 128)
    return neg_ok and pos_ok and strict, (
        "no sign crossing: negatives map to <=128, positives to >=128, and beyond "
        "one quantum (0.4 m/s) the inequality is strict")


def gate_endpoints_and_clipping():
    """Codes 1..255 span exactly [-scale, +scale]; code 0 never occurs."""
    w = np.array([-SCALE, SCALE, -999.0, 999.0], dtype="f4")
    v = webvol.encode_signed_u8(w, SCALE)
    ok = list(v) == [1, 255, 1, 255]
    return ok, (f"[-scale, +scale, -999, +999] -> {list(v)} "
                "-- out-of-range clips to the endpoints, code 0 unused")


# --- negative controls ------------------------------------------------------

def negative_controls():
    """Each gate must reject a plausible WRONG implementation.

    Without these, `gate_zero_is_exact` and `gate_sign_is_preserved` are just
    assertions about arithmetic that happens to hold; the point is that they fail
    when the encoding is the one T4 rejected.
    """
    print("\nnegative controls -- the gates must reject the rejected designs")

    def control(name, ok_if_rejected, detail):
        _results.append(ok_if_rejected)
        print(f"  {'PASS' if ok_if_rejected else 'FAIL'}  fires on: {name}\n"
              f"          {detail}")

    # The design actually rejected: an affine map over an ASYMMETRIC observed range
    # (as measured on the real single-cell run, -28.78 .. +52.50 m/s).
    lo, hi = -28.78, 52.50

    def affine(w):
        return np.clip(np.rint(1.0 + 254.0 * (w - lo) / (hi - lo)), 0, 255).astype(np.uint8)

    def affine_decode(v):
        return lo + (v.astype(np.float64) - 1.0) / 254.0 * (hi - lo)

    zero_code = affine(np.zeros((1,), dtype="f4"))
    back = affine_decode(zero_code)
    control("affine-over-observed-range puts w=0 on an inexact code",
            abs(float(back[0])) > 1e-9,
            f"w=0 -> code {int(zero_code[0])} -> decodes to {float(back[0]):+.5f} m/s, "
            "not 0 -- a false-vertical-motion band exactly at the boundary")

    # A per-sequence scale would make the same code mean different m/s per package.
    a = webvol.decode_signed_u8(np.array([200], dtype=np.uint8), 52.50)
    b = webvol.decode_signed_u8(np.array([200], dtype=np.uint8), 60.60)
    control("a per-sequence scale makes one code mean two different speeds",
            abs(float(a[0]) - float(b[0])) > 1.0,
            f"code 200 = {float(a[0]):+.2f} m/s at the single cell's peak scale but "
            f"{float(b[0]):+.2f} m/s at the Phase 0 supercell's -- the fixed "
            "cross-scenario scale exists to stop this")

    # If someone "simplifies" resample_signed by reusing resample, this must break.
    sc, ax, query = tiny_grid()
    field = np.full((2, 2, 2), -12.5, dtype="f4")
    clipped = regrid.resample(sc, field, ax, ax, ax, query)
    control("the generic resample silently zeroes a downdraft",
            np.allclose(clipped, 0.0),
            f"-12.5 m/s through regrid.resample -> {float(clipped.ravel()[0]):+.3f} "
            "-- plausible, silent, and wrong; hence a separate entry point")


def main():
    print("T4 signed-field gates -- regrid.resample_signed + webvol signed uint8")
    print(f"  fixed encode scale: +/-{SCALE} m/s "
          f"({SCALE/127.0:.4f} m/s per code)\n")

    print("resampling -- the signed path must not clip")
    check("a purely NEGATIVE field survives resampling", gate_negative_survives)
    check("a +/- pair lands on its true linear midpoint", gate_mixed_sign_midpoint)
    check("linear interpolation cannot overshoot either bound", gate_no_overshoot)

    print("\nencoding -- signed uint8, symmetric about code 128")
    check("w = 0 decodes to EXACTLY 0.0 (exact sign boundary)", gate_zero_is_exact)
    check("round-trip error stays within half a code", gate_roundtrip_within_quantum)
    check("quantization never flips the sign of w", gate_sign_is_preserved)
    check("codes 1..255 span [-scale, +scale]; 0 unused", gate_endpoints_and_clipping)

    negative_controls()

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
