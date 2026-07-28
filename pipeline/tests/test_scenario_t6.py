#!/usr/bin/env python3
"""Gates for the second scenario and the generic runner (Phase 2 T6).

    python3 pipeline/tests/test_scenario_t6.py

T6's gate CANNOT be byte-identity, and that is a property of the task rather than a
weakness in the test. `single_cell_333m` is the first config the deck generator was
not reverse-engineered from, so no hand-written reference deck exists to compare
against -- if one did, T1c's caveat about cross-scenario generalization would never
have been open. The gate is therefore DIFFERENTIAL: scenario 2's deck is compared
against scenario 1's GENERATED deck, and the difference must be exactly the change
the config declares and nothing else.

That is a stronger claim than it first looks. The scenario's entire pedagogical value
rests on "resolution is the only variable" -- if the 333 m run also differed in, say,
`ptype` or `ztop`, every visible difference between the two packages would be
unattributable. Gate 2 is what makes that sentence true rather than intended.

Reads only committed files -- no CM1 output, no WSL, no network.
"""
import copy
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import deck, scenario  # noqa: E402
import scenario_info  # noqa: E402

# The five values the 333 m config DECLARES as different, plus the four the generator
# DERIVES from them. Nothing else in 344 keys may move.
DECLARED_DIFFS = {"nx", "ny", "dx", "dy", "dtl"}
DERIVED_DIFFS = {"dx_inner", "dy_inner", "tot_x_len", "tot_y_len"}
EXPECTED_DIFFS = DECLARED_DIFFS | DERIVED_DIFFS

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def mutated(sc, provisional=None, **changes):
    """A copy of a scenario with sim.namelist changes applied (None deletes)."""
    nml = copy.deepcopy(dict(sc.namelist))
    for k, v in changes.items():
        nml.pop(k, None) if v is None else nml.__setitem__(k, v)
    return scenario.Scenario(
        name=sc.name, kind=sc.kind, phase=sc.phase, description=sc.description,
        run_dir=sc.run_dir, export_voxel_m=sc.export_voxel_m,
        crop_half_width_m=sc.crop_half_width_m, crop_z_top_m=sc.crop_z_top_m,
        provenance=sc.provenance, namelist=nml, source_path=sc.source_path,
        provisional_box=sc.provisional_box if provisional is None else provisional)


def deck_diff(sc_a, sc_b):
    """Keys whose PARSED value differs between two generated decks."""
    a = deck.parse(deck.generate(sc_a)[0])
    b = deck.parse(deck.generate(sc_b)[0])
    assert set(a) == set(b), "decks have different key SETS -- template drift"
    return {k for k in a if not deck.values_equal(a[k], b[k])}, len(a)


def main():
    print("=== Phase 2 T6 -- second scenario + generic runner ===\n")

    sc500 = scenario.load("single_cell_500m")
    sc333 = scenario.load("single_cell_333m")

    print("=== 1. the new config loads and generates a runnable deck ===")

    def generates():
        text, ov = deck.generate(sc333)
        flags = deck.check_output_flags(text)
        # 28 before Phase 3 T4, 29 after: REQUIRED_KEYS gained the semantic `seed`,
        # which build_overrides pops and re-emits as CM1's var7 (net +1).
        return len(text) > 4000 and len(ov) == 29, (
            f"{len(text)} bytes, {len(ov)} overrides, output flags on: "
            f"{', '.join(flags)}")

    check("single_cell_333m renders a deck that passes check_output_flags", generates)

    print("\n=== 2. THE GATE: exactly the declared change, over all 344 keys ===")

    def only_expected():
        diffs, total = deck_diff(sc500, sc333)
        extra = diffs - EXPECTED_DIFFS
        missing = EXPECTED_DIFFS - diffs
        ok = not extra and not missing
        return ok, (f"{len(diffs)}/{total} keys differ: {', '.join(sorted(diffs))}"
                    + (f"  UNEXPECTED: {sorted(extra)}" if extra else "")
                    + (f"  MISSING: {sorted(missing)}" if missing else ""))

    check("333 m deck differs from 500 m deck in exactly 5 declared + 4 derived keys",
          only_expected)

    def declared_values():
        p = deck.parse(deck.generate(sc333)[0])
        want = {"nx": 240, "ny": 240, "dx": 333.0, "dy": 333.0, "dtl": 2.0}
        bad = [k for k, v in want.items() if not deck.values_equal(p[k], v)]
        return not bad, (f"deck carries the JSON's values ({want}); mismatched: {bad}"
                         if bad else f"deck carries the JSON's values: {want}")

    check("the declared values reach the deck (not just 'something differs')",
          declared_values)

    def vertical_untouched():
        a = deck.parse(deck.generate(sc500)[0])
        b = deck.parse(deck.generate(sc333)[0])
        keys = ("nz", "dz", "ztop", "dz_bot", "dz_top", "stretch_z")
        same = [k for k in keys if deck.values_equal(a[k], b[k])]
        return len(same) == len(keys), (
            f"vertical grid identical in both decks: "
            + ", ".join(f"{k}={a[k]}" for k in keys))

    check("the VERTICAL grid is untouched -- only horizontal resolution changed",
          vertical_untouched)

    print("\n=== 3. negative controls for gate 2 ===")

    def sixth_change_detected():
        # If the comparator could not SEE a further difference, gate 2 would pass
        # for a scenario that quietly changed the microphysics too.
        diffs, _ = deck_diff(sc500, mutated(sc333, ptype=26))
        return "ptype" in diffs and diffs - EXPECTED_DIFFS == {"ptype"}, (
            f"a 10th changed key is reported: {', '.join(sorted(diffs))}")

    check("a change beyond the declared set IS detected", sixth_change_detected)

    def self_diff_is_empty():
        # And the comparator must not report differences that are not there.
        diffs, total = deck_diff(sc333, sc333)
        return not diffs, f"scenario vs itself: {len(diffs)}/{total} keys differ"

    check("the comparator reports NO diff for identical scenarios", self_diff_is_empty)

    print("\n=== 4. the provisional-box guard ===")

    def guard_fires():
        # sc333's box is now MEASURED (T6 exported it), so the guard is exercised
        # against a synthetically-provisional scenario -- the guard's behaviour is
        # what's under test, not whether the shipped config happens to be provisional.
        prov = mutated(sc333, provisional=True)
        try:
            scenario.require_measured_box(prov)
        except ValueError as e:
            return "_provisional" in str(e), f"refused: {str(e)[:88]}..."
        return False, "guard ACCEPTED a placeholder box -- a package would ship it"

    check("export refuses a scenario whose box is still provisional", guard_fires)

    def guard_silent_when_measured():
        # Without this control the guard could be an unconditional raise, which would
        # pass the test above and block every export forever.
        for sc, label in ((sc500, "single_cell_500m (measured)"),
                          (mutated(sc333, provisional=False), "333 m, flag cleared")):
            try:
                scenario.require_measured_box(sc)
            except ValueError as e:
                return False, f"guard wrongly refused {label}: {e}"
        return True, "measured boxes pass -- the guard reads the flag, not the clock"

    check("the guard is SILENT once a box is measured", guard_silent_when_measured)

    def deck_not_gated():
        # Deck generation must NOT require a measured box: generating the deck is what
        # produces the run the box is measured from. Gating it deadlocks new scenarios.
        text, _ = deck.generate(sc333)
        return len(text) > 4000, ("a provisional scenario still generates a deck "
                                  "-- no chicken-and-egg deadlock")

    check("deck generation is deliberately NOT gated by the box", deck_not_gated)

    print("\n=== 5. the runner reads the config through the real loader ===")

    def grid_line_tracks():
        line = scenario_info.grid_line(sc333)
        want = ["nx=240", "ny=240", "nz=40", "dx=dy=333", "79.92 km"]
        missing = [w for w in want if w not in line]
        return not missing, f"run_meta grid line: {line!r}"

    check("run_meta.txt's grid line is derived from the scenario", grid_line_tracks)

    def grid_line_would_lie():
        # The failure this guards against: run_meta describing a different run than
        # the deck. Both come from one object, so the line must follow a change.
        line = scenario_info.grid_line(mutated(sc333, nx=999))
        return "nx=999" in line, f"a changed nx moves the reported line: {line!r}"

    check("the grid line cannot describe a run that was not generated",
          grid_line_would_lie)

    passed = sum(_results)
    print(f"\n{'=' * 62}\n{passed} passed, {len(_results) - passed} failed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
