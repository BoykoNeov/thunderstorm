#!/usr/bin/env python3
"""Phase 3 T5s -- the PRE-REGISTERED neutrality gate (plan section 4.1).

    python3 sim/probes/gate_t5s_neutrality.py

Committed BEFORE the two control runs, with its thresholds already fixed in
`docs/plan-science-hurdles-2026-09-02.md` section 4.1. Nothing here is tuned after
seeing a residual; if a threshold has to move, that is a finding to record, not an
edit to make quietly.

WHAT IT COMPARES
----------------
`t5s_neutral_pc` / `t5s_neutral_a` supply the SAME environment as `t5probe_pc` /
`t5probe_a` through a different door: an external `input_sounding` file at isnd=7
instead of CM1's internal analytic sounding at isnd=5. If the door is what this
project believes it is, the base state CM1 builds is the same one.

Two separable claims, scored separately (the split is pre-registered):

  PLUMBING       CM1 read the file and honoured it. Tested against the FILE's own
                 values interpolated to CM1's levels exactly the way base.F does it
                 (RH-preserving, base.F:686-758). Contains no WK82 content at all.
  IMPLEMENTATION this project's WK82 equals CM1's WK82. Tested against the isnd=5
                 reference run. Two implementations of one paper.

A base-state breach runs the PLUMBING comparison before concluding isnd=7 is broken:
an innocuous formula difference must not stop T5s under a gate meant for the door.

RECOVERING THE REFERENCE BASE STATE (measured, not assumed)
-----------------------------------------------------------
The isnd=5 reference runs predate `output_basestate`, so `th0/qv0/prs0/u0/v0` are not
in their files. They are recovered from t=0 instead:

    th0 = th - thpert      qv0 = qv      prs0 = prs      u0 = uinterp   v0 = vinterp

Measured on both references at t=0: `thpert` is exactly 0 in the corner column, and
`th-thpert`, `qv` and `prs` are horizontally uniform to 0.000e+00 -- the warm bubble
(iinit=1, `maintain_rh=.false.`, init3d.F:450-466) perturbs potential temperature and
nothing else. The identity is not assumed: the T5s runs carry `output_basestate=1`, so
this script VERIFIES the recovery against CM1's own arrays on those runs first, and
only then applies it to the references. If the verification fails, the gate stops --
the comparison would be measuring the recovery, not the door.
"""
import os
import re
import sys

import netCDF4 as nc
import numpy as np

RUNS = "/home/boiko/thunderstorm/runs"

# CM1's constants, constants.F:110-117 (the default branch; testcase is 0 here).
G, RD, CP, RV, P00 = 9.81, 287.04, 1005.7, 461.5, 1.0e5
REPS = RV / RD

# Thresholds -- plan section 4.1, fixed before the runs.
TOL_THETA_K = 0.1
TOL_QV_GKG = 0.05
TOL_U_MS = 0.2
TOL_CAPE_FRAC = 0.10
TOL_W_FRAC = 0.05
TOL_WTIME_S = 300.0

_results = []


def check(name, ok, detail):
    _results.append(bool(ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}\n          {detail}")
    return ok


def rslf(p, t):
    """CM1's saturation mixing ratio, cm1libs.F:35-41 (Bolton 1980; the ptype=27
    branch is the `else`, identical to the ptype 1/2/3/5/6 one)."""
    esl = 611.2 * np.exp(17.67 * (t - 273.15) / (t - 29.65))
    esl = np.minimum(esl, 0.5 * p)
    return (RD / RV) * esl / (p - esl)


# --- the file, and base.F's own reading of it -------------------------------

def read_input_sounding(path):
    """Parse the file the way base.F:543-560 does, including its surface handling."""
    rows = [ln.split() for ln in open(path) if ln.strip()]
    p_sfc = float(rows[0][0]) * 100.0
    th_sfc = float(rows[0][1])
    qv_sfc = float(rows[0][2]) / 1000.0
    lev = np.array([[float(x) for x in r] for r in rows[1:]], float)
    n = len(lev) + 1
    z = np.zeros(n); th = np.zeros(n); qv = np.zeros(n)
    u = np.zeros(n); v = np.zeros(n)
    z[1:], th[1:], qv[1:] = lev[:, 0], lev[:, 1], lev[:, 2] / 1000.0
    u[1:], v[1:] = lev[:, 3], lev[:, 4]
    z[0], th[0], qv[0] = 0.0, th_sfc, qv_sfc
    # base.F:611-618 -- the header carries no wind, so the surface wind is
    # EXTRAPOLATED from levels 2 and 3, never read.
    u[0] = u[1] - (z[1] - z[0]) * (u[2] - u[1]) / (z[2] - z[1])
    v[0] = v[1] - (z[1] - z[0]) * (v[2] - v[1]) / (z[2] - z[1])
    return dict(z=z, th=th, qv=qv, u=u, v=v, p_sfc=p_sfc, th_sfc=th_sfc, qv_sfc=qv_sfc)


def basef_base_state(snd, zh_m):
    """Reproduce base.F's isnd=7 path: hydrostatic on the file's own levels, linear
    interpolation of th/qv/p/T/RH onto the model levels, qv rebuilt from interpolated
    RH, then pressure re-integrated hydrostatically (base.F:620-758)."""
    z, th, qv = snd["z"], snd["th"], snd["qv"]
    pi_sfc = (snd["p_sfc"] / P00) ** (RD / CP)
    thv_sfc = snd["th_sfc"] * (1.0 + snd["qv_sfc"] * REPS) / (1.0 + snd["qv_sfc"])

    thv = th * (1.0 + REPS * qv) / (1.0 + qv)
    pi = np.zeros_like(z); pi[0] = pi_sfc
    for k in range(1, len(z)):
        pi[k] = pi[k - 1] - G * (z[k] - z[k - 1]) / (CP * 0.5 * (thv[k] + thv[k - 1]))
    psnd = P00 * pi ** (CP / RD)
    tsnd = th * pi
    rhsnd = qv / rslf(psnd, tsnd)

    def interp(a):
        return np.interp(zh_m, z, a)

    th0 = interp(th)
    p_lin = interp(psnd)
    t_lin = interp(tsnd)
    rh0 = interp(rhsnd)
    u0 = interp(snd["u"])
    v0 = interp(snd["v"])
    # base.F rebuilds qv from the INTERPOLATED pressure/temperature, then replaces
    # the pressure by a hydrostatic integration and does NOT revisit qv.
    qv0 = rh0 * rslf(p_lin, t_lin)
    thv0 = th0 * (1.0 + REPS * qv0) / (1.0 + qv0)
    pi0 = np.zeros_like(zh_m)
    pi0[0] = pi_sfc - G * zh_m[0] / (CP * 0.5 * (thv_sfc + thv0[0]))
    for k in range(1, len(zh_m)):
        pi0[k] = pi0[k - 1] - G * (zh_m[k] - zh_m[k - 1]) / (CP * 0.5 * (thv0[k] + thv0[k - 1]))
    prs0 = P00 * pi0 ** (CP / RD)
    return dict(th0=th0, qv0=qv0, prs0=prs0, u0=u0, v0=v0)


# --- the runs ---------------------------------------------------------------

def frame0(run):
    return nc.Dataset(os.path.join(RUNS, run, "cm1out_000001.nc"))


def base_state(run):
    """Base state at t=0 in the corner column, plus how it was obtained."""
    d = frame0(run)
    V = d.variables
    zh_m = np.asarray(V["zh"][:], float) * 1000.0   # netCDF zh is in km
    rec = dict(
        zh_m=zh_m,
        th0=np.asarray(V["th"][0, :, 0, 0] - V["thpert"][0, :, 0, 0], float),
        qv0=np.asarray(V["qv"][0, :, 0, 0], float),
        prs0=np.asarray(V["prs"][0, :, 0, 0], float),
        u0=np.asarray(V["uinterp"][0, :, 0, 0], float),
        v0=np.asarray(V["vinterp"][0, :, 0, 0], float),
        cape=float(V["cape"][0, 0, 0]), cin=float(V["cin"][0, 0, 0]),
        direct=None,
    )
    if "th0" in V:   # output_basestate=1 -- CM1's own arrays, for verifying the above
        rec["direct"] = dict(
            th0=np.asarray(V["th0"][0, :, 0, 0], float),
            qv0=np.asarray(V["qv0"][0, :, 0, 0], float),
            prs0=np.asarray(V["prs0"][0, :, 0, 0], float),
            u0=np.asarray(V["u0"][0, :, 0, 0], float),
            v0=np.asarray(V["v0"][0, :, 0, 0], float),
        )
    return rec


def umove_of(run):
    """The domain speed CM1 subtracted from u0/v0 (base.F:2661-2668)."""
    txt = open(os.path.join(RUNS, run, "namelist.input")).read()
    out = {}
    for key in ("umove", "vmove"):
        for ln in txt.splitlines():
            s = ln.strip()
            if s.startswith(key) and "=" in s:
                out[key] = float(s.split("=", 1)[1].strip().rstrip(","))
                break
    return out.get("umove", 0.0), out.get("vmove", 0.0)


# CM1 writes one numbered file per output time PLUS a `cm1out_stats.nc` domain-
# statistics file, which carries none of the 3D fields. Match the numbered frames only.
FRAME_RE = re.compile(r"^cm1out_\d{6}\.nc$")


def peak_w(run):
    """(peak updraft over the run, its time in s) from winterp."""
    best, best_t = -1e30, None
    for f in sorted(os.listdir(os.path.join(RUNS, run))):
        if not FRAME_RE.match(f):
            continue
        d = nc.Dataset(os.path.join(RUNS, run, f))
        w = float(np.asarray(d.variables["winterp"][0]).max())
        t = float(d.variables["time"][0])
        if w > best:
            best, best_t = w, t
        d.close()
    return best, best_t


# --- the gate ---------------------------------------------------------------

def verify_recovery(run, rec):
    """The T5s runs carry output_basestate=1: prove the recovery identity used on the
    references reproduces CM1's own arrays before trusting it."""
    if rec["direct"] is None:
        return check(f"{run}: recovery identity verifiable (output_basestate=1)", False,
                     "output_basestate is NOT in this run -- the reference recovery "
                     "cannot be verified, so the comparison is not made")
    d = rec["direct"]
    worst = {k: float(np.abs(rec[k] - d[k]).max()) for k in ("th0", "qv0", "prs0", "u0", "v0")}
    ok = worst["th0"] < 1e-4 and worst["qv0"] < 1e-8 and worst["prs0"] < 1e-1 \
        and worst["u0"] < 1e-4 and worst["v0"] < 1e-4
    return check(f"{run}: th-thpert / qv / prs / uinterp at t=0 ARE CM1's own base state",
                 ok, "max |diff| " + ", ".join(f"{k} {v:.3e}" for k, v in worst.items())
                 + "  (this is what licenses recovering the isnd=5 references the same way)")


def compare(label, a, b, keys, note=""):
    lines, ok = [], True
    for k, tol, scale, unit in keys:
        diff = float(np.abs(a[k] - b[k]).max()) * scale
        ok &= diff < tol
        lines.append(f"max |d{k}| {diff:.4g} {unit} (tol {tol:g})")
    return check(label, ok, "; ".join(lines) + (("  " + note) if note else ""))


def main():
    print(__doc__.split("\n")[0])
    print("=" * 70)
    missing = [r for r in ("t5s_neutral_pc", "t5s_neutral_a")
               if not os.path.isfile(os.path.join(RUNS, r, "cm1out_000001.nc"))]
    if missing:
        print(f"  runs not present yet: {', '.join(missing)}")
        print("  run them first:  bash sim/probes/run_probe.sh "
              "sim/probes/configs/<name>.json 4")
        return 2

    for new, ref in (("t5s_neutral_pc", "t5probe_pc"), ("t5s_neutral_a", "t5probe_a")):
        print(f"\n=== {new}  vs  {ref} ===")
        rnew, rref = base_state(new), base_state(ref)
        if not verify_recovery(new, rnew):
            print("  recovery unverified -- stopping before the comparison")
            return 1

        # --- PLUMBING: CM1's base state vs the FILE, interpolated base.F's way ---
        snd = read_input_sounding(os.path.join(RUNS, new, "input_sounding"))
        fil = basef_base_state(snd, rnew["zh_m"])
        um, vm = umove_of(new)
        fil["u0"] = fil["u0"] - um     # CM1 stores u0 grid-relative
        fil["v0"] = fil["v0"] - vm
        compare(f"PLUMBING -- {new} base state IS the file it was given",
                rnew, fil,
                [("th0", TOL_THETA_K, 1.0, "K"), ("qv0", TOL_QV_GKG, 1000.0, "g/kg"),
                 ("u0", TOL_U_MS, 1.0, "m/s"), ("v0", TOL_U_MS, 1.0, "m/s")],
                "no WK82 content: file -> base.F interpolation -> CM1")

        # --- IMPLEMENTATION: this project's WK82 vs CM1's, through the two doors ---
        if new.endswith("_pc"):
            compare(f"IMPLEMENTATION -- {new} thermodynamics == {ref}'s",
                    rnew, rref,
                    [("th0", TOL_THETA_K, 1.0, "K"), ("qv0", TOL_QV_GKG, 1000.0, "g/kg")],
                    "isnd=7 file vs isnd=5 analytic")
        else:
            compare(f"IMPLEMENTATION -- {new} wind == {ref}'s at every level",
                    rnew, rref,
                    [("u0", TOL_U_MS, 1.0, "m/s"), ("v0", TOL_U_MS, 1.0, "m/s")],
                    "settles nothing about iwnd (the source did); confirms it")
            check(f"{new}: winds are NOT zero (iwnd=0 did not zero the profile)",
                  float(np.abs(rnew["u0"]).max()) > 1.0,
                  f"max |u0| {float(np.abs(rnew['u0']).max()):.2f} m/s, "
                  f"max |v0| {float(np.abs(rnew['v0']).max()):.3f} m/s")

        # --- CM1's own CAPE/CIN, banked at no extra cost ---
        dc = abs(rnew["cape"] - rref["cape"]) / max(rref["cape"], 1.0)
        check(f"{new}: CM1's t=0 CAPE matches {ref}'s", dc < TOL_CAPE_FRAC,
              f"CAPE {rnew['cape']:.1f} vs {rref['cape']:.1f} J/kg ({dc * 100:.2f} %); "
              f"CIN {rnew['cin']:.1f} vs {rref['cin']:.1f} J/kg "
              "(CM1 reports CIN as a positive magnitude)")

        # --- the storm itself ---
        wn, tn = peak_w(new)
        wr, tr = peak_w(ref)
        dw = abs(wn - wr) / max(wr, 1e-6)
        check(f"{new}: same storm as {ref} (peak updraft and its time)",
              dw < TOL_W_FRAC and abs(tn - tr) <= TOL_WTIME_S,
              f"peak w {wn:.2f} vs {wr:.2f} m/s ({dw * 100:.2f} %, tol {TOL_W_FRAC * 100:.0f} %); "
              f"at t={tn:.0f} vs {tr:.0f} s (tol {TOL_WTIME_S:.0f} s)")

    print("\n" + "=" * 70)
    ok, bad = _results.count(True), _results.count(False)
    print(f"{ok} passed, {bad} failed")
    if bad:
        print("\nA base-state FAIL on PLUMBING means isnd=7 is not what the plan believes\n"
              "and T5s stops. A FAIL on IMPLEMENTATION only, with PLUMBING passing, means\n"
              "the two WK82s differ -- a finding to record and size, not a broken door.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
