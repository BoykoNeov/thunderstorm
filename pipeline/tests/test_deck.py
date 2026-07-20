#!/usr/bin/env python3
"""Negative controls for the CM1 deck generator (Phase 2 T1c).

    python3 pipeline/tests/test_deck.py

The reproduction gate lives in the CLI (`gen_deck.py --verify`) and asserts that
`single_cell_500m` regenerates the committed hand-written deck. This file asserts the
complement: that the generator's guards can actually FAIL. A gate that has only ever
passed is not yet known to work.

Reads only committed files -- no CM1 output, no WSL, no network.
"""
import copy
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import deck, scenario  # noqa: E402

SCENARIO = os.path.join(REPO, "sim", "scenarios", "single_cell_500m.json")
VALIDATION_DECK = os.path.join(REPO, "sim", "validation", "namelist.input")

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def mutated(sc, **changes):
    """A copy of the scenario with sim.namelist changes applied (None deletes)."""
    nml = copy.deepcopy(dict(sc.namelist))
    for k, v in changes.items():
        nml.pop(k, None) if v is None else nml.__setitem__(k, v)
    return scenario.Scenario(
        name=sc.name, kind=sc.kind, phase=sc.phase, description=sc.description,
        run_dir=sc.run_dir, export_voxel_m=sc.export_voxel_m,
        crop_half_width_m=sc.crop_half_width_m, crop_z_top_m=sc.crop_z_top_m,
        provenance=sc.provenance, namelist=nml, source_path=sc.source_path)


def expect_error(fn, needle):
    try:
        fn()
    except deck.DeckError as e:
        if needle.lower() in str(e).lower():
            return True, f"refused: {str(e).splitlines()[0][-90:]}"
        return False, f"refused for the WRONG reason: {e}"
    return False, "generator ACCEPTED it -- the guard is dead"


def main():
    sc = scenario.load(SCENARIO)
    text, _ = deck.generate(sc)

    print("=== 1. the comparator is not vacuous ===")

    def wrong_reference():
        with open(VALIDATION_DECK) as f:
            ref = deck.parse(f.read())
        got = deck.parse(text)
        diffs = {k for k in set(ref) | set(got)
                 if k not in ref or k not in got
                 or not deck.values_equal(ref[k], got[k])}
        # 17 scenario/derived/motion keys the generator overrode, PLUS the 7
        # output-block lines retargeted in the template. The Phase 0 validation deck
        # predates the pipeline and does not write those.
        scenario_keys = {"nx", "ny", "dx", "dy", "dtl", "timax", "tapfrq", "adapt_dt",
                         "ptype", "iwnd", "imove", "umove", "vmove",
                         "dx_inner", "tot_x_len", "dy_inner", "tot_y_len"}
        output_keys = {"output_filetype", "output_thpert", "output_cape", "output_cin",
                       "output_lcl", "output_lfc", "output_pwat"}
        want = scenario_keys | output_keys
        ok = diffs == want
        return ok, (f"{len(diffs)} keys differ vs the Phase 0 deck = "
                    f"{len(scenario_keys)} scenario/derived + {len(output_keys)} output"
                    + ("" if ok else f"  UNEXPECTED: {sorted(diffs ^ want)}"))

    check("generated deck differs from the Phase 0 validation deck", wrong_reference)

    print("\n=== 2. substring clobber: dz must not hit dz_bot/dz_top ===")

    def no_clobber():
        p = deck.parse(text)
        want = {"dz": 500.0, "dz_bot": 125.0, "dz_top": 500.0,
                "dx": 500.0, "dx_inner": 500.0, "dx_outer": 7000.0,
                "dy": 500.0, "dy_inner": 500.0, "dy_outer": 7000.0}
        bad = {k: (v, p.get(k)) for k, v in want.items()
               if not deck.values_equal(v, p.get(k))}
        return not bad, ("neighbours intact" if not bad else f"CLOBBERED: {bad}")

    check("dz/dx/dy did not clobber _bot/_top/_inner/_outer", no_clobber)

    def risk_was_real():
        with open(deck.DEFAULT_TEMPLATE) as f:
            lines = f.read().splitlines()
        loose = [l.strip() for l in lines if re.search(r"dz", l) and "=" in l]
        return len(loose) >= 3, f"{len(loose)} template lines contain 'dz': {loose}"

    check("the clobber risk is real (>=3 'dz' lines to match)", risk_was_real)

    print("\n=== 3. scenario-identity keys are required, not defaulted ===")
    for key in ("ptype", "iwnd", "nx"):
        check(f"missing '{key}' is refused",
              lambda k=key: expect_error(lambda: deck.generate(mutated(sc, **{k: None})),
                                         "missing required key"))
    check("a typo'd key is refused",
          lambda: expect_error(lambda: deck.generate(mutated(sc, ptyp=27)),
                               "unrecognised key"))

    print("\n=== 4. motion coupling ===")
    check("imove=0 with umove=12.5 is refused",
          lambda: expect_error(lambda: deck.generate(mutated(sc, umove=12.5)),
                               "contradiction"))
    check("imove=1 without umove is refused",
          lambda: expect_error(lambda: deck.generate(mutated(sc, imove=1)), "bunkers"))

    def imove_ok():
        t, _ = deck.generate(mutated(sc, imove=1, umove=12.5, vmove=3.0))
        p = deck.parse(t)
        ok = p["imove"] == 1.0 and p["umove"] == 12.5 and p["vmove"] == 3.0
        return ok, f"accepted: imove=1, umove={p['umove']}, vmove={p['vmove']}"

    check("imove=1 WITH explicit umove/vmove is accepted", imove_ok)

    print("\n=== 5. contract assertion on the output block ===")
    for flag, line in (("output_dbz", " output_dbz       = 1,"),
                       ("output_winterp", " output_winterp   = 1,")):
        def flag_off(f=flag, l=line):
            broken = text.replace(l, l.replace("= 1", "= 0"))
            if broken == text:
                return False, f"test setup failed -- '{l}' not found in the deck"
            return expect_error(lambda: deck.check_output_flags(broken, "mutant"), f)

        check(f"{flag}=0 is refused", flag_off)

    print("\n=== 6. derived geometry tracks the scenario ===")

    def derived_tracks():
        t, _ = deck.generate(mutated(sc, nx=200, dx=333.0, ny=200, dy=333.0))
        p = deck.parse(t)
        ok = (deck.values_equal(p["tot_x_len"], 66600.0)
              and deck.values_equal(p["dx_inner"], 333.0)
              and deck.values_equal(p["tot_y_len"], 66600.0)
              and deck.values_equal(p["dx_outer"], 7000.0))
        return ok, (f"nx=200,dx=333 -> tot_x_len={p['tot_x_len']}, "
                    f"dx_inner={p['dx_inner']}, dx_outer untouched={p['dx_outer']}")

    check("nx/dx propagate to tot_x_len and dx_inner", derived_tracks)

    passed = sum(_results)
    print(f"\n{'=' * 62}\n{passed} passed, {len(_results) - passed} failed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
