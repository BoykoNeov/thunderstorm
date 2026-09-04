#!/usr/bin/env python3
"""Phase 3 T5s -- offline feasibility check for the CAPPED SINGLE-CELL CONTROL.

    python3 sim/probes/bubble_feasibility.py

Answers three questions that `docs/plan-science-hurdles-2026-09-02.md` section 5.1
does NOT, all BEFORE any compute is spent (section 5.2 pre-registers the run itself):

  1. Which `z_blend_m` reproduces section 5.1's CIN table?  The table records
     `z_cap_m` and `dtheta_k` only, and CIN depends on the blend depth -- so the
     table alone does not specify a runnable cap.
  2. How much CAPE does the cap actually cost, with no solver?  (Section 5.1 claims
     "within 2 J/kg"; this measures it.)
  3. **Does CM1's warm bubble still break the cap?**  Section 5.1's table is the CIN
     of an UNPERTURBED SURFACE parcel.  What has to initiate is a parcel carrying the
     bubble's theta excess -- and CM1's bubble (`iinit=1`, init3d.F:456-479) is
     centred at z = 1400 m with `bptpert` = 1.0 K, so its warm core sits ABOVE a
     600 m cap.  Those are different numbers and only the second predicts initiation.

`parcel_from` below is `sounding.parcel()` generalised to a source level and a theta
increment; it is GATED against the shipped `parcel(kind="sb")` at k0=0, dtheta=0
before it is used for anything, the same way every other tool in this directory is
checked against the thing it generalises.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pipeline"))

from cm1post import sounding as S  # noqa: E402

G, P00, KAPPA, EPS = S.G, S.P00, S.KAPPA, S.EPS

# --- CM1's warm bubble, iinit=1 (init3d.F:456-479) --------------------------
ZC, BVRAD, BPTPERT = 1400.0, 1400.0, 1.0

# CM1 scalar levels for the T5s probe deck (dz=500 m, stretch_z=0): zh = 250, 750, ...
CM1_ZH = np.arange(0.5, 40.0) * 500.0

# section 5.1's table, as published, for the z_blend identification
PLAN_TABLE = {(600, 2): -53, (600, 3): -60, (600, 4): -67, (600, 5): -74, (600, 6): -82,
              (700, 2): -49, (700, 3): -56, (700, 4): -63, (700, 5): -70, (700, 6): -78,
              (800, 2): -44, (800, 3): -51, (800, 4): -59, (800, 5): -66, (800, 6): -73,
              (900, 2): -39, (900, 3): -46, (900, 4): -53, (900, 5): -60, (900, 6): -68}

CANDIDATES = [("uncapped", None)] + [
    (f"z{zc}_dt{dt}", dict(z_cap_m=float(zc), dtheta_k=float(dt), z_blend_m=500.0))
    for zc, dt in [(600, 3), (600, 6), (700, 3), (700, 6), (800, 6), (900, 6)]]


def bubble_dtheta(z):
    """theta' on the bubble AXIS (x=ric, y=rjc), where beta reduces to its z term."""
    beta = np.abs(np.asarray(z, dtype=float) - ZC) / BVRAD
    return np.where(beta < 1.0, BPTPERT * np.cos(0.5 * math.pi * beta) ** 2, 0.0)


def parcel_from(prof, k0=0, dtheta_k=0.0, virtual_correction=True):
    """Pseudo-adiabatic ascent from source level `k0` with a theta increment.

    Identical to `sounding.parcel(kind="sb")` at k0=0, dtheta_k=0 -- gated below.
    Buoyancy is against the UNPERTURBED environment (the bubble is a local
    perturbation, not a new base state); CIN is the negative area from k0 to the LFC.
    """
    z, th_e, qv_e, p, T_e = prof.z, prof.theta, prof.qv, prof.p, prof.T
    th0 = float(th_e[k0]) + dtheta_k
    qv0 = float(qv_e[k0])
    p0 = float(p[k0])
    T0 = th0 * (p0 / P00) ** KAPPA
    tl = S.t_lcl(T0, qv0, p0)
    p_lcl = p0 * (tl / T0) ** (1.0 / KAPPA)
    the = S.theta_e(tl, qv0, p_lcl, tl)

    Tp = np.empty_like(T_e)
    qp = np.empty_like(qv_e)
    for k in range(len(z)):
        if p[k] >= p_lcl:
            Tp[k] = th0 * (p[k] / P00) ** KAPPA
            qp[k] = qv0
        else:
            Tp[k] = S._t_moist(the, float(p[k]))
            qp[k] = float(S.qvs(Tp[k], p[k]))
    if virtual_correction:
        tv_p = Tp * (1.0 + qp / EPS) / (1.0 + qp)
        tv_e = T_e * (1.0 + qv_e / EPS) / (1.0 + qv_e)
    else:
        tv_p, tv_e = Tp, T_e
    B = G * (tv_p - tv_e) / tv_e
    lcl_m = float(np.interp(-p_lcl, -p, z))
    pos = np.where((B > 0) & (z >= max(lcl_m, z[k0])))[0]
    if len(pos) == 0:
        return dict(cape=0.0, cin=S._area(z, np.minimum(B, 0.0), k0, len(z) - 1),
                    lcl=lcl_m, lfc=math.nan, el=math.nan)
    k_lfc, k_el = int(pos[0]), int(pos[-1])
    return dict(cape=S._area(z, np.maximum(B, 0.0), k_lfc, k_el),
                cin=S._area(z, np.minimum(B, 0.0), k0, k_lfc),
                lcl=lcl_m, lfc=float(z[k_lfc]), el=float(z[k_el]))


def gate():
    ref = S.build()
    a, b = S.parcel(ref, kind="sb"), parcel_from(ref)
    dc, dn = abs(a.cape_jkg - b["cape"]), abs(a.cin_jkg - b["cin"])
    print("=== GATE: parcel_from(k0=0, dtheta=0) == sounding.parcel('sb') ===")
    print(f"  CAPE {a.cape_jkg:9.4f} vs {b['cape']:9.4f}   d={dc:.3e}")
    print(f"  CIN  {a.cin_jkg:9.4f} vs {b['cin']:9.4f}   d={dn:.3e}")
    if dc > 1e-9 or dn > 1e-9:
        raise SystemExit("GATE FAILED -- the generalisation is not the shipped parcel")
    print("  PASS\n")
    return ref, a


def q1_identify_blend():
    print("=== Q1: which z_blend_m reproduces section 5.1's CIN table? ===")
    best = None
    for zb in (100.0, 200.0, 300.0, 400.0, 500.0):
        errs = []
        for (zc, dt), want in PLAN_TABLE.items():
            try:
                p = S.build(cap=dict(z_cap_m=float(zc), dtheta_k=float(dt), z_blend_m=zb))
                errs.append(abs(S.parcel(p, kind="sb").cin_jkg - want))
            except S.SoundingError:
                errs.append(float("nan"))
        e = np.array(errs)
        print(f"  z_blend={zb:6.0f} m   max|err| {np.nanmax(e):6.2f}   "
              f"mean|err| {np.nanmean(e):5.2f}  J/kg")
        if best is None or np.nanmax(e) < best[1]:
            best = (zb, float(np.nanmax(e)))
    print(f"  -> z_blend_m = {best[0]:.0f} m (max |err| {best[1]:.2f} J/kg = rounding)\n")
    return best[0]


def q2_q3(ref_sb):
    print("=== bubble theta' on CM1's own scalar levels (on axis) ===")
    for z in CM1_ZH[:6]:
        print(f"  zh={z:7.0f} m   theta' = {float(bubble_dtheta(z)):.3f} K")
    print()
    print("=== Q2 (CAPE hold, no solver) and Q3 (does the bubble break the cap?) ===")
    for name, cap in CANDIDATES:
        prof = S.build(cap=cap)
        sb = S.parcel(prof, kind="sb")
        grid = []
        for z in CM1_ZH:
            d = float(bubble_dtheta(z))
            if d <= 0.0:
                continue
            k = int(np.argmin(np.abs(prof.z - z)))
            r = parcel_from(prof, k0=k, dtheta_k=d)
            grid.append((z, d, r["cin"], r["cape"], r["lfc"]))
        gbest = max(grid, key=lambda r: r[2])   # least negative CIN = easiest parcel
        print(f"--- {name} ---")
        print(f"  environment (unperturbed SB): CAPE {sb.cape_jkg:7.1f}  "
              f"CIN {sb.cin_jkg:7.1f}   dCAPE vs uncapped "
              f"{ref_sb.cape_jkg - sb.cape_jkg:5.1f} J/kg")
        print(f"  bubble parcel, easiest CM1 level: z0={gbest[0]:6.0f} m  "
              f"theta'={gbest[1]:.3f} K  CIN {gbest[2]:7.2f}  CAPE {gbest[3]:7.1f}  "
              f"LFC {gbest[4]:.0f} m")
        print("    CIN per CM1 level: " + "  ".join(
            f"{z:.0f}m:{c:+.1f}" for z, _, c, _, _ in grid[:5]))
        print()


def main():
    ref, ref_sb = gate()
    print(f"uncapped reference: SB CAPE {ref_sb.cape_jkg:.1f}  CIN {ref_sb.cin_jkg:.1f}  "
          f"LFC {ref_sb.lfc_m:.0f} m  EL {ref_sb.el_m:.0f} m\n")
    q1_identify_blend()
    q2_q3(ref_sb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
