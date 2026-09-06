#!/usr/bin/env python3
"""Gates for the coarsened web export (--web-voxel-m).

    python3 pipeline/tests/test_web_decimation.py

WHY THIS SHAPE. The obvious way to ship a lighter diorama payload is a second
scenario JSON with a bigger `voxel_m`. That is wrong here, and the reason is
written into scenario.py's own docstring: the JSON exists so "a scenario cannot be
simulated with one geometry and exported with another". A copy of the `sim` block
is a second file claiming that guarantee while free to drift from it -- edit the
parent's namelist and the copy keeps the old one, silently, while still declaring
the same provenance. So the coarser grid is a FLAG on the export, and the record
lives in `web/web_manifest.json`, which is tracked in git for web packages and is
where a reader gets its grid anyway.

That design has exactly two failure modes, and these gates are those two:

  1. A voxel size that does not divide the declared crop box. `nx`/`ny`/`nz` are
     `int(round(...))` properties, so a non-dividing factor does not raise -- it
     rounds, and the package then ships a grid that is NOT the box the manifest
     declares. The re-validation inside `with_export_voxel` is the whole safety
     argument for the flag; the refusal gates are what prove it is wired up.
  2. A coarsened manifest a reader cannot tell from a native one. `voxel_m: 666`
     alone is ambiguous with a 666 m simulation, and the package NAME cannot
     settle it either -- this project's suffixes track the SIMULATION resolution
     (`single_cell_500m` exports at 250 m), so the export voxel has never been
     readable off the name.

Plus one negative control: with the flag absent, the emitted grid block must be
key-for-key what the SHIPPED manifest already carries. A key that appeared
unconditionally would change the format for every existing package.
"""
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import contract, scenario, webvol  # noqa: E402

_results = []

# The real shipped supercell: 540x540x54 @ 333 m, crop half-width 89910 m,
# z-top 17982 m. Both spans are exact multiples of 666, which is why 2x is the
# factor this project can actually use.
SCEN = "supercell_333m"
COARSE_M = 666.0


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"         {detail}")


def _native():
    return scenario.load(SCEN)


def _qmax():
    return {c: 1.0 for c in contract.CHANNELS}


# --- 1. the derived grid follows from ONE substitution -----------------------

def gate_derived_grid_halves():
    """nx/ny/nz are properties, so the whole grid must follow from voxel_m alone."""
    sc = _native()
    c = scenario.with_export_voxel(sc, COARSE_M)
    want = (sc.nx // 2, sc.ny // 2, sc.nz // 2)
    got = (c.nx, c.ny, c.nz)
    return got == want, (f"{sc.nx}x{sc.ny}x{sc.nz} @ {sc.export_voxel_m:.0f} m "
                         f"-> {c.nx}x{c.ny}x{c.nz} @ {c.export_voxel_m:.0f} m "
                         f"(want {want})")


def gate_origin_recomputes():
    """origin_m is derived from nx and voxel_m -- it MUST move, or the coarse
    package would claim the fine package's voxel centres."""
    sc = _native()
    c = scenario.with_export_voxel(sc, COARSE_M)
    want_x = -(c.nx - 1) / 2.0 * c.export_voxel_m
    ok = (abs(c.origin_m[0] - want_x) < 1e-9
          and abs(c.origin_m[0] - sc.origin_m[0]) > 1.0)
    return ok, (f"origin x {sc.origin_m[0]:.1f} -> {c.origin_m[0]:.1f} "
                f"(derived {want_x:.1f}); z {sc.origin_m[2]:.1f} -> "
                f"{c.origin_m[2]:.1f}")


def gate_box_is_unchanged():
    """The crop box is what the run MEASURED; coarsening samples it, never resizes
    it. If the box moved, the two packages would not be the same storm volume."""
    sc = _native()
    c = scenario.with_export_voxel(sc, COARSE_M)
    same = (c.crop_half_width_m == sc.crop_half_width_m
            and c.crop_z_top_m == sc.crop_z_top_m)
    extent = c.nx * c.export_voxel_m
    return same and abs(extent - 2 * sc.crop_half_width_m) < 1e-9, (
        f"half-width {c.crop_half_width_m:.0f} m, z-top {c.crop_z_top_m:.0f} m "
        f"unchanged; coarse grid spans {extent / 1000:.3f} km")


def gate_parent_not_mutated():
    """`Scenario` is frozen and `replace` copies -- but a future refactor could
    reintroduce in-place mutation, which would corrupt any caller still holding the
    native scenario. The exporter is such a caller: it reads `native` afterwards."""
    sc = _native()
    before = (sc.export_voxel_m, sc.nx, sc.origin_m)
    scenario.with_export_voxel(sc, COARSE_M)
    after = (sc.export_voxel_m, sc.nx, sc.origin_m)
    return before == after, f"parent still {sc.nx} @ {sc.export_voxel_m:.0f} m"


def gate_voxel_count_drops_eightfold():
    """The reason this exists at all: bytes per frame scale with voxel count."""
    sc = _native()
    c = scenario.with_export_voxel(sc, COARSE_M)
    ratio = (sc.nx * sc.ny * sc.nz) / (c.nx * c.ny * c.nz)
    return abs(ratio - 8.0) < 1e-9, (
        f"{sc.nx * sc.ny * sc.nz:,} -> {c.nx * c.ny * c.nz:,} voxels "
        f"({ratio:.1f}x fewer)")


# --- 2. a non-dividing voxel is REFUSED, not rounded -------------------------

def gate_non_dividing_voxel_refused():
    """400 m divides neither span (179820/400 = 449.55, 17982/400 = 44.955).
    Without re-validation this rounds to 450x450x45 and ships a box 180.00 km wide
    while the manifest keeps declaring 179.82 km."""
    sc = _native()
    try:
        c = scenario.with_export_voxel(sc, 400.0)
    except ValueError as e:
        return "integer number" in str(e), f"refused: {str(e)[:110]}..."
    return False, (f"ACCEPTED 400 m -> {c.nx}x{c.ny}x{c.nz}, which spans "
                   f"{c.nx * 400 / 1000:.2f} km, not "
                   f"{2 * sc.crop_half_width_m / 1000:.2f} km")


def gate_a_dividing_odd_factor_is_allowed():
    """The gate must reject non-dividing sizes, not merely everything that is not
    a power of two -- 999 m (3x) divides both spans exactly and is legal."""
    sc = _native()
    c = scenario.with_export_voxel(sc, 999.0)
    return (c.nx, c.nz) == (180, 18), f"999 m -> {c.nx}x{c.ny}x{c.nz}"


def gate_cli_refuses_a_finer_voxel():
    """The flag exists to shrink the payload. Upsampling past the scenario's own
    export voxel costs bytes and adds no information -- refused at the CLI, before
    any frame is read (so this gate needs no run directory)."""
    import export_scenario
    args = types.SimpleNamespace(scenario=SCEN, run=None, out=os.devnull,
                                 frames=None, web_voxel_m=166.5)
    rc = export_scenario.cmd_export_web(args)
    return rc == 2, f"exit code {rc} for --web-voxel-m 166.5 (native 333)"


# --- 3. the manifest says which grid it is -----------------------------------

def gate_coarse_manifest_declares_itself():
    sc = _native()
    c = scenario.with_export_voxel(sc, COARSE_M)
    blk = webvol.decimation_block(sc.export_voxel_m, c.export_voxel_m)
    doc = webvol.build_manifest(c, [], _qmax(), web_decimation=blk)
    g = doc["grid"]
    ok = (g["voxel_m"] == COARSE_M
          and g["source_voxel_m"] == sc.export_voxel_m
          and abs(g["decimation_factor"] - 2.0) < 1e-12
          and "COARSENED" in g["decimation_note"])
    return ok, (f"voxel_m {g['voxel_m']:.0f}, source_voxel_m "
                f"{g['source_voxel_m']:.0f}, factor {g['decimation_factor']:g}")


def gate_native_manifest_is_key_for_key_unchanged():
    """NEGATIVE CONTROL. Without the flag the grid block must be exactly what the
    shipped packages already carry -- a key appearing unconditionally would change
    the format for every existing package without a version bump."""
    import json
    path = os.path.join(REPO, "scenarios", SCEN, "web", "web_manifest.json")
    with open(path) as f:
        shipped = json.load(f)["grid"]
    sc = _native()
    built = webvol.build_manifest(sc, [], _qmax())["grid"]
    extra = sorted(set(built) - set(shipped))
    missing = sorted(set(shipped) - set(built))
    same_values = all(built[k] == shipped[k] for k in shipped if k in built)
    return (not extra and not missing and same_values), (
        f"keys {sorted(built)}; extra {extra or 'none'}, "
        f"missing {missing or 'none'}, values match: {same_values}")


def main():
    print("coarsened web export gates -- --web-voxel-m (presentation-side only)")
    print(f"  scenario {SCEN}, native export voxel 333 m, "
          f"coarse {COARSE_M:.0f} m\n")

    print("the derived grid follows from one substitution")
    check("nx/ny/nz halve", gate_derived_grid_halves)
    check("origin_m recomputes (it MUST move)", gate_origin_recomputes)
    check("the measured crop box is unchanged", gate_box_is_unchanged)
    check("the parent scenario is not mutated", gate_parent_not_mutated)
    check("8x fewer voxels -- the point of the exercise",
          gate_voxel_count_drops_eightfold)

    print("\na non-dividing voxel is refused, not silently rounded")
    check("400 m is REFUSED", gate_non_dividing_voxel_refused)
    check("999 m (3x, divides exactly) is allowed",
          gate_a_dividing_odd_factor_is_allowed)
    check("a FINER voxel is refused at the CLI", gate_cli_refuses_a_finer_voxel)

    print("\nthe manifest distinguishes a coarse export from a native one")
    check("coarse manifest carries source_voxel_m + factor",
          gate_coarse_manifest_declares_itself)
    check("native manifest is key-for-key unchanged (negative control)",
          gate_native_manifest_is_key_for_key_unchanged)

    n, tot = sum(_results), len(_results)
    print(f"\n{n}/{tot} gates pass")
    return 0 if n == tot else 1


if __name__ == "__main__":
    sys.exit(main())
