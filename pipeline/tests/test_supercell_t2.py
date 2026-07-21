#!/usr/bin/env python3
"""Gates for the Phase 3 supercell deck (T2 -- run health + bbox gate, deck half).

    python3 pipeline/tests/test_supercell_t2.py

The supercell is the FIRST sheared, moving scenario, and its whole pedagogical
premise is "same storm family as the single-cell pulse, only sheared and put in a
moving frame big enough to hold the split." T6 proved the analogous claim for a
resolution change ("resolution is the only variable") with a DIFFERENTIAL deck gate:
compare the new scenario's generated deck against an existing scenario's generated
deck, and require the difference to be exactly the declared change and nothing else.
This is the same gate with a wider, classified expected set.

The reference is `single_cell_333m`, NOT the 500 m cell -- same resolution, so dx/dy
and dtl do NOT move, which isolates the change to shear + motion + domain + timing +
restart. Every one of the 10 differing keys is classified into a DECLARED category;
the gate fails on any key it cannot classify. That per-key classification is the gate:
seeding it from the plan's "shear/motion" shorthand would have silently accepted the
domain/timing/restart keys, and a genuinely unintended change (a microphysics or
sounding drift) would hide among them. Getting the set exactly right is the point.

The SAME-FAMILY half is the mirror image: the keys that must NOT move -- ptype, the
sounding, initiation, the vertical grid, horizontal resolution -- are asserted equal,
so any visible difference between the supercell and single-cell packages is
attributable to shear/motion alone.

Reads only committed files -- no CM1 output, no WSL, no network. (The run-health
verdict -- peak w, the split into counter-rotating movers, mover locations for T3 --
is a separate WSL analysis; see docs/phase3-t2-run-health.md.)
"""
import copy
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import deck, scenario  # noqa: E402

# The 10 keys the supercell deck changes vs single_cell_333m, each tagged with the
# DECLARED category it belongs to. A key that differs but is absent here is an
# unclassified change and fails the gate; a key listed here that does NOT differ is a
# missing change and also fails. Categories are prose only -- the gate is membership.
EXPECTED = {
    "iwnd": "shear",          # 0 -> 2  WK unidirectional shear (the supercell maker)
    "imove": "motion",        # 0 -> 1  Bunkers moving frame
    "umove": "motion",        # 0 -> 12.5  required at imove=1
    "vmove": "motion",        # 0 -> 3.0   required at imove=1
    "nx": "domain",           # 240 -> 540  bigger domain to hold the split
    "ny": "domain",           # 240 -> 540
    "tot_x_len": "domain",    # derived nx*dx
    "tot_y_len": "domain",    # derived ny*dy
    "timax": "timing",        # 3600 -> 7200  2 h, the split fully develops
    "rstfrq": "restart",      # -3600 -> 3600  hourly restarts (Category-5 optional)
}

# Keys that MUST be identical in both decks -- the same-family invariants. If any of
# these moved, "differs only by shear/motion/domain" would be false.
SAME_FAMILY = {
    "ptype": "microphysics (NSSL true-hail)",
    "isnd": "Weisman-Klemp analytic sounding",
    "iinit": "single warm bubble",
    "irandp": "no random perturbations",
    "icor": "Coriolis off (canonical WK)",
    "iorigin": "centred coordinates",
    "dx": "horizontal resolution",
    "dy": "horizontal resolution",
    "dtl": "large time step",
    "tapfrq": "output cadence",
    "nz": "vertical levels",
    "dz": "vertical spacing",
    "ztop": "domain top",
    "stretch_z": "vertical stretching",
}

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def mutated(sc, **changes):
    """A copy of a scenario with sim.namelist changes applied (None deletes)."""
    nml = copy.deepcopy(dict(sc.namelist))
    for k, v in changes.items():
        nml.pop(k, None) if v is None else nml.__setitem__(k, v)
    return scenario.Scenario(
        name=sc.name, kind=sc.kind, phase=sc.phase, description=sc.description,
        run_dir=sc.run_dir, export_voxel_m=sc.export_voxel_m,
        crop_half_width_m=sc.crop_half_width_m, crop_z_top_m=sc.crop_z_top_m,
        provenance=sc.provenance, namelist=nml, source_path=sc.source_path,
        provisional_box=sc.provisional_box)


def deck_diff(sc_a, sc_b):
    """Keys whose PARSED value differs between two generated decks (+ key count)."""
    a = deck.parse(deck.generate(sc_a)[0])
    b = deck.parse(deck.generate(sc_b)[0])
    assert set(a) == set(b), "decks have different key SETS -- template drift"
    return {k for k in a if not deck.values_equal(a[k], b[k])}, len(a)


def main():
    print("=== Phase 3 T2 -- supercell deck gate (differential vs single_cell_333m) ===\n")

    sc_ref = scenario.load("single_cell_333m")
    sc = scenario.load("supercell_333m")

    print("=== 1. the supercell config renders a runnable deck ===")

    def generates():
        text, ov = deck.generate(sc)
        flags = deck.check_output_flags(text)
        return len(text) > 4000 and len(flags) >= 3, (
            f"{len(text)} bytes, {len(ov)} overrides, output flags on: "
            f"{', '.join(flags)}")

    check("supercell_333m renders a deck that passes check_output_flags", generates)

    print("\n=== 2. THE GATE: every differing key is a DECLARED change, classified ===")

    def only_classified():
        diffs, total = deck_diff(sc_ref, sc)
        unclassified = diffs - set(EXPECTED)   # differs but not a declared change
        missing = set(EXPECTED) - diffs        # declared but did not differ
        ok = not unclassified and not missing
        by_cat = {}
        for k in sorted(diffs & set(EXPECTED)):
            by_cat.setdefault(EXPECTED[k], []).append(k)
        detail = f"{len(diffs)}/{total} keys differ: " + "; ".join(
            f"{cat}={ks}" for cat, ks in sorted(by_cat.items()))
        if unclassified:
            detail += f"  UNCLASSIFIED: {sorted(unclassified)}"
        if missing:
            detail += f"  MISSING: {sorted(missing)}"
        return ok, detail

    check("exactly the 10 declared keys differ, all classified into a category",
          only_classified)

    def all_five_categories_present():
        # The change spans FIVE categories; if the gate only saw shear/motion it would
        # miss that the domain/timing/restart keys also moved as intended.
        cats = {EXPECTED[k] for k in EXPECTED}
        return cats == {"shear", "motion", "domain", "timing", "restart"}, (
            f"declared categories: {sorted(cats)}")

    check("the declared change spans shear + motion + domain + timing + restart",
          all_five_categories_present)

    def declared_values():
        p = deck.parse(deck.generate(sc)[0])
        want = {"iwnd": 2.0, "imove": 1.0, "umove": 12.5, "vmove": 3.0,
                "nx": 540.0, "ny": 540.0, "timax": 7200.0, "rstfrq": 3600.0}
        bad = [k for k, v in want.items() if not deck.values_equal(p[k], v)]
        return not bad, (f"deck carries the config's values; mismatched: {bad}"
                         if bad else f"deck carries the config's values: {want}")

    check("the declared values actually reach the deck (not just 'something differs')",
          declared_values)

    print("\n=== 3. SAME FAMILY: the invariant keys do NOT move ===")

    def same_family_untouched():
        a = deck.parse(deck.generate(sc_ref)[0])
        b = deck.parse(deck.generate(sc)[0])
        moved = [k for k in SAME_FAMILY if not deck.values_equal(a[k], b[k])]
        return not moved, (
            f"microphysics/sounding/initiation/vertical-grid/resolution identical "
            f"in both decks ({len(SAME_FAMILY)} keys); moved: {moved}" if not moved
            else f"SAME-FAMILY VIOLATION -- these moved: {moved}")

    check("ptype, sounding, initiation, vertical grid and resolution are identical",
          same_family_untouched)

    print("\n=== 4. negative controls for the gate ===")

    def unclassified_change_detected():
        # A change outside the declared set must be caught, not absorbed. ptype=26 is
        # a same-family invariant -- moving it is exactly the drift the gate exists for.
        diffs, _ = deck_diff(sc_ref, mutated(sc, ptype=26))
        unclassified = diffs - set(EXPECTED)
        return unclassified == {"ptype"}, (
            f"a change beyond the declared set is reported as UNCLASSIFIED: "
            f"{sorted(unclassified)}")

    check("a change beyond the declared set IS detected (ptype 27->26)",
          unclassified_change_detected)

    def missing_change_detected():
        # If the supercell quietly stopped shearing, the gate must fail (iwnd missing
        # from the diff), not pass because "fewer changes is fine".
        diffs, _ = deck_diff(sc_ref, mutated(sc, iwnd=0))
        return "iwnd" not in diffs and ("shear" in {EXPECTED[k] for k in diffs & set(EXPECTED)}) is False, (
            f"with iwnd un-sheared, the shear key drops out of the diff: "
            f"iwnd differs = {'iwnd' in diffs}")

    check("a MISSING declared change is visible (un-sheared supercell)",
          missing_change_detected)

    def self_diff_is_empty():
        diffs, total = deck_diff(sc, sc)
        return not diffs, f"supercell vs itself: {len(diffs)}/{total} keys differ"

    check("the comparator reports NO diff for identical scenarios", self_diff_is_empty)

    print("\n=== 5. imove=1 is exercised POSITIVELY (first in the project) ===")

    def imove_carries_motion():
        # Phase 2 reached imove=1 only via negative controls. Here it is the real path:
        # the deck must carry imove=1 WITH nonzero umove/vmove.
        p = deck.parse(deck.generate(sc)[0])
        return (deck.values_equal(p["imove"], 1.0)
                and not deck.values_equal(p["umove"], 0.0)
                and not deck.values_equal(p["vmove"], 0.0)), (
            f"imove={p['imove']} umove={p['umove']} vmove={p['vmove']}")

    check("the moving-frame deck carries imove=1 with nonzero Bunkers umove/vmove",
          imove_carries_motion)

    def imove_guard_still_fires():
        # The generator's guard (imove=1 requires umove/vmove) must still refuse a
        # supercell stripped of its motion -- the guard that makes umove/vmove REQUIRED.
        try:
            deck.generate(mutated(sc, umove=None))
        except Exception as e:  # noqa: BLE001
            return "umove" in str(e).lower() or "imove" in str(e).lower(), (
                f"refused imove=1 without umove: {str(e)[:80]}")
        return False, "generator ACCEPTED imove=1 with no umove -- guard did not fire"

    check("the imove=1 guard refuses a moving frame with no Bunkers motion",
          imove_guard_still_fires)

    passed = sum(_results)
    print(f"\n{'=' * 62}\n{passed} passed, {len(_results) - passed} failed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
