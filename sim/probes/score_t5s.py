#!/usr/bin/env python3
"""Phase 3 T5s section 4.2 -- score the shear sweep under the AMENDED rules.

    python3 sim/probes/score_t5s.py

Amended scoring is pre-registered in `docs/plan-science-hurdles-2026-09-02.md`
section 4.2 and recorded in `sim/probes/README.md`. Three things it enforces that a
bare `classify_t5` run would not:

1. **Criterion 2 (births) is a DESCRIPTOR, not a label.** It failed its own control
   validation (SC 2 births against a bar of <=1; PC's 0 is a non-exercise, and its
   gust-front ring shows up four times identical to the decimal in the censored
   tail). It is printed with its control numbers beside it and never decides
   anything.

2. **P1 = 80 min is the CEILING, not evidence.** `P1` is measured over the mature
   window -- 80 min of a 120 min run -- and T5 section 13.4 measured all six of its
   storms at that ceiling while the SUPERCELL band starts at 35 min. A member reading
   80 has said its rotation did not break; it has NOT said it is a supercell rather
   than a multicell whose successive cells each rotate. This script prints `AT
   CEILING` next to any 80 so the number cannot be read as a result later.

3. **Containment voids a member outright.** `classify_t5.drift_fit`'s section-5 rule:
   a storm within BOUNDARY_KM of an OPEN wall in a mature frame is NOT SCORABLE at
   any label. `umove` here is a 0-6 km mean wind, i.e. a SUPERCELL-motion estimate,
   and a multicell propagates on its cold pool -- so this is a live hazard, not a
   formality.

The reading the sweep is FOR is the descriptor family as a TREND across a controlled
one-parameter environment sweep (U_s = 15/20/25 m/s, thermodynamics fixed). That is
what three members buy that one member cannot, and it is the first such sweep this
project has had.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import births_t5s as B  # noqa: E402
import classify_t5 as C  # noqa: E402

SWEEP = ["t5s_us15", "t5s_us20", "t5s_us25"]
CONTROLS = ["t5probe_sc", "t5probe_pc"]
P1_CEILING_MIN = 80.0        # (120 min run) - (MATURE_MIN 40) = the most P1 can read

BRN = {"t5s_us15": 58.6, "t5s_us20": 33.0, "t5s_us25": 21.1,
       "t5probe_sc": None, "t5probe_pc": None}
SHEAR = {"t5s_us15": 14.46, "t5s_us20": 19.28, "t5s_us25": 24.1,
         "t5probe_sc": 31.8, "t5probe_pc": 0.0}
PREDICTED = {"t5s_us15": "multicell", "t5s_us20": "supercell", "t5s_us25": "supercell",
             "t5probe_sc": "-", "t5probe_pc": "-"}


def score(name):
    run = C.run_metrics(name)
    label, ev = C.classify_v3(run)
    dr = C.drift_fit(run)
    bi = B.births(name)
    fr = C.mature(run["frames"])
    return {
        "name": name, "label": label, "ev": ev, "drift": dr, "births": bi,
        "max_updrafts": max((f["n_updrafts"] for f in fr), default=0),
        "max_cells": max((f["n_cells"] for f in fr), default=0),
        "max_cold_km2": max((f["coldpool_area_km2"] for f in fr), default=0.0),
        "min_thpert": min((f["min_thpert_sfc"] for f in fr), default=0.0),
        "peak_w": max((f["max_w"] for f in fr), default=0.0),
    }


def main():
    print(__doc__.split("\n")[0])
    print("=" * 92)
    rows = [score(n) for n in SWEEP + CONTROLS]

    for r in rows:
        ev, dr, bi = r["ev"], r["drift"], r["births"]
        p1 = ev.get("P1_chain_min", 0.0)
        ceil = "  <-- AT CEILING: not evidence of a supercell" \
            if p1 >= P1_CEILING_MIN else ""
        print(f"\n=== {r['name']}   (0-6 km shear {SHEAR[r['name']]} m/s, "
              f"BRN {BRN[r['name']]}, WK82 predicts {PREDICTED[r['name']]}) ===")
        if dr["void"]:
            print(f"  !! VOID -- NOT SCORABLE: {dr['void_why']}")
        print(f"  label (crit 1'/2'/3, thresholds unchanged) : {r['label']}")
        print(f"  P1 rotation persistence                    : {p1:g} min "
              f"(band {C.T_PERSIST_MIN:g}+-{C.T_BAND_MIN:g}){ceil}")
        print(f"  criterion 2' organisation  R / E           : "
              f"{ev.get('median_R')} / {ev.get('median_E')} "
              f"(floors {C.R_FLOOR} / {C.E_FLOOR}, "
              f"{ev.get('qualifying_frames')} qualifying frames)")
        print(f"  criterion 3 echo span                      : "
              f"{ev.get('echo_span_min')} min (floor {C.MIN_SYSTEM_MINUTES:g})")
        print(f"  containment: min clearance cell / w        : "
              f"{dr['min_cell_clearance_km']} / {dr['min_w_clearance_km']} km "
              f"(void below {C.BOUNDARY_KM:g})")
        print(f"  drift vs declared motion                   : "
              f"measured ({dr['drift_u_ms']}, {dr['drift_v_ms']}) m/s -> implied "
              f"umove/vmove ({dr['implied_umove']}, {dr['implied_vmove']}); "
              f"declared {run_declared(r['name'])}")
        print(f"  DESCRIPTOR births (NOT a label)            : {bi['n_births']} "
              f"[censored {bi['n_censored']}, clause-(c) gated "
              f"{bi['reinitiations_gated_by_clause_c']}]  "
              f"-- controls: SC 2, PC 0-not-exercised")
        print(f"  descriptors: max updrafts {r['max_updrafts']}, max cells "
              f"{r['max_cells']}, peak w {r['peak_w']:.1f} m/s, cold pool "
              f"{r['max_cold_km2']:.0f} km2, min theta' {r['min_thpert']:.1f} K")

    print("\n" + "=" * 92)
    print("THE TREND ACROSS THE CONTROLLED SWEEP (thermodynamics fixed; only U_s varies)")
    print(f"{'run':<13}{'shear':>7}{'BRN':>7}{'WK82':>11}{'label':>13}{'P1':>6}"
          f"{'R':>7}{'E':>6}{'updr':>6}{'cells':>6}{'cold_km2':>10}{'births':>7}{'void':>6}")
    for r in rows:
        if r["name"] in CONTROLS:
            continue
        ev = r["ev"]
        print(f"{r['name']:<13}{SHEAR[r['name']]:>7}{BRN[r['name']]:>7}"
              f"{PREDICTED[r['name']]:>11}{r['label']:>13}"
              f"{ev.get('P1_chain_min', 0):>6g}"
              f"{_f(ev.get('median_R')):>7}{_f(ev.get('median_E')):>6}"
              f"{r['max_updrafts']:>6}{r['max_cells']:>6}{r['max_cold_km2']:>10.0f}"
              f"{r['births']['n_births']:>7}{('YES' if r['drift']['void'] else 'no'):>6}")
    print("\ncontrols, for scale (NOT normalisers -- criterion 1' takes no control ratio):")
    for r in rows:
        if r["name"] not in CONTROLS:
            continue
        ev = r["ev"]
        print(f"{r['name']:<13}{SHEAR[r['name']]:>7}{'-':>7}{'-':>11}{r['label']:>13}"
              f"{ev.get('P1_chain_min', 0):>6g}"
              f"{_f(ev.get('median_R')):>7}{_f(ev.get('median_E')):>6}"
              f"{r['max_updrafts']:>6}{r['max_cells']:>6}{r['max_cold_km2']:>10.0f}"
              f"{r['births']['n_births']:>7}{('YES' if r['drift']['void'] else 'no'):>6}")

    # Criterion 2' READ ON ITS OWN. This is not a new rule and not a new threshold:
    # it is `classify_v3`'s own crit2' block (T5 section 8, floors and bands
    # unchanged), evaluated without criterion 1' -- which the amendment pre-registered
    # as unable to speak when it sits at its ceiling. Printing it is the "read the
    # descriptor family" instruction made explicit rather than done by eye.
    print("\n" + "-" * 92)
    print("CRITERION 2' READ ALONE (T5 section 8 floors and bands, UNCHANGED), because")
    print("criterion 1' is at its ceiling for every sheared run and cannot discriminate:")
    for r in rows:
        ev = r["ev"]
        rm, em = ev.get("median_R"), ev.get("median_E")
        if rm is None:
            continue
        decisive_org = (rm >= C.R_FLOOR + C.R_BAND) or (em >= C.E_FLOOR * C.E_BAND_FACTOR)
        near = ((C.R_FLOOR - C.R_BAND <= rm < C.R_FLOOR + C.R_BAND)
                or (em is not None and C.E_FLOOR / C.E_BAND_FACTOR <= em < C.E_FLOOR * C.E_BAND_FACTOR))
        enough = ev.get("qualifying_frames", 0) >= C.MIN_QUALIFYING_FRAMES
        if decisive_org and enough:
            verdict = "MULTICELL signature (decisively organised)"
        elif near:
            verdict = "INDETERMINATE (inside the pre-registered band)"
        else:
            verdict = "no multicell signature"
        why = []
        if em is not None and em >= C.E_FLOOR * C.E_BAND_FACTOR:
            why.append(f"E={em:.3f} past the decisive edge {C.E_FLOOR * C.E_BAND_FACTOR:.2f}")
        if rm < C.R_FLOOR - C.R_BAND:
            why.append(f"R={rm:.3f} below the decisive edge {C.R_FLOOR - C.R_BAND:.2f}")
        print(f"  {r['name']:<14} {verdict}"
              + (f"   [{'; '.join(why)}]" if why else ""))

    at_ceiling = [r["name"] for r in rows if r["name"] in SWEEP
                  and r["ev"].get("P1_chain_min", 0) >= P1_CEILING_MIN]
    print(f"\nP1 at ceiling ({P1_CEILING_MIN:g} min): {len(at_ceiling)}/3 sweep members"
          f"{' -- ' + ', '.join(at_ceiling) if at_ceiling else ''}")
    if len(at_ceiling) == 3:
        print("=> PRE-REGISTERED OUTCOME: criterion 1' has NO DISCRIMINATING POWER on\n"
              "   this sweep, and criterion 2 is unavailable. The honest reading is\n"
              "   'NO DISCRIMINATOR', NOT 'three supercells'. Section 4.2's 500 m\n"
              "   contingency applies, and it is about resolution AND H3, not about\n"
              "   the environment. Read the descriptor TREND above, not the labels.")
    return 0


def _f(v):
    return "-" if v is None else f"{v:.3f}" if isinstance(v, float) else str(v)


def run_declared(name):
    import json
    try:
        with open(os.path.join(C.DEFAULT_RUNS, name, "scenario.json")) as f:
            n = json.load(f)["sim"]["namelist"]
        return f"({n.get('umove', 0)}, {n.get('vmove', 0)})"
    except (OSError, KeyError, ValueError):
        return "(?, ?)"


if __name__ == "__main__":
    sys.exit(main())
