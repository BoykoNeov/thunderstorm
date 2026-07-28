#!/usr/bin/env python3
"""Write-convention gates for the plan/volume bricks (Phase 3 T3).

    python3 pipeline/tests/test_orientation_t3.py

WHAT THIS EXISTS FOR

Phase 2 T9 shipped the cref plan view and could only earn its orientation from an
ARGUMENT, not a test: the Phase 1 storm was a centred, near-axisymmetric pulse cell,
so an x<->y transpose was pixel-identical and the capture could not see the failure
mode. The doc said so plainly and deferred the independent test to "the Phase 3
asymmetric asset". T3 discharges that with the split supercell -- measured against
CM1's netCDF and re-measured in a real-GPU capture (docs/phase3-t3-orientation.md).

But that measurement is a ONE-SHOT: it reads a 218 GB run directory and a 1.5 GB
web package, neither of which is in git, so it can never be a repeatable gate. What
CAN be committed is the thing the argument was actually about -- the write
convention itself -- exercised through the production functions on a fixture small
enough to live in a test file. That is this file. It is the permanent half of T3;
the measurement is the empirical half.

THE ONE DESIGN CHOICE THAT MATTERS

The fixture grid is NON-SQUARE (nx=7, ny=5), and `control_square_grid_defangs_it`
proves that is load-bearing rather than incidental: on a square grid the transposed
implementation produces a same-shaped array and the gate stops firing -- which is
precisely the trap T9 fell into, one level down. A test fixture can mask a failure
mode exactly the way a symmetric storm can.
"""
import gzip
import os
import shutil
import sys
import tempfile

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import contract, regrid, webvol  # noqa: E402

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


class FakeScenario:
    """Minimal stand-in -- regrid reads nx/ny/nz, export_voxel_m and origin_m."""

    def __init__(self, nx, ny, nz, voxel=1000.0, origin=(0.0, 0.0, 0.0)):
        self.nx, self.ny, self.nz = nx, ny, nz
        self.export_voxel_m = voxel
        self.origin_m = origin


# Deliberately non-square, and deliberately a hot cell whose i != j: both are what
# make a transpose observable at all.
NX, NY, NZ = 7, 5, 3
VOX = 1000.0
HOT_I, HOT_J, HOT_K = 5, 1, 2      # x index, y index, z index of the hot cell
HOT_DBZ = 70.0
COLD_DBZ = 0.0
THR = contract.THRESHOLDS["dbz"]
VMAX = 75.0


def _scenario():
    return FakeScenario(NX, NY, NZ, VOX, (0.0, 0.0, 0.0))


def _cm1_axes(sc):
    """CM1 source axes CO-LOCATED with the export grid, so the resample is a
    pass-through and any index motion is the convention, never interpolation."""
    xs, ys, zs = regrid.export_axes(sc)
    return xs, ys, zs


def _hot_plan_field():
    """CM1-shaped 2D plan field (ny, nx) with exactly one hot cell."""
    f = np.full((NY, NX), COLD_DBZ, dtype="f4")
    f[HOT_J, HOT_I] = HOT_DBZ
    return f


def _hot_volume_field():
    f = np.full((NZ, NY, NX), COLD_DBZ, dtype="f4")
    f[HOT_K, HOT_J, HOT_I] = HOT_DBZ
    return f


def _written_bytes(channels, name):
    """Run the REAL writer and read the bytes back out of the gzip, so the gate
    covers ravel order and the file layer, not just the in-memory array."""
    tmp = tempfile.mkdtemp(prefix="t3orient-")
    try:
        webvol.write_frame(tmp, 0, channels)
        with gzip.open(os.path.join(tmp, f"f0000.{name}.gz"), "rb") as fh:
            return np.frombuffer(fh.read(), dtype=np.uint8)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _full_channels(plan, vol):
    """Every channel write_frame needs, so the plan/volume ones can be read back."""
    zeros3 = np.zeros((NZ, NY, NX), dtype=np.uint8)
    ch = {c: zeros3 for c in webvol.RGBA_CHANNELS}
    ch["dbz"] = vol
    for name in contract.WEB_EXTRA_FIELDS:
        ch[name] = zeros3
    for name in contract.WEB_PLAN_FIELDS:
        ch[name] = plan
    return ch


# --- the gates ---------------------------------------------------------------

def gate_plan_byte_lands_at_x_fastest_index():
    """A hot cell at CM1 (x_i, y_j) writes byte index j*nx + i, through the real path.

    Source field -> regrid.resample_dbz_2d (with the PRODUCTION query builder,
    regrid.build_query_2d -- writing my own query here would test my own meshgrid
    order, not the exporter's) -> webvol.encode_linear_u8 -> webvol.write_frame ->
    gunzip. The assertion is on the FLAT byte index, because that is what the viewer
    uploads into a width=nx texture; an array that merely "looks right" in numpy but
    ravels the other way would still render transposed.
    """
    sc = _scenario()
    xs, ys, _ = _cm1_axes(sc)
    out = regrid.resample_dbz_2d(sc, _hot_plan_field(), xs, ys, regrid.build_query_2d(sc))
    enc = webvol.encode_linear_u8(out, THR, VMAX)
    raw = _written_bytes(_full_channels(enc, np.zeros((NZ, NY, NX), dtype=np.uint8)), "cref")

    want = HOT_J * NX + HOT_I
    got = int(np.argmax(raw))
    nonzero = int((raw > 0).sum())
    ok = raw.size == NX * NY and got == want and nonzero == 1
    return ok, (f"{raw.size} bytes; hot byte at flat index {got}, want "
                f"j*nx+i = {HOT_J}*{NX}+{HOT_I} = {want}; {nonzero} non-zero byte(s)")


def gate_volume_byte_lands_at_the_same_x_fastest_index():
    """The 3D dbz brick uses the SAME convention: k*ny*nx + j*nx + i.

    This is the gate that licenses the viewer sharing one mapping between the cref
    plane and the volume (T9: cref's `fuv` reuses the volume's exact
    (p-boxMin)/(boxMax-boxMin) expression). That sharing is only safe while both
    bricks ravel x-fastest; if the two ever diverged, the plan view would be
    transposed relative to the cloud it is drawn under and nothing in the viewer
    would notice.
    """
    sc = _scenario()
    xs, ys, zs = _cm1_axes(sc)
    out = regrid.resample_dbz(sc, _hot_volume_field(), xs, ys, zs, regrid.build_query(sc, xs, ys, zs))
    enc = webvol.encode_linear_u8(out, THR, VMAX)
    raw = _written_bytes(_full_channels(np.zeros((NY, NX), dtype=np.uint8), enc), "dbz")

    want = (HOT_K * NY + HOT_J) * NX + HOT_I
    got = int(np.argmax(raw))
    nonzero = int((raw > 0).sum())
    ok = raw.size == NX * NY * NZ and got == want and nonzero == 1
    return ok, (f"{raw.size} bytes; hot byte at flat index {got}, want "
                f"(k*ny+j)*nx+i = {want}; {nonzero} non-zero byte(s)")


def gate_plan_and_volume_agree_on_the_same_storm_feature():
    """One feature, both bricks: the (i, j) recovered from each must be identical.

    Stated as a relationship rather than two absolute indices so it still holds if
    the layout is ever deliberately changed on BOTH sides at once -- which is the
    only way it may legally change.
    """
    sc = _scenario()
    xs, ys, zs = _cm1_axes(sc)
    plan = webvol.encode_linear_u8(
        regrid.resample_dbz_2d(sc, _hot_plan_field(), xs, ys, regrid.build_query_2d(sc)), THR, VMAX)
    vol = webvol.encode_linear_u8(
        regrid.resample_dbz(sc, _hot_volume_field(), xs, ys, zs,
                            regrid.build_query(sc, xs, ys, zs)), THR, VMAX)
    p = _written_bytes(_full_channels(plan, vol), "cref")
    v = _written_bytes(_full_channels(plan, vol), "dbz")

    pj, pi = divmod(int(np.argmax(p)), NX)
    vk, rem = divmod(int(np.argmax(v)), NY * NX)
    vj, vi = divmod(rem, NX)
    ok = (pi, pj) == (vi, vj)
    return ok, (f"plan says (i, j) = ({pi}, {pj}); volume says ({vi}, {vj}) at k={vk} "
                f"-- {'same cell' if ok else 'DIFFERENT cells: the shared fuv mapping is unsafe'}")


def gate_shipped_manifest_declares_x_fastest():
    """The tracked web manifest states the convention the viewer codes against.

    Reads the committed `supercell_333m` web manifest -- the first package whose
    contract file is in git (Phase 3 T2). A convention the pipeline honours but the
    contract does not state is a convention the next consumer has to guess.
    """
    import json
    path = os.path.join(REPO, "scenarios", "supercell_333m", "web", "web_manifest.json")
    man = json.load(open(path, encoding="utf-8"))
    vol_layout = man["volume"]["layout"]
    cref_layout = man["plan_fields"]["cref"].get("layout", "")
    ok = "x fastest" in vol_layout and "x fastest" in cref_layout
    return ok, (f"volume.layout = {vol_layout!r}; plan_fields.cref.layout = "
                f"{cref_layout!r}")


# --- negative controls -------------------------------------------------------

def negative_controls():
    """Each control is a mistake that would render a transposed or flipped map."""
    print("\nnegative controls -- the gates must reject the ways this actually breaks")
    outs = []

    def control(name, rejected, detail):
        outs.append(rejected)
        print(f"  {'PASS' if rejected else 'FAIL'}  {name}\n          {detail}")

    sc = _scenario()
    xs, ys, _ = _cm1_axes(sc)
    good = webvol.encode_linear_u8(
        regrid.resample_dbz_2d(sc, _hot_plan_field(), xs, ys, regrid.build_query_2d(sc)),
        THR, VMAX)
    want = HOT_J * NX + HOT_I

    # 1. The transpose itself -- the failure mode T9 could not test for.
    t = np.ascontiguousarray(good.T)
    control("a transposed plane does NOT land on j*nx+i",
            int(np.argmax(t.ravel())) != want,
            f"transposed hot byte at {int(np.argmax(t.ravel()))}, correct is {want} "
            f"(and its shape is {t.shape} vs {good.shape})")

    # 2. A y-flip: same shape, same ravel order, mirrored map. Nothing about the
    #    file size or the channel count would reveal it.
    fl = np.ascontiguousarray(good[::-1, :])
    control("a y-flipped plane does NOT land on j*nx+i",
            int(np.argmax(fl.ravel())) != want,
            f"y-flipped hot byte at {int(np.argmax(fl.ravel()))}, correct is {want}")

    # 3. The query built in the other order -- the realistic upstream mistake,
    #    since build_query_2d's meshgrid order is a single word ("ij") away from
    #    producing (x, y) pairs against a (y, x) field.
    xs_a, ys_a, _ = regrid.export_axes(sc)
    X, Y = np.meshgrid(xs_a, ys_a, indexing="ij")          # x-major instead of y-major
    swapped = np.stack([Y.ravel(), X.ravel()], axis=-1)
    try:
        out = regrid.resample_dbz_2d(sc, _hot_plan_field(), xs, ys, swapped)
        enc = webvol.encode_linear_u8(out, THR, VMAX)
        moved = int(np.argmax(enc.ravel())) != want
        why = f"hot byte moved to {int(np.argmax(enc.ravel()))}"
    except ValueError as e:
        moved = True
        why = f"reshape refused it outright: {e}"
    control("a query built x-major does NOT reproduce the correct byte", moved, why)

    # 4. THE FIXTURE ITSELF. On a square grid the transposed array has the same
    #    shape and control 1 can still fire only by luck of where the hot cell is;
    #    put the hot cell on the diagonal and it stops firing entirely. This is
    #    T9's trap reproduced deliberately, and it is why NX != NY above.
    n = 6
    sq = np.zeros((n, n), dtype=np.uint8)
    sq[3, 3] = 255                                          # i == j: on the mirror line
    diag_want = 3 * n + 3
    control("a SQUARE fixture with a diagonal feature defangs the transpose control",
            int(np.argmax(np.ascontiguousarray(sq.T).ravel())) == diag_want,
            f"transposed square fixture still lands on {diag_want} -- identical bytes, "
            f"gate blind. The real fixture is {NX}x{NY} with the hot cell at "
            f"i={HOT_I}, j={HOT_J} precisely to avoid this")

    return outs


def main():
    print("T3 write-convention gates -- regrid + webvol brick layout")
    print(f"  fixture: {NX}x{NY}x{NZ} @ {VOX:.0f} m, hot cell at "
          f"i={HOT_I}, j={HOT_J}, k={HOT_K} (non-square, off-diagonal)\n")
    check("plan brick: hot byte at j*nx + i", gate_plan_byte_lands_at_x_fastest_index)
    check("volume brick: hot byte at (k*ny + j)*nx + i",
          gate_volume_byte_lands_at_the_same_x_fastest_index)
    check("plan and volume recover the SAME (i, j)",
          gate_plan_and_volume_agree_on_the_same_storm_feature)
    check("the shipped manifest states the convention",
          gate_shipped_manifest_declares_x_fastest)
    _results.extend(negative_controls())
    n_ok = sum(1 for r in _results if r)
    print(f"\n{n_ok}/{len(_results)} checks passed")
    return 0 if n_ok == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
