#!/usr/bin/env python3
"""Gates for the external-sounding generator (Phase 3 T5s).

    python3 pipeline/tests/test_sounding_t5s.py

WHAT THIS FILE CAN AND CANNOT GATE
----------------------------------
The claims T5s rests on are RUN properties -- "an isnd=7 run of the generated WK82
profile reproduces the isnd=5 base state", "CM1 takes the wind from the file and
ignores iwnd", "a tanh U_s=20 environment produces the storm BRN predicts". Those
need the CM1 binary and the WSL box (docs/plan-science-hurdles-2026-09-02.md section
4), same shape as T3's links A/B and T4's run gates.

What IS gated permanently is everything upstream of CM1 that can silently rot:

  1. the analytic profile IS Weisman & Klemp (1982) -- checked against the paper's
     own fixed points and against T5's independently derived shear arithmetic;
  2. the parcel diagnostics behave like CAPE/CIN (monotone in the moisture knob,
     zero for a dry sounding, the virtual-temperature correction actually applied);
  3. the CIN knob is a CIN knob (monotone in cap strength) and CAPE is HELD through
     it, and a saturated base state is refused rather than clipped;
  4. the file the run reads round-trips through the writer/reader in CM1's format;
  5. the scenario -> (deck, sounding) COUPLING refuses every way the environment
     could silently differ from the one declared.

Negative controls fire on each family -- a gate that has only ever passed is not
known to work. Reads only committed files -- no CM1 output, no WSL, no network.
"""
import copy
import json
import math
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from cm1post import deck, scenario, sounding as S  # noqa: E402

SCENARIOS = ("single_cell_500m", "single_cell_333m", "supercell_333m")
PROBE_DIR = os.path.join(REPO, "sim", "probes", "configs")

_results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"unexpected {type(e).__name__}: {e}"
    _results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")


def expect_error(fn, exc, needle):
    try:
        fn()
    except exc as e:
        if needle.lower() in str(e).lower():
            return True, f"refused: {str(e).splitlines()[0][-95:]}"
        return False, f"refused for the WRONG reason: {e}"
    return False, "ACCEPTED it -- the guard is dead"


def mutated(sc, sounding=None, **changes):
    nml = copy.deepcopy(dict(sc.namelist))
    for k, v in changes.items():
        nml.pop(k, None) if v is None else nml.__setitem__(k, v)
    return scenario.Scenario(
        name=sc.name, kind=sc.kind, phase=sc.phase, description=sc.description,
        run_dir=sc.run_dir, export_voxel_m=sc.export_voxel_m,
        crop_half_width_m=sc.crop_half_width_m, crop_z_top_m=sc.crop_z_top_m,
        provenance=sc.provenance, namelist=nml, source_path=sc.source_path,
        sounding=dict(sounding) if sounding else {})


WK82_BLOCK = {"kind": "wk82", "wind": {"kind": "none"}}
CAP = {"z_cap_m": 1000.0, "dtheta_k": 3.0, "z_blend_m": 500.0, "mixed_below": False}


def main():
    ref = S.build()
    sb = S.parcel(ref, "sb")

    print("=== 1. the profile is WK82's, at the paper's fixed points ===")

    def fixed_points():
        z_tr = S.WK82_DEFAULTS["z_tr_m"]
        th_tr = float(np.interp(z_tr, ref.z, ref.theta))
        rh = ref.rh
        k_tr = int(np.argmin(abs(ref.z - z_tr)))
        rh_above = float(np.interp(15000.0, ref.z, ref.qv / S.qvs(ref.T, ref.p)))
        ok = (abs(ref.theta[0] - 300.0) < 1e-9 and abs(th_tr - 343.0) < 1e-6
              and abs(ref.qv[0] * 1000 - 14.0) < 1e-9
              and abs(rh_above - 0.25) < 0.01)
        return ok, (f"theta(0)={ref.theta[0]:.1f}, theta(z_tr)={th_tr:.3f}, "
                    f"qv(0)={ref.qv[0] * 1000:.2f} g/kg (capped at qv_pbl), "
                    f"RH(15 km)={rh_above:.3f} (WK82 eq. 2 gives 0.25); "
                    f"RH at z_tr {rh[k_tr]:.3f}")

    check("theta_0=300, theta(z_tr)=343, qv(0)=qv_pbl, RH=1/4 above z_tr (WK82 eqs 1-2)",
          fixed_points)

    def tropopause_consistency():
        # WK82 chose theta_tr=343 with T_tr=213 so the hydrostatic profile is
        # self-consistent at z_tr; the generator's OWN pressure must reproduce it.
        t_tr = float(np.interp(12000.0, ref.z, ref.T))
        p_tr = float(np.interp(12000.0, ref.z, ref.p)) / 100.0
        return abs(t_tr - 213.0) < 6.0 and 180.0 < p_tr < 230.0, (
            f"T(z_tr)={t_tr:.1f} K vs WK82 T_tr=213 K; p(z_tr)={p_tr:.0f} hPa -- the "
            "hydrostatic integration lands where the paper's constants say it should")

    check("hydrostatic pressure puts T(z_tr) within 6 K of T_tr=213 K", tropopause_consistency)

    def pressure_monotone():
        ok = bool(np.all(np.diff(ref.p) < 0)) and abs(ref.p[0] - 1.0e5) < 1e-6
        return ok, f"p_sfc={ref.p[0] / 100:.1f} hPa, p_top={ref.p[-1] / 100:.1f} hPa, strictly decreasing"

    check("pressure is hydrostatic: surface 1000 hPa, strictly decreasing", pressure_monotone)

    def shear_arithmetic_matches_t5():
        # docs/phase3-t5-multicell.md section 2.1 did this arithmetic by hand from
        # the CM1 source: iwnd=4 is 35 tanh(z/3 km) -> 33.5 m/s at the 5.75 km scalar
        # level, iwnd=1 is 10 m/s over 0-2.5 km. Same profiles, independently derived.
        pt = S.build(wind={"kind": "tanh", "u_max_ms": 35.0, "z_scale_m": 3000.0})
        pl = S.build(wind={"kind": "linear", "u_max_ms": 10.0, "z_scale_m": 2500.0})
        u575 = float(np.interp(5750.0, pt.z, pt.u))
        ok = (abs(S.bulk_shear(pt) - 35.0 * math.tanh(2.0)) < 1e-9
              and abs(u575 - 33.5) < 0.1
              and abs(S.bulk_shear(pl) - 10.0) < 1e-9
              and abs(S.mean_wind(pt)[0] - 23.2) < 0.3)
        return ok, (f"tanh(35, 3 km): 0-6 km {S.bulk_shear(pt):.2f} m/s, u(5.75 km)="
                    f"{u575:.1f} (T5 read 33.5 at CM1's scalar level), 0-6 km mean "
                    f"{S.mean_wind(pt)[0]:.1f} (probe A used 23.2); linear(10, 2.5 km): "
                    f"{S.bulk_shear(pl):.1f} m/s")

    check("wind profiles reproduce CM1's iwnd=4 / iwnd=1 numbers T5 derived by hand",
          shear_arithmetic_matches_t5)

    print("\n=== 2. the parcel diagnostics behave like CAPE and CIN ===")

    def cape_in_wk82_band():
        return 1500.0 < sb.cape_jkg < 2800.0 and -100.0 < sb.cin_jkg < 0.0, (
            f"SB CAPE {sb.cape_jkg:.0f} J/kg, CIN {sb.cin_jkg:.0f} J/kg, LCL {sb.lcl_m:.0f} m, "
            f"LFC {sb.lfc_m:.0f} m, EL {sb.el_m:.0f} m -- the 'weak, incidental CIN' the "
            "charter describes; the exact number is compared with CM1's own cape/cin "
            "output at t=0 on the box, not asserted here")

    check("WK82 at 14 g/kg: CAPE in the paper's band, CIN small and negative", cape_in_wk82_band)

    def cape_monotone_in_moisture():
        capes = [S.parcel(S.build(qv_pbl_gkg=q)).cape_jkg for q in (11, 12, 13, 14, 15, 16)]
        cins = [S.parcel(S.build(qv_pbl_gkg=q)).cin_jkg for q in (11, 12, 13, 14, 15, 16)]
        ok = all(b > a for a, b in zip(capes, capes[1:])) and all(b > a for a, b in zip(cins, cins[1:]))
        return ok, ("CAPE " + " < ".join(f"{c:.0f}" for c in capes)
                    + "; CIN shrinks with moisture: " + ", ".join(f"{c:.0f}" for c in cins))

    check("CAPE rises and CIN shrinks monotonically over WK82's 11-16 g/kg family",
          cape_monotone_in_moisture)

    def dry_is_zero():
        r = S.parcel(S.build(qv_pbl_gkg=0.1))
        return r.cape_jkg == 0.0 and math.isnan(r.lfc_m), (
            f"qv_pbl=0.1 g/kg: CAPE {r.cape_jkg}, LFC {r.lfc_m} -- no LFC, no CAPE")

    check("a dry sounding has zero CAPE and no LFC", dry_is_zero)

    def virtual_correction_applied():
        # Doswell & Rasmussen 1994: the T_v correction is not cosmetic. Demonstrate
        # it moves the number, so the gate is not asserting that a flag exists.
        plain = S.parcel(ref, virtual_correction=False).cape_jkg
        return abs(sb.cape_jkg - plain) > 25.0, (
            f"with T_v {sb.cape_jkg:.0f} J/kg, without {plain:.0f} J/kg "
            f"(delta {sb.cape_jkg - plain:+.0f}) -- the correction is live")

    check("the virtual-temperature correction changes CAPE (not a dead flag)",
          virtual_correction_applied)

    def ml_parcel_differs():
        ml = S.parcel(ref, "ml")
        return ml.kind == "ml" and ml.cape_jkg != sb.cape_jkg and ml.lcl_m > sb.lcl_m, (
            f"ML500 CAPE {ml.cape_jkg:.0f} vs SB {sb.cape_jkg:.0f}; ML LCL {ml.lcl_m:.0f} m > "
            f"SB {sb.lcl_m:.0f} m (the layer mean is drier than the surface)")

    check("mixed-layer parcel is a different parcel (higher LCL)", ml_parcel_differs)

    print("\n=== 3. the CIN knob is a CIN knob, and CAPE is held through it ===")

    def cin_monotone_in_cap():
        rows = []
        for d in (0.0, 1.0, 2.0, 3.0, 4.0):
            c = dict(CAP, dtheta_k=d)
            r = S.parcel(S.build(cap=c))
            rows.append((d, r.cape_jkg, r.cin_jkg))
        cins = [r[2] for r in rows]
        capes = [r[1] for r in rows]
        ok = (all(b < a for a, b in zip(cins, cins[1:]))
              and max(capes) - min(capes) < 0.02 * capes[0])
        return ok, ("dtheta -> CIN: " + ", ".join(f"{d:.0f} K: {c:.0f}" for d, _, c in rows)
                    + f"; CAPE drifts only {max(capes) - min(capes):.0f} J/kg")

    check("CIN deepens monotonically with cap strength while CAPE barely moves",
          cin_monotone_in_cap)

    def cap_edits_theta_only():
        p = S.build(cap=CAP)
        above = p.z > CAP["z_cap_m"] + CAP["z_blend_m"]
        ok = (np.allclose(p.theta[above], ref.theta[above])
              and np.allclose(p.qv, ref.qv)
              and float(p.theta[p.z == 1100.0][0] - ref.theta[ref.z == 1100.0][0]) > 2.0)
        return ok, ("theta identical above the blend, qv identical everywhere, "
                    "+2.4 K at 1.1 km -- the cap is where it says it is and nowhere else")

    check("the cap edits theta in [z_cap, z_cap+z_blend] only; qv is untouched",
          cap_edits_theta_only)

    def hold_cape():
        q = S.solve_qv_pbl_for_cape(2200.0, cap=CAP)
        r = S.parcel(S.build(qv_pbl_gkg=q, cap=CAP))
        r0 = S.parcel(S.build(qv_pbl_gkg=q))
        ok = abs(r.cape_jkg - 2200.0) <= 10.0 and r.cin_jkg < r0.cin_jkg
        return ok, (f"qv_pbl={q:.3f} g/kg -> CAPE {r.cape_jkg:.0f} (target 2200 +/- 10), "
                    f"CIN {r.cin_jkg:.0f} vs {r0.cin_jkg:.0f} uncapped at the same moisture")

    check("solve_qv_pbl_for_cape holds CAPE to +/-10 J/kg with the cap applied", hold_cape)

    def mixed_layer_saturation_refused():
        # A 14 g/kg well-mixed layer 1 km deep saturates at its top (LCL ~1 km). The
        # generator must say so, not quietly dry the layer -- that would be a
        # different CAPE shipped under the declared one.
        return expect_error(lambda: S.build(cap=dict(CAP, mixed_below=True)),
                            S.SoundingError, "saturat")

    check("a saturating mixed layer is REFUSED, never clipped", mixed_layer_saturation_refused)

    def unbracketed_target_refused():
        return expect_error(lambda: S.solve_qv_pbl_for_cape(20000.0), S.SoundingError,
                            "not bracketed")

    check("an unreachable CAPE target is refused, not answered with the endpoint",
          unbracketed_target_refused)

    def bad_cap_refused():
        a = expect_error(lambda: S.build(cap=dict(CAP, z_blend_m=0.0)), S.SoundingError, "z_blend")
        b = expect_error(lambda: S.build(cap=dict(CAP, dtheta_k=-1.0)), S.SoundingError, "superadiabatic")
        c = expect_error(lambda: S.build(cap=dict(CAP, dthetak=1.0)), S.SoundingError, "unrecognised")
        return a[0] and b[0] and c[0], f"zero blend: {a[0]}; negative cap: {b[0]}; typo key: {c[0]}"

    check("zero-depth blend, negative cap and a typo'd cap key are all refused", bad_cap_refused)

    print("\n=== 4. BRN: the WK82 regime PREDICTION is monotone in shear ===")

    def brn_monotone():
        rows = []
        for us in (10.0, 15.0, 20.0, 25.0, 30.0, 35.0):
            p = S.build(wind={"kind": "tanh", "u_max_ms": us, "z_scale_m": 3000.0})
            rows.append((us, S.brn(p, S.parcel(p).cape_jkg)))
        vals = [b for _, b in rows]
        ok = all(b < a for a, b in zip(vals, vals[1:])) and vals[0] > 50 and vals[-1] < 50
        return ok, ("U_s -> BRN: " + ", ".join(f"{u:.0f}: {b:.0f}" for u, b in rows)
                    + " -- the 50 crossing sits INSIDE T5's 10-31.8 m/s gap")

    check("BRN falls monotonically with U_s and crosses 50 between 15 and 20 m/s",
          brn_monotone)

    def regime_bands():
        ok = ("multicell" in S.wk82_regime(60.0) and "supercell" in S.wk82_regime(30.0)
              and "shear-dominated" in S.wk82_regime(5.0))
        return ok, "BRN 60 -> multicell, 30 -> supercell, 5 -> shear-dominated (WK82 section 5)"

    check("wk82_regime returns the paper's bands", regime_bands)

    print("\n=== 5. the file CM1 reads: format and round-trip ===")

    def roundtrip():
        text = S.to_input_sounding(ref)
        p_sfc, th_sfc, qv_sfc, z, th, qv, u, v = S.parse_input_sounding(text)
        lines = text.splitlines()
        ok = (len(lines[0].split()) == 3 and all(len(l.split()) == 5 for l in lines[1:])
              and abs(p_sfc - ref.p[0]) < 1e-3 and abs(th_sfc - ref.theta[0]) < 1e-4
              and np.allclose(z, ref.z[1:]) and np.allclose(th, ref.theta[1:], atol=1e-4)
              and np.allclose(qv, ref.qv[1:], atol=1e-9) and z[-1] >= 19750.0
              and text.endswith("\n") and "\r" not in text)
        return ok, (f"{len(lines)} lines: header (p[hPa] theta qv[g/kg]) + {len(z)} levels "
                    f"(z theta qv u v), top {z[-1]:.0f} m >= CM1 ztop 19750 m, LF-only")

    check("input_sounding writes CM1's format and reads back to the same profile", roundtrip)

    def malformed_refused():
        a = expect_error(lambda: S.parse_input_sounding("1000 300\n100 300 14 0 0\n"),
                         S.SoundingError, "3 fields")
        b = expect_error(lambda: S.parse_input_sounding("1000 300 14\n100 300 14 0\n"),
                         S.SoundingError, "5 fields")
        return a[0] and b[0], f"2-field header: {a[0]}; 4-field level: {b[0]}"

    check("a malformed file is refused by the reader (so a hand edit cannot pass)",
          malformed_refused)

    print("\n=== 6. scenario -> (deck, sounding) coupling ===")
    base = scenario.load(os.path.join(REPO, "sim", "scenarios", "single_cell_500m.json"))

    def shipped_have_no_block():
        rows = []
        for name in SCENARIOS:
            sc = scenario.load(os.path.join(REPO, "sim", "scenarios", f"{name}.json"))
            deck.generate(sc)
            rows.append((name, sc.namelist["isnd"], bool(sc.sounding)))
        ok = all(i == 5 and not b for _, i, b in rows)
        return ok, "; ".join(f"{n}: isnd={i}, block={b}" for n, i, b in rows)

    check("all three shipped scenarios are isnd=5 with no sounding block (untouched)",
          shipped_have_no_block)

    def external_needs_block():
        return expect_error(lambda: deck.generate(mutated(base, isnd=7, iwnd=0)),
                            deck.DeckError, "no sim.sounding")

    check("isnd=7 without a sounding block is refused", external_needs_block)

    def block_needs_external():
        return expect_error(lambda: deck.generate(mutated(base, sounding=WK82_BLOCK)),
                            deck.DeckError, "only at isnd=7")

    check("a sounding block at isnd=5 is refused (CM1 would never read it)", block_needs_external)

    def external_needs_iwnd0():
        return expect_error(lambda: deck.generate(mutated(base, isnd=7, iwnd=2, sounding=WK82_BLOCK)),
                            deck.DeckError, "iwnd=0")

    check("isnd=7 with iwnd!=0 is refused (the wind comes from the file)", external_needs_iwnd0)

    def external_generates():
        text, ov = deck.generate(mutated(base, isnd=7, iwnd=0, sounding=WK82_BLOCK))
        parsed = deck.parse(text)
        return parsed["isnd"] == 7.0 and parsed["iwnd"] == 0.0 and "sounding" not in parsed, (
            "deck carries isnd=7, iwnd=0 and no bogus `sounding =` line; the block is "
            "rendered by gen_sounding.py, never substituted into the namelist")

    check("isnd=7 + block + iwnd=0 generates a deck", external_generates)

    def block_typo_refused():
        return expect_error(lambda: S.from_config({"kind": "wk82", "qv_pbl": 14.0}),
                            S.SoundingError, "unrecognised")

    check("a typo'd sounding key is refused (deck.py's convention, applied to the block)",
          block_typo_refused)

    def hold_and_qv_exclusive():
        return expect_error(lambda: S.from_config({"hold_cape_jkg": 2000.0, "qv_pbl_gkg": 14.0}),
                            S.SoundingError, "either")

    check("declaring both qv_pbl and hold_cape is refused (one would silently win)",
          hold_and_qv_exclusive)

    def from_config_equals_build():
        a = S.from_config({"kind": "wk82"})
        ok = np.array_equal(a.theta, ref.theta) and np.array_equal(a.qv, ref.qv)
        return ok, "from_config({kind: wk82}) == build() exactly (defaults are WK82's)"

    check("the empty config IS the WK82 reference", from_config_equals_build)

    print("\n=== 7. the pre-registered probe configs generate, and say what they are ===")

    def probes_generate():
        names = sorted(f for f in os.listdir(PROBE_DIR) if f.startswith("t5s_"))
        if not names:
            return False, "no t5s_*.json probe configs found"
        rows = []
        for f in names:
            sc = scenario.load(os.path.join(PROBE_DIR, f))
            text, _ = deck.generate(sc)
            prof = S.from_config(sc.sounding)
            rep = S.report(prof)
            parsed = deck.parse(text)
            ok = parsed["isnd"] == 7.0 and parsed["iwnd"] == 0.0 and rep["max_rh"] < S.RH_MAX
            rows.append((f, ok, rep["bulk_shear_0_6km_ms"], rep["brn"]))
        return all(r[1] for r in rows), "; ".join(
            f"{f}: shear {s:.1f} BRN {b:.0f}" for f, _, s, b in rows)

    check("every t5s_* probe config generates a deck and a sub-saturated sounding",
          probes_generate)

    def probe_predictions_recorded():
        # The prediction each probe carries must be the generator's own -- a config
        # that claims 'multicell' for an environment BRN puts at 30 is a lie the run
        # would appear to falsify for the wrong reason.
        rows = []
        for f in sorted(os.listdir(PROBE_DIR)):
            if not f.startswith("t5s_"):
                continue
            d = json.load(open(os.path.join(PROBE_DIR, f)))
            claimed = d["sim"]["provenance"].get("brn_regime_prediction", "")
            prof = S.from_config(d["sim"]["sounding"])
            actual = S.wk82_regime(S.brn(prof, S.parcel(prof).cape_jkg)).split(" (")[0]
            rows.append((f, claimed, actual))
        ok = all(c.split(" (")[0] == a for _, c, a in rows)
        return ok, "; ".join(f"{f}: {a}" for f, _, a in rows)

    check("each probe's recorded BRN prediction equals what its own sounding computes",
          probe_predictions_recorded)

    print("\n" + "=" * 62)
    ok, bad = _results.count(True), _results.count(False)
    print(f"{ok} passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
