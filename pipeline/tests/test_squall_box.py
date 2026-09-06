#!/usr/bin/env python3
"""Gates for the RECTANGULAR export box and the periodic-axis measurement rule.

    python3 pipeline/tests/test_squall_box.py

The squall line is the scenario the export contract could not describe. `Scenario`
carried one `crop_half_width_m` and derived `ny = nx`, so the box was SQUARE BY
CONSTRUCTION -- and a line is compact ACROSS the line and spans the whole domain
ALONG it. The only legal square box for a line was therefore the full domain: the
largest possible package, mostly empty (docs/plan-science-hurdles-2026-09-02.md
section 4.4; the hazard was first flagged as docs/phase3-t5-multicell.md section
11.7).

Two things are under test, and the second was NOT in section 4.4's scope list:

1. The SCHEMA. An optional `crop_half_depth_m` gives y its own half-extent, and
   nx/ny/origin_m/manifest follow. Optional so every shipped config and package is
   byte-unchanged -- the manifest already wrote `dimensions` and `extent_m.x/.y` as
   separate keys, so only the VALUES become unequal and format_version stays put.

2. The MEASUREMENT. `export_scenario.cmd_bbox` collapsed both horizontal axes into
   one scalar (`half = max(half, |x|..., |y|...)`), which is right for a square box
   and silently wrong otherwise: on a periodic-y line it would report the full
   domain as "the" half-width and demand a square box that large -- arriving at the
   mostly-empty package through the sweep instead of through the schema.

**Why every fixture here has nx != ny != nz, all three distinct.** This project has
already been bitten: "a symmetric fixture / near-origin feature / SQUARE TEST GRID
silently defang a transpose test" (T5's recorded lessons). A 208x208 grid cannot
tell (nz, ny, nx) from (nz, nx, ny). Nothing in this file is square.

Reads only committed files -- no CM1 output, no WSL, no network, no netCDF.
"""
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import densevol, manifest, regrid, scenario  # noqa: E402

SHIPPED = ("single_cell_500m", "single_cell_333m", "supercell_333m")

# The rectangular fixture. 120 x 180 x 54 -- no two equal, and no two in a ratio
# any of the derivations could accidentally satisfy.
VOXEL = 333.0
HALF_X = 19980.0     # -> nx = 120
HALF_Y = 29970.0     # -> ny = 180
Z_TOP = 17982.0      # -> nz = 54

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def refuses(fn, needle):
    """`fn` must raise a ValueError whose message contains `needle`."""
    try:
        fn()
    except ValueError as e:
        msg = str(e)
        return needle in msg, f"refused: {msg[:110]}..."
    return False, "NOT refused -- the gate let it through"


def fixture(half_x=HALF_X, half_y=HALF_Y, z_top=Z_TOP, voxel=VOXEL,
            namelist=None, provisional=False, validate=True):
    """A synthetic Scenario. Never loaded from disk -- these geometries do not
    correspond to any run, and inventing a JSON for them would put a config in
    sim/scenarios/ that no scenario owns."""
    sc = scenario.Scenario(
        name="fixture_line", kind="multicell", phase="test",
        description="rectangular-box fixture", run_dir="/nonexistent",
        export_voxel_m=voxel, crop_half_width_m=half_x, crop_z_top_m=z_top,
        crop_half_depth_m=half_y, namelist=dict(namelist or {}),
        source_path="<fixture>", provisional_box=provisional)
    if validate:
        scenario._validate(sc, "<fixture>")
    return sc


# --- 1. nothing shipped moves -------------------------------------------------

def gate_shipped_square():
    """Every shipped scenario stays square, by ABSENCE of the new key."""
    rows = []
    for name in SHIPPED:
        sc = scenario.load(name)
        if sc.crop_half_depth_m is not None:
            return False, f"{name} unexpectedly declares crop_half_depth_m"
        if sc.ny != sc.nx or sc.half_depth_m != sc.crop_half_width_m:
            return False, f"{name}: ny={sc.ny} != nx={sc.nx}"
        rows.append(f"{name} {sc.nx}x{sc.ny}x{sc.nz}")
    return True, "; ".join(rows)


def gate_shipped_manifest_extent():
    """extent_m.y still equals extent_m.x for a square scenario.

    The BYTE-identity of the shipped manifest is gated by test_manifest.py's
    rebuild check (17/17); this asserts the specific key the change touched, so a
    failure here says WHICH key moved rather than only that one did.
    """
    sc = scenario.load("supercell_333m")
    doc = manifest.build(sc, frames=[], provenance={})
    ext = doc["volume"]["extent_m"]
    ok = ext["y"] == ext["x"] == [-sc.crop_half_width_m, sc.crop_half_width_m]
    return ok, f"x={ext['x']} y={ext['y']}"


def gate_shipped_not_periodic():
    """No shipped scenario has a periodic axis, so the new rule cannot bind one."""
    rows = []
    for name in SHIPPED:
        per = scenario.periodic_axes(scenario.load(name))
        if any(per.values()):
            return False, f"{name} reports periodic {per}"
        rows.append(f"{name} {per}")
    return True, "; ".join(rows)


# --- 2. the rectangular grid --------------------------------------------------

def gate_grid_rectangular():
    sc = fixture()
    got = (sc.nx, sc.ny, sc.nz)
    ok = got == (120, 180, 54) and len(set(got)) == 3
    return ok, f"{sc.describe_grid()}   all three distinct: {len(set(got)) == 3}"


def gate_origin_follows_depth():
    """origin_m's y term is derived from ny, and the box centre stays (0,0).

    The static bbox centre is the SVT constraint -- it must survive the box
    becoming rectangular, since that is the one thing UE cannot tolerate moving.
    """
    sc = fixture()
    ox, oy, oz = sc.origin_m
    want_ox = -(sc.nx - 1) / 2.0 * VOXEL
    want_oy = -(sc.ny - 1) / 2.0 * VOXEL
    cx = ox + (sc.nx - 1) / 2.0 * VOXEL       # centre of the voxel-CENTRE span
    cy = oy + (sc.ny - 1) / 2.0 * VOXEL
    doc = manifest.build(sc, frames=[], provenance={})
    ok = (abs(ox - want_ox) < 1e-9 and abs(oy - want_oy) < 1e-9
          and ox != oy and abs(cx) < 1e-9 and abs(cy) < 1e-9
          and doc["volume"]["bbox_center_m"] == [0.0, 0.0, Z_TOP / 2.0])
    return ok, (f"origin ({ox:.1f}, {oy:.1f}, {oz:.1f}) -- x and y DIFFER; "
                f"centre ({cx:.1f}, {cy:.1f}); bbox_center_m "
                f"{doc['volume']['bbox_center_m']}")


def gate_manifest_rectangular():
    sc = fixture()
    v = manifest.build(sc, frames=[], provenance={})["volume"]
    ok = (v["dimensions"] == [120, 180, 54]
          and v["extent_m"]["x"] == [-HALF_X, HALF_X]
          and v["extent_m"]["y"] == [-HALF_Y, HALF_Y]
          and v["extent_m"]["x"] != v["extent_m"]["y"])
    return ok, f"dimensions {v['dimensions']}  extent {v['extent_m']}"


def gate_transpose_refused():
    """densevol REFUSES a (nz, nx, ny) array and accepts (nz, ny, nx).

    On the old square grid both shapes were (nz, N, N) and this check could not
    fail -- the exact defanging T5 recorded. It can fail now.
    """
    import tempfile
    from cm1post import contract
    sc = fixture()
    good = {c: np.zeros((sc.nz, sc.ny, sc.nx), dtype=np.float32)
            for c in contract.CHANNELS}
    bad = {c: a.transpose(0, 2, 1).copy() for c, a in good.items()}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.densevol")
        densevol.write(p, sc, good)          # must not raise
        size_ok = os.path.getsize(p) > sc.nx * sc.ny * sc.nz * 4
        try:
            densevol.write(p, sc, bad)
        except ValueError as e:
            return size_ok, f"transposed (nz,nx,ny) refused: {str(e)[:80]}"
    return False, "a TRANSPOSED array was accepted -- shapes are not distinguishable"


def gate_regrid_axes():
    """export_axes spans each half-extent independently."""
    sc = fixture()
    xs, ys, zs = regrid.export_axes(sc)
    ok = (len(xs) == 120 and len(ys) == 180 and len(zs) == 54
          and abs(xs[-1] - xs[0] - (HALF_X * 2 - VOXEL)) < 1e-6
          and abs(ys[-1] - ys[0] - (HALF_Y * 2 - VOXEL)) < 1e-6)
    return ok, (f"x spans {xs[0]:.1f}..{xs[-1]:.1f} ({len(xs)}), "
                f"y spans {ys[0]:.1f}..{ys[-1]:.1f} ({len(ys)})")


def gate_depth_divisibility():
    """A depth that is not a whole number of voxels is refused, same as width."""
    return refuses(lambda: fixture(half_y=HALF_Y + 100.0), "crop_half_depth_m")


def gate_depth_positive():
    return refuses(lambda: fixture(half_y=-1.0), "crop_half_depth_m must be > 0")


# --- 3. periodicity, read from the namelist -----------------------------------

def gate_periodic_default_open():
    """No sbc/nbc in the namelist means the template default -- open, not periodic."""
    per = scenario.periodic_axes(fixture(namelist={"nx": 180, "dx": 999.0}))
    return per == {"x": False, "y": False}, f"{per} (template runs 2 on all sides)"


def gate_periodic_detected():
    per = scenario.periodic_axes(fixture(namelist={"sbc": 1, "nbc": 1}))
    return per == {"x": False, "y": True}, f"{per}"


def gate_half_declared_axis_refused():
    """Periodicity is a property of the AXIS. One wall is a typo, not a setup."""
    return refuses(
        lambda: scenario.periodic_axes(fixture(namelist={"sbc": 1, "nbc": 2})),
        "property of the y AXIS")


# --- 4. the periodic-axis extent rule ----------------------------------------

# A line: 180 x 999 m = 179.82 km domain, so the full y half-extent is 89910 m.
LINE_NML = {"nx": 180, "ny": 180, "dx": 999.0, "dy": 999.0, "sbc": 1, "nbc": 1}
FULL_HALF = 89910.0


def line_fixture(half_y=FULL_HALF, half_x=19980.0, **kw):
    return fixture(half_x=half_x, half_y=half_y, voxel=333.0,
                   namelist=LINE_NML, **kw)


def gate_domain_half():
    sc = line_fixture()
    got = (scenario.domain_half_m(sc, "x"), scenario.domain_half_m(sc, "y"))
    return got == (FULL_HALF, FULL_HALF), f"x {got[0]:.1f} m, y {got[1]:.1f} m"


def gate_line_box_accepted():
    """The whole point: a box compact in x and full-domain in y CLEARS the gate.

    This is what could not be expressed before -- and note the result is not
    square (120 x 540 x 54), so it is also not the mostly-empty full-domain
    package the old schema forced. Across the line the box is 40 km wide; along
    it, the full 180 km domain.
    """
    sc = line_fixture()
    scenario.require_measured_box(sc)   # must not raise
    return (sc.nx, sc.ny, sc.nz) == (120, 540, 54), (
        f"{sc.describe_grid()} -- accepted with x measured and y by construction")


def gate_cropped_periodic_axis_refused():
    """Smaller than the domain on a periodic axis is a crop with no outside."""
    return refuses(lambda: scenario.require_measured_box(
        line_fixture(half_y=FULL_HALF / 2)), "PERIODIC")


def gate_larger_periodic_axis_refused():
    """Bigger is refused too -- the box would advertise volume the domain lacks."""
    return refuses(lambda: scenario.require_measured_box(
        line_fixture(half_y=FULL_HALF + 999.0)), "PERIODIC")


def gate_provisional_still_first():
    """The placeholder guard is unchanged and still fires BEFORE the new rule."""
    return refuses(lambda: scenario.require_measured_box(
        line_fixture(half_y=FULL_HALF / 2, provisional=True)), "_provisional")


def gate_open_axis_unconstrained():
    """A non-periodic axis is NOT forced to the domain -- cropping is its job."""
    sc = fixture(half_x=19980.0, half_y=29970.0,
                 namelist={"nx": 540, "ny": 540, "dx": 333.0, "dy": 333.0})
    scenario.require_measured_box(sc)   # must not raise
    return True, ("open box 120x180 inside a 540x540 domain accepted -- the "
                  "sweep, not the boundary condition, is its gate")


def gate_c2_probe_loads():
    """The real periodic-y config (t5probe_c2) loads, reads periodic, and is
    still refused for the RIGHT reason (it is a probe: provisional, never
    exported)."""
    sc = scenario.load(os.path.join(REPO, "sim", "probes", "configs",
                                    "t5probe_c2.json"))
    per = scenario.periodic_axes(sc)
    if per != {"x": False, "y": True}:
        return False, f"periodicity read as {per}"
    scenario.check_periodic_extents(sc)   # its box IS the full domain already
    ok, detail = refuses(lambda: scenario.require_measured_box(sc), "_provisional")
    return ok, f"periodic {per}, extent {sc.half_depth_m:.0f} m == domain; {detail}"


# --- 5. the sweep's per-axis verdict (the bug section 4.4 did not name) -------

def gate_verdict_axes_independent():
    """A y union larger than the box must fail Y ONLY -- never x.

    The collapsed `half = max(...)` could not do this: one scalar carried both
    axes, so a large y overflow was indistinguishable from a large x one.
    """
    sc = fixture(namelist={"nx": 540, "ny": 540, "dx": 333.0, "dy": 333.0})
    rows = scenario.box_verdict(sc, half_x=15000.0, half_y=40000.0,
                                       ztop=17000.0)
    by = {r[0]: r for r in rows}
    ok = (by["x half-width"][3] is True and by["y half-depth"][3] is False
          and by["top"][3] is True)
    return ok, "; ".join(f"{r[0]} {'ok' if r[3] else 'FAIL'}" for r in rows)


def gate_verdict_line_passes():
    """The squall-line case end to end: y reaches the wall and that is a PASS.

    Under the collapsed rule the y union (89.74 km) became "the" half-width and
    was checked against crop_half_width_m (19.98 km) -- an instant FAIL, with the
    only remedy a square 180 x 180 km box.
    """
    sc = line_fixture()
    rows = scenario.box_verdict(sc, half_x=18000.0, half_y=89744.0,
                                       ztop=17000.0)
    ok = all(r[3] for r in rows)
    y = [r for r in rows if r[0] == "y half-depth"][0]
    return ok, (f"all axes ok; y measured {y[1]/1000:.3f} km against box "
                f"{y[2]/1000:.3f} km -- {y[4]}")


def gate_verdict_periodic_box_must_be_full():
    """On a periodic axis the verdict tracks the BOX, not the union: a cropped
    box fails even when the measured union fits inside it."""
    sc = line_fixture(half_y=FULL_HALF / 2, validate=True)
    rows = scenario.box_verdict(sc, half_x=18000.0, half_y=1000.0,
                                       ztop=17000.0)
    y = [r for r in rows if r[0] == "y half-depth"][0]
    return y[3] is False, (f"y union 1.000 km fits box {y[2]/1000:.3f} km and "
                           f"still FAILS: {y[4]}")


def main():
    print(__doc__.strip().split("\n\n")[0])
    print("\n=== 1. nothing shipped moves ===")
    check("all three shipped scenarios stay square (key ABSENT)", gate_shipped_square)
    check("shipped manifest extent_m.y still == extent_m.x", gate_shipped_manifest_extent)
    check("no shipped scenario has a periodic axis", gate_shipped_not_periodic)

    print("\n=== 2. the rectangular grid (nx != ny != nz) ===")
    check("a declared depth derives a rectangular grid", gate_grid_rectangular)
    check("origin_m follows ny; bbox centre stays (0,0)", gate_origin_follows_depth)
    check("the manifest carries unequal x/y extents", gate_manifest_rectangular)
    check("a TRANSPOSED (nz,nx,ny) array is refused", gate_transpose_refused)
    check("regrid axes span each half-extent independently", gate_regrid_axes)
    check("a depth off the voxel grid is refused", gate_depth_divisibility)
    check("a non-positive depth is refused", gate_depth_positive)

    print("\n=== 3. periodicity comes from the NAMELIST ===")
    check("absent sbc/nbc means open (template default)", gate_periodic_default_open)
    check("sbc=nbc=1 reads as a periodic y axis", gate_periodic_detected)
    check("a half-declared axis (sbc=1, nbc=2) is refused", gate_half_declared_axis_refused)

    print("\n=== 4. the periodic-axis extent rule ===")
    check("domain_half_m reads nx*dx/2 from the namelist", gate_domain_half)
    check("a LINE box (compact x, full-domain y) is ACCEPTED", gate_line_box_accepted)
    check("a cropped periodic axis is refused", gate_cropped_periodic_axis_refused)
    check("an over-large periodic axis is refused", gate_larger_periodic_axis_refused)
    check("the _provisional guard still fires first", gate_provisional_still_first)
    check("an OPEN axis is not forced to the domain", gate_open_axis_unconstrained)
    check("the real t5probe_c2 config reads periodic", gate_c2_probe_loads)

    print("\n=== 5. the sweep's per-axis verdict ===")
    check("x and y verdicts are independent", gate_verdict_axes_independent)
    check("a wall-touching periodic union PASSES", gate_verdict_line_passes)
    check("a cropped periodic box FAILS even when the union fits",
          gate_verdict_periodic_box_must_be_full)

    n = len(_results)
    p = sum(_results)
    print("\n" + "=" * 62)
    print(f"{p} passed, {n - p} failed")
    return 0 if p == n else 1


if __name__ == "__main__":
    sys.exit(main())
