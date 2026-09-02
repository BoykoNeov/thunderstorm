#!/usr/bin/env python3
"""Phase 3 T5s criterion 2 -- DISCRETE PROPAGATION, re-pre-registered 2026-09-02.

    python3 sim/probes/births_t5s.py --only sc,pc          # the controls
    python3 sim/probes/births_t5s.py --only us15,us20,us25 # the sweep (AFTER controls)

WK82's own multicell signature is that new cells are repeatedly born on the gust
front while old ones die -- discrete propagation. No T5 criterion measures it
(H3), which is why the plan added one. This module is that measurement, kept OUT
of `classify_t5.py` so T5's recorded numbers stay reproducible; it imports that
file's primitives rather than reinventing them, and reuses its pre-registered field
thresholds unchanged (`W_UPDRAFT` 10 m/s, `W_MIN_AREA_KM2` 4 km2, `LINK_KM` 7.5
km/frame, `MATURE_MIN` 40 min, `BOUNDARY_KM` 15 km).

WHY THE PLAN'S VERSION WAS REPLACED BEFORE IT WAS EVER SCORED
-------------------------------------------------------------
`docs/plan-science-hurdles-2026-09-02.md` section 4.2 pre-registered:

    "AFTER the first cell's updraft maximum decays below half its peak, a new
     |w| >= 10 m/s updraft component at 3-6 km appears >= 8 km from every existing
     component's centroid and persists >= 15 min -- a birth."

That leading clause was measured, on the six T5 runs already on disk, BEFORE any
sweep member was run or read:

    probe   global peak w            domain-peak half-decay after it
    SC      60.74 m/s at t=7200 s    NEVER FIRES        <- the supercell CONTROL
    A       52.88 m/s at t=7200 s    NEVER FIRES
    B       56.21 m/s at t=1500 s    NEVER FIRES
    C       46.72 m/s at t=5400 s    NEVER FIRES
    C2      48.41 m/s at t=3900 s    NEVER FIRES
    PC      61.60 m/s at t=1500 s    fires at t=3300 s

The trigger fires on ONE of six runs, and not on the supercell control. The reason
is structural, not incidental: the clause reads the DOMAIN-WIDE peak updraft, which
is a running maximum over whichever cell is currently strongest. It does not fall
when a cell dies -- in a supercell because one updraft sustains, and in a multicell
because the next cell is already up before the previous one's decay reaches the
domain maximum. So the birth count would have been structurally 0 for every sheared
run, and section 4.2's prediction "us20, us25 -> SUPERCELL by (2)" would have come
back CORRECT AND VACUOUS. That is T5's own twice-learned lesson (a control that
cannot fail measures nothing), caught this time before the runs instead of after.

Re-pre-registered here, in full, before any sweep member is scored:

    A BIRTH is an updraft component (3-6 km layer max of w >= W_UPDRAFT, area >=
    W_MIN_AREA_KM2) in frame i such that
      (a) it has NO predecessor within LINK_KM in frame i-1  -- it is not the
          continuation of an existing updraft that merely moved;
      (b) its centroid is >= BIRTH_SEP_KM from EVERY component in frame i-1
          -- the plan's 8 km, unchanged;
      (c) frame i-1 contains at least one component -- the first convection of the
          run is INITIATION, not propagation, and must not be counted;
      (d) it persists >= BIRTH_PERSIST_MIN by UNAMBIGUOUS forward linking at
          LINK_KM -- the plan's 15 min, unchanged; "unambiguous" and the censoring
          rule below are stated in full because clause (d) is where the first
          implementation got it wrong twice (see AMENDMENTS).
    MULTICELL by this criterion if births >= 3 over the run (the plan's threshold,
    unchanged: a supercell's split is ONE birth ~20 km away, so 3 sits above it,
    while a multicell regenerating every 20-30 min gives 3-5 in 2 h).

AMENDMENTS TO CLAUSE (d), 2026-09-02, BOTH BEFORE THE SWEEP AND BOTH THRESHOLD-FREE
------------------------------------------------------------------------------------
The first implementation of (d) scored SC at 3 births -- a control failure that would
have retired the criterion. Both of its extra births turned out to rest on defects in
(d) itself, not on the storm. Neither fix moves a threshold; both were argued from the
project's own record before the corrected numbers were seen.

  (d.1) RIGHT CENSORING. The run ends at t=120 min and both extra births were at
        t=105, where the maximum observable duration is exactly BIRTH_PERSIST_MIN.
        They "persisted 15.0 min" because the data ran out. Worse, a birth after
        t=105 can NEVER satisfy (d), so late births were being silently dropped. A
        birth in the final BIRTH_PERSIST_MIN is therefore UNSCORABLE -- not a pass,
        not a fail -- and is reported in `censored_births`, apart from the count.

  (d.2) NO GREEDY HOPPING. The forward walk chose the nearest of several candidates.
        That is the argmax tracker T4 section 5.2 retired, and `chain_stats`'s own
        docstring refuses it: "A LINKER, NOT A TRACKER ... it refuses to hop, and a
        broken chain IS the measurement." SC carries 3->5->7->9 components in its
        last four frames, so hopping is not hypothetical there. Two or more
        candidates within LINK_KM now END the chain: the continuation is not
        identifiable, so there is no track. `reach_min` reports the LENIENT reading
        (any candidate continues it) beside every birth, so the strict rule's cost
        is a number rather than an assumption.

What changed is ONLY the trigger clause, and it changed because it was measured
inoperable. Everything else -- 8 km, 15 min, 3 births, and every field threshold --
is the plan's, untouched. Clauses (a) and (c) together carry the meaning the deleted
clause was reaching for ("something new, where there was already something") without
depending on a statistic that never moves.

WHAT IS REPORTED BESIDE EVERY COUNT (so a 0 is never ambiguous)
---------------------------------------------------------------
  first_convection_min  when the run first has any component. A count of 0 with no
                        convection is a different fact from 0 with a storm running.
  max_link_step_km      the largest frame-to-frame displacement of any LINKED
                        component. The birth test assumes a real continuation is
                        within LINK_KM (7.5) and a birth is beyond BIRTH_SEP_KM (8).
                        Those brackets are only 0.5 km apart, so if this number
                        approaches 7.5 the separation is doing less work than it
                        looks -- it is REPORTED, every run, not assumed away.
  n_censored            births inside the right-censored tail (d.1) -- unscorable.
  reinitiations_gated_by_clause_c
                        frames whose predecessor had NO component. Clause (c) gates
                        every component in such a frame vacuously, so a count of 0
                        births with a NON-ZERO value here means the criterion was
                        never exercised on that run -- which is exactly what happens
                        to PC (its updrafts run ... 1 1 0 0 0 4 4 4 4 ..., so its
                        daughter ring is gated, not rejected). "PC scored 0" is
                        therefore NOT a validation of the single-cell side.
  void                  `classify_t5.drift_fit`'s section-5 rule: a run whose storm
                        came within BOUNDARY_KM of an OPEN wall in a mature frame is
                        NOT SCORABLE at any birth count. A multicell propagates on
                        its cold pool and can leave `umove` (a 0-6 km mean-wind,
                        i.e. SUPERCELL-motion, estimate) behind, so this is a live
                        hazard for the sweep, not a formality.

FRAME DEPENDENCE, STATED
------------------------
Positions are in the run's own grid frame. PC runs `imove=0` and the sweep members
run `imove=1`, so the two controls between them exercise both, and `max_link_step_km`
is the number that would expose a frame problem: a whole storm translating >= 8 km
per frame in its own grid would manufacture births. Reported, not assumed.
"""
import argparse
import glob
import os
import sys

import netCDF4
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify_t5 as C  # noqa: E402

# --- re-pre-registered constants, 2026-09-02 --------------------------------
# The plan's own numbers. Nothing here is new except the names.
BIRTH_SEP_KM = 8.0          # "appears >= 8 km from every existing component"
BIRTH_PERSIST_MIN = 15.0    # "and persists >= 15 min"
MIN_BIRTHS_MULTICELL = 3    # "multicell if births >= 3 in 2 h"
W_LAYER_KM = (3.0, 6.0)     # "a |w| >= 10 m/s updraft component at 3-6 km"


def updraft_nodes(path, periodic):
    """Updraft components in one frame, as {x_km, y_km, area_km2, peak}.

    The 3-6 km LAYER MAX the plan specifies -- not `classify_t5`'s column-max
    `n_updrafts`, which is a different (existing, untouched) statistic.
    """
    d = netCDF4.Dataset(path)
    zh = np.asarray(d.variables["zh"][:], float)          # km
    xh = np.asarray(d.variables["xh"][:], float)
    yh = np.asarray(d.variables["yh"][:], float)
    t_s = float(d.variables["time"][0])
    kk = np.where((zh >= W_LAYER_KM[0]) & (zh <= W_LAYER_KM[1]))[0]
    w = np.asarray(d.variables["winterp"][0, kk], float).max(axis=0)
    d.close()

    cell_km2 = abs(float(xh[1] - xh[0])) * abs(float(yh[1] - yh[0]))
    mask = w >= C.W_UPDRAFT
    nodes = []
    if mask.any():
        lab, n = C.label_periodic(mask, periodic)
        if n:
            idx = np.arange(1, n + 1)
            sizes = ndimage.sum(mask, lab, index=idx) * cell_km2
            for c in idx[sizes >= C.W_MIN_AREA_KM2]:
                jj, ii = np.nonzero(lab == c)
                nodes.append({
                    "x_km": C.wrapped_centroid(xh[ii], xh, periodic["x"]),
                    "y_km": C.wrapped_centroid(yh[jj], yh, periodic["y"]),
                    "area_km2": round(float(len(ii) * cell_km2), 2),
                    "peak": round(float(w[jj, ii].max()), 2),
                })
    return t_s / 60.0, nodes, xh, yh


def _sep(a, b, xh, yh, periodic):
    dx = C.wrap_delta(a["x_km"] - b["x_km"], C._period(xh), periodic["x"])
    dy = C.wrap_delta(a["y_km"] - b["y_km"], C._period(yh), periodic["y"])
    return float(np.hypot(dx, dy))


def births(name, runs=C.DEFAULT_RUNS):
    run_dir = os.path.join(runs, name)
    files = sorted(glob.glob(os.path.join(run_dir, "cm1out_0*.nc")))
    if not files:
        raise SystemExit(f"{name}: no cm1out_*.nc in {run_dir}")
    periodic = C.periodic_sides(run_dir)

    times, frames, xh, yh = [], [], None, None
    for f in files:
        t_min, nodes, xh, yh = updraft_nodes(f, periodic)
        times.append(t_min)
        frames.append(nodes)

    # the largest displacement of anything that DID link -- the reported safeguard
    max_step = 0.0
    for i in range(1, len(frames)):
        for c in frames[i]:
            near = [_sep(c, p, xh, yh, periodic) for p in frames[i - 1]]
            if near and min(near) <= C.LINK_KM:
                max_step = max(max_step, min(near))

    first_conv = next((t for t, ns in zip(times, frames) if ns), None)

    found, censored_out = [], []
    for i in range(1, len(frames)):
        if not frames[i - 1]:
            continue                                   # (c) initiation, not a birth
        for c in frames[i]:
            seps = [_sep(c, p, xh, yh, periodic) for p in frames[i - 1]]
            if min(seps) <= C.LINK_KM:
                continue                               # (a) a continuation
            if min(seps) < BIRTH_SEP_KM:
                continue                               # (b) not far enough
            # (d) forward persistence -- UNAMBIGUOUS linking only. Picking the
            # nearest of several candidates is the argmax tracker T4 section 5.2
            # retired and chain_stats's docstring refuses ("a broken chain IS the
            # measurement"); with SC carrying 3->5->7->9 components in its last four
            # frames, hopping is not hypothetical. Two or more candidates within
            # LINK_KM means the continuation is not identifiable, and the chain ends.
            # `reach_min` is the LENIENT reading (any candidate continues it),
            # reported so the strict rule's cost is visible rather than assumed.
            cur, j, end = c, i + 1, times[i]
            ambiguous_at = None
            while j < len(frames):
                nxt = [n for n in frames[j] if _sep(n, cur, xh, yh, periodic) <= C.LINK_KM]
                if not nxt:
                    break
                if len(nxt) > 1:
                    ambiguous_at = times[j]
                    break
                cur, end, j = nxt[0], times[j], j + 1
            dur = end - times[i]

            reach, jr = [c], i + 1
            while jr < len(frames):
                nxt = [n for n in frames[jr]
                       if any(_sep(n, r, xh, yh, periodic) <= C.LINK_KM for r in reach)]
                if not nxt:
                    break
                reach, jr = nxt, jr + 1
            reach_min = times[jr - 1] - times[i] if jr - 1 > i else 0.0

            # RIGHT CENSORING: a birth in the last BIRTH_PERSIST_MIN of the run
            # cannot be tested -- the most it can show is the time remaining. It is
            # not a pass and not a fail; it is unscorable, and is reported apart.
            censored = times[i] > times[-1] - BIRTH_PERSIST_MIN
            rec = {"t_min": round(times[i], 1),
                   "sep_km": round(min(seps), 2),
                   "persist_min": round(dur, 1),
                   "reach_min": round(reach_min, 1),
                   "ambiguous_at_min": None if ambiguous_at is None else round(ambiguous_at, 1),
                   "peak_ms": c["peak"],
                   "area_km2": c["area_km2"],
                   "x_km": round(c["x_km"], 1), "y_km": round(c["y_km"], 1),
                   "censored": censored}
            if censored:
                censored_out.append(rec)
            elif dur >= BIRTH_PERSIST_MIN:
                found.append(rec)

    mature_births = [b for b in found if b["t_min"] >= C.MATURE_MIN]
    # Clause (c) can be satisfied vacuously: if the frame before a re-initiation has
    # NO components, none of the new ones can be a birth however far apart they are.
    # That is how PC scores 0, so the count alone would misread as "the criterion was
    # exercised and passed". Report the gating explicitly.
    gated = sum(1 for i in range(1, len(frames)) if frames[i] and not frames[i - 1])
    return {
        "name": name,
        "n_frames": len(files),
        "t_end_min": round(times[-1], 1),
        "first_convection_min": None if first_conv is None else round(first_conv, 1),
        "max_link_step_km": round(max_step, 2),
        "births": found,
        "n_births": len(found),
        "n_births_mature": len(mature_births),
        "censored_births": censored_out,
        "n_censored": len(censored_out),
        "reinitiations_gated_by_clause_c": gated,
        "n_updrafts_per_frame": [len(ns) for ns in frames],
        "multicell_by_crit2": len(found) >= MIN_BIRTHS_MULTICELL,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", default=C.DEFAULT_RUNS)
    ap.add_argument("--only", default="sc,pc",
                    help="comma-separated suffixes: sc,pc,a,b,c,c2 or us15,us20,us25")
    ap.add_argument("--no-void-check", action="store_true",
                    help="skip the section-5 containment check (it re-reads every frame)")
    args = ap.parse_args()

    names = []
    for s in (x.strip() for x in args.only.split(",")):
        names.append(s if s.startswith("t5") else
                     (f"t5s_{s}" if s.startswith("us") or s.startswith("neutral")
                      else f"t5probe_{s}"))

    print(f"criterion 2 (discrete propagation), re-pre-registered 2026-09-02: "
          f"birth = new updraft >= {BIRTH_SEP_KM:g} km from every component in the "
          f"previous frame,\n  not a continuation (> LINK_KM={C.LINK_KM:g}), with "
          f"convection already present, persisting >= {BIRTH_PERSIST_MIN:g} min. "
          f"MULTICELL if births >= {MIN_BIRTHS_MULTICELL}.")
    print("=" * 78)

    rows = []
    for name in names:
        r = births(name, args.runs)
        void = None
        if not args.no_void_check:
            try:
                void = C.drift_fit(C.run_metrics(name, args.runs))
            except SystemExit:
                void = None
        r["void"] = bool(void and void["void"])
        r["void_why"] = void["void_why"] if void and void["void"] else None
        rows.append(r)

        print(f"\n=== {name} ===")
        print(f"  births                 {r['n_births']}  "
              f"(mature only, t>={C.MATURE_MIN:g} min: {r['n_births_mature']})")
        print(f"  first convection       t={r['first_convection_min']} min")
        print(f"  max linked step        {r['max_link_step_km']} km "
              f"(LINK_KM {C.LINK_KM:g}, birth separation {BIRTH_SEP_KM:g})")
        print(f"  updrafts per frame     "
              + " ".join(str(n) for n in r["n_updrafts_per_frame"]))
        print(f"  unscorable (censored)  {r['n_censored']}  "
              f"(born after t={r['t_end_min'] - BIRTH_PERSIST_MIN:g} min, so "
              f"{BIRTH_PERSIST_MIN:g} min of persistence cannot be observed)")
        print(f"  re-initiations gated   {r['reinitiations_gated_by_clause_c']}  "
              f"(frames whose predecessor had NO component -- clause (c) gates these "
              f"vacuously; 0 here means the criterion WAS exercised)")
        for b in r["births"] + r["censored_births"]:
            amb = ("" if b["ambiguous_at_min"] is None
                   else f", link ambiguous from t={b['ambiguous_at_min']}")
            tag = "CENSORED" if b["censored"] else "birth   "
            print(f"    {tag} t={b['t_min']:>6} min  {b['sep_km']:>5} km from the "
                  f"nearest existing updraft, persisted {b['persist_min']:>5} min "
                  f"(lenient reach {b['reach_min']:g}){amb}, "
                  f"peak {b['peak_ms']} m/s, area {b['area_km2']} km2")
        verdict = "MULTICELL by criterion 2" if r["multicell_by_crit2"] else \
                  "NOT multicell by criterion 2"
        if r["void"]:
            print(f"  !! VOID -- NOT SCORABLE: {r['void_why']}")
        else:
            print(f"  => {verdict}")

    print("\n" + "=" * 78)
    print(f"{'run':<18}{'births':>7}{'mature':>8}{'maxstep_km':>12}"
          f"{'first_conv':>12}  verdict")
    for r in rows:
        v = "VOID" if r["void"] else ("MULTICELL" if r["multicell_by_crit2"] else "not multicell")
        print(f"{r['name']:<18}{r['n_births']:>7}{r['n_births_mature']:>8}"
              f"{r['max_link_step_km']:>12}{str(r['first_convection_min']):>12}  {v}"
              f"   [censored {r['n_censored']}, clause-(c) gated "
              f"{r['reinitiations_gated_by_clause_c']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
