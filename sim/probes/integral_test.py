#!/usr/bin/env python3
"""Phase 3 T5s section 5.5 -- the COPY-BLIND instrument for the capped control.

    python3 sim/probes/integral_test.py

Section 5.4 voided section 5.2's secondary singleness criterion: the capped control's
configuration is exactly four-fold symmetric (irandp=0, a centred bubble, a square
domain), so every feature appears as 4 copies (on an axis or a diagonal) or 8 (generic)
and `n_updrafts` counts copies. The copy factor is PER FEATURE, so the counts are not
even inflated by a common factor.

An INTEGRAL has no such problem. Under exact four-fold symmetry a whole-domain integral
is exactly 4x a one-quadrant integral whatever the features are and wherever they sit,
so the factor is a uniform 4 in the capped and uncapped runs alike and a DIRECTION-ONLY
comparison of integrated quantities is valid under the symmetry -- on the data already
on disk, with no new compute. That is what section 5.4's gate asked for: an instrument
that does not count copies.

PRE-REGISTERED in docs/plan-science-hurdles-2026-09-02.md section 5.5, committed
(f913be4) BEFORE this file existed, including the disclosure that the design postdates
reading section 5.3's per-frame counts, and including all three outcomes with the one
that reflects badly on the cap written first.

Nothing here is new physics. The object set is classify_t5.py's own -- column-max w >=
W_UPDRAFT, 8-connectivity, per-component floor W_MIN_AREA_KM2 -- imported rather than
restated, so this measures the same objects the criterion counted. Only the REDUCTION
changes, from a count to two integrals:

    A   total updraft area                       km^2
    F   the same area weighted by column-max w   m/s km^2

The primary/secondary split is topological, not metric: the primary is the updraft
component connected to the domain centre (the bubble is centred; zero shear, so it does
not translate), and secondary is everything else. No radius is chosen, so no radius can
be tuned. Split-free totals are reported alongside and the verdict must survive both.
"""
import os
import sys
import glob

import numpy as np
import netCDF4
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import classify_t5 as C          # noqa: E402
import ring_test as R            # noqa: E402

BASE = "/home/boiko/thunderstorm/runs"
REFERENCE = "t5s_neutral_pc"
MEMBERS = ["t5s_capped_dt3", "t5s_capped_dt6"]

# Section 5.2's own window, unchanged: T5 section 7.5's onset time.
T_SECONDARY_MIN = 70.0

# Section 5.3's three named frames -- gate 3 reads the instrument against ring_test there.
GATE3_FRAMES = {"t5s_neutral_pc": 120.0, "t5s_capped_dt3": 105.0, "t5s_capped_dt6": 95.0}

ANNULUS_KM = 5.0

OUT = os.path.join(BASE, "t5s_capped_clean", "INTEGRAL_TEST.txt")

_lines = []


def say(s=""):
    print(s)
    _lines.append(s)


def frames(run_dir):
    """(path, t_minutes) for every output frame, in time order."""
    out = []
    for f in sorted(glob.glob(os.path.join(run_dir, "cm1out_0*.nc"))):
        try:
            d = netCDF4.Dataset(f)
            t = float(d.variables["time"][0])
            d.close()
        except Exception as e:                     # a raced/truncated frame must be
            say(f"  !! unreadable frame {os.path.basename(f)}: {e}")
            continue
        out.append((f, t / 60.0))
    out.sort(key=lambda p: p[1])
    return out


def measure(path):
    """Every number this instrument reads from one frame."""
    d = netCDF4.Dataset(path)
    xh = np.asarray(d.variables["xh"][:], dtype=float)      # km
    yh = np.asarray(d.variables["yh"][:], dtype=float)
    w = np.asarray(d.variables["winterp"][0], dtype=float)  # (z, y, x)
    d.close()

    ny, nx = len(yh), len(xh)
    cell_km2 = float((xh[1] - xh[0]) * (yh[1] - yh[0]))

    # -- gate 1: symmetry measured, not assumed ------------------------------------
    # The centre falls BETWEEN cells (0.5000 cells, verified in section 5.5), so a
    # mirror is a plain axis reversal.
    scale = float(np.abs(w).max()) or 1.0
    res_x = float(np.abs(w - w[:, :, ::-1]).max())
    res_y = float(np.abs(w - w[:, ::-1, :]).max())
    res_t = float(np.abs(w - np.swapaxes(w, 1, 2)).max())

    colmax = w.max(axis=0)
    mask = colmax >= C.W_UPDRAFT

    # -- gate 2: quadrant identity on the UNFLOORED integrals ----------------------
    # The per-component area floor is deliberately NOT applied here: a component
    # straddling an axis is split between quadrants, and its piece can fall under the
    # floor, so a floored integral is not quadrant-additive by construction. The
    # copy-stability claim is about the integral, and that is what is tested.
    a_full = float(mask.sum()) * cell_km2
    f_full = float(colmax[mask].sum()) * cell_km2 if mask.any() else 0.0
    qy, qx = ny // 2, nx // 2
    q = mask[:qy, :qx]
    a_quad = float(q.sum()) * cell_km2
    f_quad = float(colmax[:qy, :qx][q].sum()) * cell_km2 if q.any() else 0.0

    # -- the objects section 5.2 counted, and the topological split ----------------
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    # The four cells nearest the centre: with an even nx and the centre between cells,
    # that is the 2x2 block at (ny/2-1, ny/2) x (nx/2-1, nx/2).
    centre_labels = set(int(v) for v in lab[qy - 1:qy + 1, qx - 1:qx + 1].ravel() if v)

    a_tot = f_tot = a_pri = f_pri = a_sec = f_sec = 0.0
    n_kept = 0
    comps = []
    for c in range(1, n + 1):
        sel = lab == c
        area = float(sel.sum()) * cell_km2
        if area < C.W_MIN_AREA_KM2:
            continue
        flux = float(colmax[sel].sum()) * cell_km2
        n_kept += 1
        a_tot += area
        f_tot += flux
        if c in centre_labels:
            a_pri += area
            f_pri += flux
        else:
            a_sec += area
            f_sec += flux
        jj, ii = np.nonzero(sel)
        comps.append((float(np.hypot(xh[ii].mean(), yh[jj].mean())), area))

    # -- radial profile of the FLOORED mask (5 km annuli, out to the corner) -------
    kept = np.zeros_like(mask)
    for c in range(1, n + 1):
        sel = lab == c
        if float(sel.sum()) * cell_km2 >= C.W_MIN_AREA_KM2:
            kept |= sel
    yy, xx = np.meshgrid(yh, xh, indexing="ij")
    rr = np.hypot(xx, yy)
    r_max = float(rr.max())
    edges = np.arange(0.0, r_max + ANNULUS_KM, ANNULUS_KM)
    prof, _ = np.histogram(rr[kept], bins=edges)
    prof = prof.astype(float) * cell_km2

    # -- POST-HOC, NOT pre-registered: the same integrals restricted to the
    # geometrically complete interior (r <= the inscribed radius = the domain
    # half-width). Section 5.4(c) noted dt6 components at 81-103 km on an 89.4 km
    # half-width; this says whether the verdict depends on that material. Labelled
    # post-hoc wherever it is reported, and it cannot create a verdict -- only
    # weaken confidence in one, by disagreeing.
    r_in = float(min(abs(xh[0]), abs(xh[-1]), abs(yh[0]), abs(yh[-1])))
    inside = kept & (rr <= r_in)
    a_in = float(inside.sum()) * cell_km2
    f_in = float(colmax[inside].sum()) * cell_km2 if inside.any() else 0.0

    return {
        "res_x": res_x, "res_y": res_y, "res_t": res_t, "scale": scale,
        "a_full": a_full, "f_full": f_full, "a_quad": a_quad, "f_quad": f_quad,
        "a_tot": a_tot, "f_tot": f_tot,
        "a_pri": a_pri, "f_pri": f_pri, "a_sec": a_sec, "f_sec": f_sec,
        "n_kept": n_kept, "has_primary": bool(centre_labels),
        "prof": prof, "edges": edges, "comps": comps,
        "a_in": a_in, "f_in": f_in, "r_in": r_in,
    }


def run_series(name):
    run_dir = os.path.join(BASE, name)
    out = []
    for path, t in frames(run_dir):
        m = measure(path)
        m["t"] = t
        m["path"] = path
        out.append(m)
    return out


def main():
    series = {}
    for name in [REFERENCE] + MEMBERS:
        say(f"reading {name} ...")
        series[name] = run_series(name)
        say(f"  {len(series[name])} frames")
    say()

    # ---------------------------------------------------------------- gate 1
    say("=" * 78)
    say("GATE 1 -- symmetry measured, not assumed (max |w - mirror(w)|, all frames)")
    say("=" * 78)
    g1_exact = True
    for name in series:
        rx = max(m["res_x"] for m in series[name])
        ry = max(m["res_y"] for m in series[name])
        rt = max(m["res_t"] for m in series[name])
        sc = max(m["scale"] for m in series[name])
        say(f"  {name:18s} x-flip {rx:.3e}  y-flip {ry:.3e}  transpose {rt:.3e}"
            f"   (peak |w| {sc:.2f} m/s)")
        if max(rx, ry, rt) > 0.0:
            g1_exact = False
    say(f"  => four-fold symmetry is {'EXACT (bitwise)' if g1_exact else 'approximate'};"
        f" the integrals are valid either way, this quantifies section 5.4(b).")
    say()

    # ---------------------------------------------------------------- gate 2
    say("=" * 78)
    say("GATE 2 -- quadrant identity: whole domain == 4 x one quadrant (unfloored)")
    say("=" * 78)
    g2 = True
    for name in series:
        da = max(abs(m["a_full"] - 4.0 * m["a_quad"]) for m in series[name])
        df = max(abs(m["f_full"] - 4.0 * m["f_quad"]) for m in series[name])
        ref = max(m["f_full"] for m in series[name]) or 1.0
        ok = da == 0.0 and df <= 1e-9 * ref
        g2 &= ok
        say(f"  {name:18s} max |A - 4A_q| {da:.3e} km2   max |F - 4F_q| {df:.3e}"
            f"   {'OK' if ok else 'FAIL'}")
    say(f"  => copy-stability of the reduction: {'CONFIRMED' if g2 else 'FAILED'}")
    say()

    # ---------------------------------------------------------------- gate 3
    say("=" * 78)
    say("GATE 3 -- same objects as section 5.2 (instrument total area vs ring_test)")
    say("=" * 78)
    g3 = True
    for name, t_target in GATE3_FRAMES.items():
        m = min(series[name], key=lambda m: abs(m["t"] - t_target))
        rc, _ = R.components(m["path"])
        ring_area = sum(c["area_km2"] for c in rc)
        ok = abs(ring_area - m["a_tot"]) <= 1e-9 * max(ring_area, 1.0)
        g3 &= ok
        say(f"  {name:18s} t={m['t']:5.1f} min  ring_test {len(rc):3d} comps"
            f" {ring_area:9.2f} km2   instrument {m['n_kept']:3d} / {m['a_tot']:9.2f} km2"
            f"   {'OK' if ok else 'FAIL'}")
    say(f"  => {'CONFIRMED' if g3 else 'FAILED'}")
    say()

    if not (g2 and g3):
        say("!! An instrument gate FAILED. Per section 5.5 that voids this run of the")
        say("!! instrument, NOT the cap. No numbers below are read.")
        write_out()
        return 1

    # ---------------------------------------------------------------- per-frame
    say("=" * 78)
    say("PER-FRAME totals -- A = updraft area km2, F = w-weighted area m/s km2")
    say("  pri = component connected to the domain centre; sec = everything else")
    say("=" * 78)
    say(f"  {'t min':>6}  " + "  ".join(f"{n:>34s}" for n in [REFERENCE] + MEMBERS))
    say(f"  {'':>6}  " + "  ".join(
        f"{'A_tot':>8} {'A_sec':>8} {'F_sec':>9} {'np':>5}" for _ in series))
    ts = sorted({round(m["t"], 3) for m in series[REFERENCE]})
    for t in ts:
        row = f"  {t:6.1f}  "
        cells = []
        for name in [REFERENCE] + MEMBERS:
            hit = [m for m in series[name] if abs(m["t"] - t) < 1e-6]
            if not hit:
                cells.append(f"{'-':>8} {'-':>8} {'-':>9} {'-':>5}")
                continue
            m = hit[0]
            cells.append(f"{m['a_tot']:8.1f} {m['a_sec']:8.1f} {m['f_sec']:9.1f}"
                         f" {('yes' if m['has_primary'] else 'no'):>5}")
        say(row + "  ".join(cells))
    say()

    # ---------------------------------------------------------------- headline
    say("=" * 78)
    say(f"HEADLINE -- time-integrated over the section 5.2 window t > {T_SECONDARY_MIN:.0f} min")
    say("=" * 78)

    def window_sum(name, key):
        return sum(m[key] for m in series[name] if m["t"] > T_SECONDARY_MIN)

    ref_a_sec = window_sum(REFERENCE, "a_sec")
    ref_f_sec = window_sum(REFERENCE, "f_sec")
    ref_a_tot = window_sum(REFERENCE, "a_tot")
    ref_f_tot = window_sum(REFERENCE, "f_tot")
    nwin = len([m for m in series[REFERENCE] if m["t"] > T_SECONDARY_MIN])
    say(f"  window = {nwin} frames; reference sums: A_sec {ref_a_sec:.1f}  F_sec"
        f" {ref_f_sec:.1f}  A_tot {ref_a_tot:.1f}  F_tot {ref_f_tot:.1f}")
    say()

    verdicts = {}
    for name in MEMBERS:
        a_sec = window_sum(name, "a_sec")
        f_sec = window_sum(name, "f_sec")
        a_tot = window_sum(name, "a_tot")
        f_tot = window_sum(name, "f_tot")
        RA = a_sec / ref_a_sec if ref_a_sec else float("nan")
        RF = f_sec / ref_f_sec if ref_f_sec else float("nan")
        RA0 = a_tot / ref_a_tot if ref_a_tot else float("nan")
        RF0 = f_tot / ref_f_tot if ref_f_tot else float("nan")
        say(f"  {name}")
        say(f"     split   A_sec {a_sec:9.1f}  R_A = {RA:6.3f}"
            f"     F_sec {f_sec:9.1f}  R_F = {RF:6.3f}")
        say(f"     split-free  A_tot {a_tot:9.1f}  R_A0 = {RA0:6.3f}"
            f"  F_tot {f_tot:9.1f}  R_F0 = {RF0:6.3f}")
        if RA > 1.0 and RF > 1.0:
            v = "NOT SUPPRESSED (increased)"
        elif RA < 1.0 and RF < 1.0:
            v = "SUPPRESSED"
        else:
            v = "AMBIGUOUS (R_A and R_F disagree)"
        if v != "AMBIGUOUS (R_A and R_F disagree)":
            same = (RA0 > 1.0 and RF0 > 1.0) if RA > 1.0 else (RA0 < 1.0 and RF0 < 1.0)
            if not same:
                v = "AMBIGUOUS (split-free totals contradict the split ones)"
        verdicts[name] = v
        say(f"     => {v}")
        say()

    # ---------------------------------------------------------------- profiles
    say("=" * 78)
    say(f"RADIAL PROFILE -- updraft area km2 per {ANNULUS_KM:.0f} km annulus,"
        f" summed over the window")
    say("  reported unreduced; the inscribed radius is 89.41 km, the corner 126.44 km")
    say("=" * 78)
    edges = series[REFERENCE][0]["edges"]
    acc = {}
    for name in [REFERENCE] + MEMBERS:
        s = np.zeros(len(edges) - 1)
        for m in series[name]:
            if m["t"] > T_SECONDARY_MIN:
                s += m["prof"]
        acc[name] = s
    say(f"  {'r km':>12}  " + "  ".join(f"{n:>18s}" for n in [REFERENCE] + MEMBERS))
    for i in range(len(edges) - 1):
        if all(acc[n][i] == 0.0 for n in acc):
            continue
        lo, hi = edges[i], edges[i + 1]
        say(f"  {lo:5.0f}-{hi:5.0f}  " + "  ".join(f"{acc[n][i]:18.1f}" for n in acc))
    say()

    # ------------------------------------------------- post-hoc robustness check
    say("=" * 78)
    say("POST-HOC ROBUSTNESS -- NOT PRE-REGISTERED, cannot create a verdict")
    say(f"  the same window ratios with the mask restricted to r <= the inscribed")
    say(f"  radius {series[REFERENCE][0]['r_in']:.2f} km (the geometrically complete")
    say("  interior). Section 5.4(c) put dt6 components at 81-103 km on an 89.4 km")
    say("  half-width; this asks whether the verdict depends on that material.")
    say("=" * 78)
    ref_a_in = window_sum(REFERENCE, "a_in")
    ref_f_in = window_sum(REFERENCE, "f_in")
    for name in MEMBERS:
        ra = window_sum(name, "a_in") / ref_a_in if ref_a_in else float("nan")
        rf = window_sum(name, "f_in") / ref_f_in if ref_f_in else float("nan")
        agree = (ra > 1.0) == verdicts[name].startswith("NOT SUPPRESSED")
        say(f"  {name:18s} R_A(interior) = {ra:6.3f}   R_F(interior) = {rf:6.3f}"
            f"   {'agrees with the verdict' if agree else 'DISAGREES -- confidence down'}")
    say()

    say("=" * 78)
    for name in MEMBERS:
        say(f"VERDICT  {name:20s} {verdicts[name]}")
    say("=" * 78)
    write_out()
    return 0


def write_out():
    with open(OUT, "w") as fh:
        fh.write("\n".join(_lines) + "\n")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    sys.exit(main())
