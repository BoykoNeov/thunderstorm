#!/usr/bin/env python3
"""Generate a CM1 `input_sounding` from a scenario's `sim.sounding` block.

    python3 pipeline/gen_sounding.py --scenario multicell_probe -o input_sounding \\
        --report input_sounding.report.json

The file is CM1's SECOND scenario input at `isnd=7` (the first is the generated
namelist). sim/run_scenario.sh calls this and records the file's sha256 in
run_meta.txt beside the binary's, so the recovery path "regenerate from sim/ +
pipeline/" stays whole: config -> (deck, sounding) -> run.

`--report` writes the environment diagnostics (CAPE/CIN/LCL/LFC/EL for surface and
mixed-layer parcels, 0-6 km bulk shear, BRN and the WK82 regime it PREDICTS) as
JSON. They are diagnostics of the environment, computed before the run; the CM1
`cape`/`cin` output fields at t=0 are what a run-time gate compares them against.

`--wk82-reference` ignores the scenario and writes the stock WK82 profile
(theta_0=300, theta_tr=343, T_tr=213, z_tr=12 km, 14 g/kg, no wind): the input of
the base-state NEUTRALITY gate, which runs it at isnd=7 and compares th0/qv0 with an
isnd=5 run's.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm1post import scenario, sounding  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", help="scenario name (sim/scenarios/) or JSON path")
    p.add_argument("--wk82-reference", action="store_true",
                   help="write the stock WK82 profile (neutrality-gate input)")
    p.add_argument("-o", "--out", help="write input_sounding here (default: stdout)")
    p.add_argument("--report", help="write the diagnostics JSON here")
    args = p.parse_args()

    try:
        if args.wk82_reference:
            prof = sounding.build()
            label = "WK82 reference (isnd=5 equivalent)"
        elif args.scenario:
            sc = scenario.load(args.scenario)
            if not sc.sounding:
                print(f"error: {sc.source_path} has no sim.sounding block "
                      "(it is an analytic-sounding scenario, isnd=5)", file=sys.stderr)
                return 2
            prof = sounding.from_config(sc.sounding)
            label = f"{sc.name} ({sc.kind}, {sc.phase})"
        else:
            p.error("give --scenario or --wk82-reference")
    except (sounding.SoundingError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    rep = sounding.report(prof)
    print(f"sounding : {label}")
    print(f"levels   : {rep['levels']} (0-{rep['z_top_m']:.0f} m), "
          f"p_sfc {rep['p_sfc_hpa']:.1f} hPa, qv_pbl {rep['qv_pbl_gkg']:.3f} g/kg, "
          f"max RH {rep['max_rh']:.3f}, PW {rep['pwat_mm']:.1f} mm")
    for k in ("sb", "ml500"):
        d = rep[k]
        print(f"{k:<9}: CAPE {d['cape_jkg']:7.0f}  CIN {d['cin_jkg']:6.0f} J/kg   "
              f"LCL {d['lcl_m']:5.0f}  LFC {d['lfc_m']:5.0f}  EL {d['el_m']:6.0f} m")
    um, vm = rep["mean_wind_0_6km_ms"]
    print(f"wind     : 0-6 km bulk shear {rep['bulk_shear_0_6km_ms']:.1f} m/s, "
          f"0-6 km mean ({um:.1f}, {vm:.1f}) m/s")
    print(f"BRN      : {rep['brn']:.1f} -> {rep['wk82_regime_prediction']}  [PREDICTION]")

    text = sounding.to_input_sounding(prof)
    if args.out:
        with open(args.out, "w", newline="\n") as f:
            f.write(text)
        print(f"wrote {args.out} ({len(text)} bytes)")
    else:
        print()
        sys.stdout.write(text)
    if args.report:
        with open(args.report, "w", newline="\n") as f:
            json.dump(rep, f, indent=2, default=float)
            f.write("\n")
        print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
