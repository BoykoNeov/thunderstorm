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

    print("\n=== 7. optional run-control passthrough (rstfrq) ===")

    def optional_absent_uses_template():
        # single_cell_500m does NOT declare rstfrq -> the template default must stand.
        # This is exactly why adding OPTIONAL_KEYS leaves the reproduction gate intact:
        # scenarios that omit an optional key regenerate byte-for-byte.
        if "rstfrq" in sc.namelist:
            return False, "test setup: single_cell_500m unexpectedly declares rstfrq"
        p = deck.parse(text)
        return deck.values_equal(p.get("rstfrq"), -3600.0), \
            f"absent -> template default rstfrq={p.get('rstfrq')} (not substituted)"

    check("omitting an optional key keeps the template default (-3600)",
          optional_absent_uses_template)

    def optional_present_is_substituted():
        t, _ = deck.generate(mutated(sc, rstfrq=3600.0))
        p = deck.parse(t)
        return deck.values_equal(p.get("rstfrq"), 3600.0), \
            f"declared rstfrq=3600 -> deck rstfrq={p.get('rstfrq')}"

    check("a declared optional key is substituted into the deck",
          optional_present_is_substituted)

    def optional_key_keeps_the_templates_fortran_type():
        """An INTEGER namelist variable must not be emitted as a REAL.

        The cast used to be a blanket float(), which was right for rstfrq (a CM1
        REAL) and silently wrong for sbc/nbc (INTEGERs): `sbc = 1.0` is a hard
        gfortran namelist read error, so the run dies at startup. The type is now
        read off the template line -- the same source of truth as everything else
        in the generator -- so adding a future integer optional key cannot
        reintroduce it.
        """
        t, _ = deck.generate(mutated(sc, sbc=1, nbc=1, rstfrq=3600.0))
        bad = [ln.strip() for ln in t.splitlines()
               if re.match(r"^\s*(sbc|nbc)\s*=", ln) and "." in ln]
        if bad:
            return False, f"integer key emitted as REAL: {bad}"
        real = [ln.strip() for ln in t.splitlines()
                if re.match(r"^\s*rstfrq\s*=", ln)]
        if not real or "." not in real[0]:
            return False, f"REAL key lost its decimal point: {real}"
        p = deck.parse(t)
        return p.get("sbc") == 1 and p.get("nbc") == 1, \
            f"sbc={p.get('sbc')} nbc={p.get('nbc')} rstfrq line={real[0]!r}"

    check("an optional key is emitted with the template's Fortran type",
          optional_key_keeps_the_templates_fortran_type)

    # ---------------------------------------------------------------- terrain
    # Phase 3 T7. The rule is written BEFORE Phase 3T opens, and its failure mode is
    # what makes it worth a guard: a moving domain plus terrain does not crash CM1 --
    # it produces a run in which the ground slides beneath the storm, with nothing in
    # the output saying so. Both halves of the test matter: the two refusals prove the
    # guard fires on either route into terrain, and the two controls prove it is a
    # targeted rule rather than a blanket ban on terrain or on motion.
    print("\n=== terrain and a moving domain are mutually exclusive ===")

    check("terrain_flag=true with imove=1 is refused",
          lambda: expect_error(
              lambda: deck.generate(mutated(sc, terrain_flag=True, imove=1,
                                            umove=12.5, vmove=3.0)),
              "mutually exclusive"))

    check("itern!=0 with imove=1 is refused too (the OTHER route into terrain)",
          lambda: expect_error(
              lambda: deck.generate(mutated(sc, itern=1, imove=1,
                                            umove=12.5, vmove=3.0)),
              "mutually exclusive"))

    def terrain_on_a_static_domain_is_allowed():
        t, _ = deck.generate(mutated(sc, terrain_flag=True, itern=1))
        p = deck.parse(t)
        return p.get("terrain_flag") is True and p.get("imove") == 0, \
            f"terrain_flag={p.get('terrain_flag')} itern={p.get('itern')} imove={p.get('imove')}"

    check("CONTROL: terrain with imove=0 still generates",
          terrain_on_a_static_domain_is_allowed)

    def motion_without_terrain_is_allowed():
        t, _ = deck.generate(mutated(sc, imove=1, umove=12.5, vmove=3.0))
        p = deck.parse(t)
        return p.get("imove") == 1 and p.get("umove") == 12.5, \
            f"imove={p.get('imove')} umove={p.get('umove')} (supercell_333m's shape)"

    check("CONTROL: a moving domain with no terrain still generates",
          motion_without_terrain_is_allowed)

    passed = sum(_results)
    print(f"\n{'=' * 62}\n{passed} passed, {len(_results) - passed} failed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
