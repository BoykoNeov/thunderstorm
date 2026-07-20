#!/usr/bin/env python3
"""T3 gates -- dBZ is resampled in linear Z, not in dB.

    python3 pipeline/tests/test_regrid_dbz.py            # synthetic gates only
    python3 pipeline/tests/test_regrid_dbz.py --run-dir /home/boiko/thunderstorm/runs/singlecell

T3 is the task where byte-identity is SUPPOSED to break
(docs/phase2-plan-2026-07-20.md §9), so the T1b/T2 trick is unavailable here and the
gate has to be POSITIVE instead: pin the physics, then pin the direction.

  1. HAND-COMPUTED CASE. Neighbours at 20 and 40 dBZ, sampled at the midpoint.
     Linear Z: 10*log10((1e2 + 1e4)/2) = 10*log10(5050) = 37.0329 dBZ.
     In dB:    (20 + 40)/2             = 30.0 dBZ.
     A 7 dB (5x in Z) error, in the direction that hollows out echo cores. The gate
     asserts the new resampler lands on 37.03 and the old one on 30.0, so it fails
     if the transform is dropped AND if it is applied twice.

  2. JENSEN INVARIANT on a real frame. 10*log10(Z) is CONCAVE, so
        10*log10(mean Z) >= mean(10*log10 Z)
     i.e. new >= old EVERYWHERE, with equality exactly at grid points and in flat
     regions. This is the whole-field replacement for byte-identity: it cannot be
     satisfied by a resampler that is merely different, only by one that is
     correctly concave. It also proves the change is not cosmetic -- this export
     upsamples 2x (250 m from a 500 m run), so nearly every voxel is interpolated.

  3. NO INFLATION. An interpolated Z never exceeds the largest contributing Z, so
     the resampled max dBZ never exceeds the source frame's max. This is what keeps
     the web export's qmax (scanned on the CM1 grid) a valid bound, and it is the
     reason T3 cannot grow the bbox.

Gate 1 needs nothing but numpy. Gates 2-3 need the CM1 run and are skipped (not
failed) without --run-dir, so the file is runnable from Windows.
"""
import argparse
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

# `fields` is imported lazily inside _real(): it pulls in netCDF4, which the Windows
# interpreter does not have. The synthetic gates must stay runnable without it.
from cm1post import contract, regrid, scenario  # noqa: E402

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


class _Box:
    """Minimal stand-in for a Scenario -- resample only reads nx/ny/nz."""

    def __init__(self, nx, ny, nz):
        self.nx, self.ny, self.nz = nx, ny, nz


# --- gate 1: hand-computed midpoint -----------------------------------------

EXPECT_Z = 10.0 * np.log10((10.0 ** 2 + 10.0 ** 4) / 2.0)   # 37.0329... dBZ
EXPECT_DB = 30.0


def _midpoint(fn):
    """Sample the midpoint of a 20 / 40 dBZ pair along x."""
    cm1_x = np.array([0.0, 1000.0])
    cm1_y = np.array([0.0, 1000.0])
    cm1_z = np.array([0.0, 1000.0])
    field = np.empty((2, 2, 2), dtype="f4")
    field[..., 0] = 20.0
    field[..., 1] = 40.0
    query = np.array([[500.0, 500.0, 500.0]])          # (z, y, x)
    return float(fn(_Box(1, 1, 1), field, cm1_x, cm1_y, cm1_z, query).ravel()[0])


def gate_hand_computed():
    new = _midpoint(regrid.resample_dbz)
    old = _midpoint(regrid.resample)
    ok = abs(new - EXPECT_Z) < 1e-3 and abs(old - EXPECT_DB) < 1e-3
    return ok, (f"linear-Z midpoint {new:.4f} dBZ (expect {EXPECT_Z:.4f}), "
                f"dB midpoint {old:.4f} (expect {EXPECT_DB:.1f}) "
                f"-- the correction is {new - old:+.2f} dB")


def gate_grid_points_exact():
    """At a source grid point both spaces must agree -- interpolation is identity."""
    cm1_x = np.array([0.0, 1000.0])
    cm1_y = np.array([0.0, 1000.0])
    cm1_z = np.array([0.0, 1000.0])
    field = np.empty((2, 2, 2), dtype="f4")
    field[..., 0] = 20.0
    field[..., 1] = 40.0
    query = np.array([[0.0, 0.0, 1000.0]])
    got = float(regrid.resample_dbz(_Box(1, 1, 1), field, cm1_x, cm1_y, cm1_z,
                                    query).ravel()[0])
    return abs(got - 40.0) < 1e-3, f"grid point reproduces {got:.4f} dBZ (expect 40)"


def gate_floor_preserved():
    """A uniform no-echo field (0 dBZ = Z 1) must stay 0, not become -inf or NaN."""
    cm1_x = cm1_y = cm1_z = np.array([0.0, 1000.0])
    field = np.zeros((2, 2, 2), dtype="f4")
    query = np.array([[500.0, 500.0, 500.0], [2000.0, 500.0, 500.0]])  # inside, outside
    out = regrid.resample_dbz(_Box(2, 1, 1), field, cm1_x, cm1_y, cm1_z, query).ravel()
    ok = np.all(np.isfinite(out)) and np.allclose(out, 0.0, atol=1e-5)
    return ok, (f"interior {out[0]:.6f} dBZ, outside-domain fill {out[1]:.6f} dBZ "
                "(fill_value=1.0 in Z is 0 dBZ -- same 'no echo' the dB path meant)")


# --- gates 2-3: real frame --------------------------------------------------

def _real(run_dir, frame):
    from cm1post import fields  # netCDF4 -- WSL only

    sc = scenario.load("single_cell_500m", run_dir_override=run_dir)
    files = fields.frame_files(run_dir)
    ch, _ = fields.build_channels(files[frame])
    cm1_x, cm1_y, cm1_z = fields.read_grid(files[0])
    query = regrid.build_query(sc, cm1_x, cm1_y, cm1_z)
    src = ch["dbz"]
    new = regrid.resample_dbz(sc, src, cm1_x, cm1_y, cm1_z, query)
    old = regrid.resample(sc, src, cm1_x, cm1_y, cm1_z, query)
    return src, new, old


def gate_jensen(state):
    src, new, old = state
    diff = new.astype("f8") - old.astype("f8")
    bad = int((diff < -1e-4).sum())
    changed = int((diff > 1e-4).sum())
    ok = bad == 0 and changed > 0
    return ok, (f"{bad} voxels violate new >= old; {changed} of {diff.size} "
                f"({changed / diff.size * 100:.2f}%) raised, "
                f"max correction {diff.max():+.3f} dB, "
                f"mean over changed {diff[diff > 1e-4].mean():+.3f} dB")


def gate_no_inflation(state):
    src, new, old = state
    smax, nmax = float(src.max()), float(new.max())
    ok = nmax <= smax + 1e-3
    return ok, (f"resampled max {nmax:.3f} dBZ <= source max {smax:.3f} dBZ "
                "-- web qmax stays a valid bound, bbox cannot grow")


def gate_above_threshold_changed(state):
    """The correction must land where the radar view looks, not only in the noise."""
    src, new, old = state
    thr = contract.THRESHOLDS["dbz"]
    m = new > thr
    d = (new.astype("f8") - old.astype("f8"))[m]
    ok = m.sum() > 0 and d.max() > 0.1
    return ok, (f"{int(m.sum())} voxels above the {thr} dBZ export threshold, "
                f"max correction there {d.max():+.3f} dB")


# --- negative controls ------------------------------------------------------

def negative_controls(state):
    """Each gate must FAIL on the mistake it exists to catch.

    Gate 2 in particular is an INEQUALITY, and an inequality is easy to satisfy by
    accident -- `new >= old` also holds when new IS old. The controls below check
    that it rejects a no-op, rejects the arrow pointing the other way, and that the
    hand-computed gate rejects the dB resampler it was written against.
    """
    print("\nnegative controls -- each gate must reject its own failure mode")

    def control(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        _results.append(not ok)
        print(f"  {'PASS' if not ok else 'FAIL'}  fires on: {name}\n"
              f"          {'rejected' if not ok else 'ACCEPTED -- gate is blind'}"
              f": {detail[:100]}")

    src, new, old = state
    control("dBZ resampled in dB after all (no-op change)",
            lambda: gate_jensen((src, old, old)))
    control("the correction applied BACKWARDS (dB result sold as linear-Z)",
            lambda: gate_jensen((src, old, new)))
    control("resampler inflates past the source max",
            lambda: gate_no_inflation((src, new + 5.0, old)))

    real_dbz = regrid.resample_dbz
    try:
        regrid.resample_dbz = regrid.resample     # the pre-T3 behaviour
        control("hand-computed midpoint gate vs the dB resampler",
                gate_hand_computed)
    finally:
        regrid.resample_dbz = real_dbz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", help="CM1 run dir; enables the real-frame gates")
    ap.add_argument("--frame", type=int, default=150)
    args = ap.parse_args()

    print("T3 gates -- dBZ resampled in linear Z")
    print("\nsynthetic -- the physics is pinned by hand")
    check("20/40 dBZ midpoint is 37.03 dBZ, not 30.0", gate_hand_computed)
    check("source grid points reproduce exactly", gate_grid_points_exact)
    check("no-echo floor survives (no -inf, no NaN)", gate_floor_preserved)

    if args.run_dir:
        print(f"\nreal frame {args.frame} -- {args.run_dir}")
        state = _real(args.run_dir, args.frame)
        check("Jensen: new >= old everywhere, and it actually moved",
              lambda: gate_jensen(state))
        check("no inflation above the source max", lambda: gate_no_inflation(state))
        check("correction lands above the export threshold",
              lambda: gate_above_threshold_changed(state))
        negative_controls(state)
    else:
        print("\nreal-frame gates SKIPPED (pass --run-dir to run them)")

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
