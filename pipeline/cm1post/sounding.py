"""Environmental sounding generation for CM1 `isnd=7` (external `input_sounding`).

WHY THIS MODULE EXISTS
----------------------
Two of the charter's open science tasks are the SAME task, and Phase 3 T5 hit the
wall that this module removes:

  * "CIN is a design task, not a config value" (charter; advisor item 7) -- the WK82
    analytic sounding has no independent CIN knob.
  * The T5 SHEAR GAP (docs/phase3-t5-multicell.md section 2.2) -- CM1's namelist
    reaches only three fixed wind profiles (0-6 km bulk shear 10 / 31.8 / 33.5 m/s),
    and the multicell<->supercell transition sits between the first two. T5 concluded
    that "only a source edit can reach" the gap and priced a second CM1 fork.

Both rest on the base state being COMPUTED INSIDE CM1 (`isnd=5`, `iwnd=N`), where
every parameter is a hardcoded Fortran local. Stock cm1r21.1 also reads the base
state from a text file: `isnd=7` reads `input_sounding` (WRF-style: a surface line
`p_sfc[hPa] theta[K] qv[g/kg]`, then `z[m] theta[K] qv[g/kg] u[m/s] v[m/s]` per
level) and takes the WIND from the same file. That moves the whole environment --
CAPE, CIN, shear magnitude, shear depth, hodograph shape -- into a generated text
file with NO change to the binary. The charter's "the namelist is CM1's sole
scenario input" becomes "the namelist plus one generated text file, both derived
from `sim/scenarios/<name>.json`", which is the same recovery path as before with
one more file whose sha256 `run_meta.txt` records.

    Verify-on-the-box before the first run (the CM1 source is not in this repo):
      1. base.F: `isnd.eq.7` reads `input_sounding` in the format above;
      2. base.F: with isnd=7 the wind comes from the file and `iwnd` is not applied
         on top (deck.py requires iwnd=0 at isnd=7 so the deck cannot LOOK like it
         declares shear it does not use; the neutrality gate below is the arbiter);
      3. the maximum number of file levels base.F accepts (this writer defaults to
         441 levels: 0-22 km at 50 m).
    Neutrality gate (docs/plan-science-hurdles-2026-09-02.md section 4): a scenario
    run at isnd=7 with THIS module's WK82 profile must reproduce the isnd=5 base
    state (th0/qv0/u0/v0 in cm1out) to interpolation accuracy. Not bitwise -- the
    file is interpolated by CM1 -- so the gate is a base-state comparison, and the
    storm-level check is the Phase 0 same-family test (split, peak w).

WHAT IS GENERATED, AND WHERE EACH PIECE COMES FROM
--------------------------------------------------
Thermodynamics: Weisman & Klemp (1982, MWR 110, 504-520), eqs. 1-2:
    theta(z) = theta_0 + (theta_tr - theta_0) (z/z_tr)^(5/4)          z <= z_tr
             = theta_tr exp[ g/(cp T_tr) (z - z_tr) ]                  z >  z_tr
    RH(z)    = 1 - 3/4 (z/z_tr)^(5/4)                                  z <= z_tr
             = 1/4                                                     z >  z_tr
    with qv capped at qv_pbl in the lowest levels -- WK82's CAPE knob (they used
    11-16 g/kg). Defaults theta_0=300 K, theta_tr=343 K, T_tr=213 K, z_tr=12 km,
    p_sfc=1000 hPa. Pressure comes from hydrostatic integration in Exner form using
    virtual potential temperature, which is how CM1 builds its own base state.

CIN knob -- capped mixed layer: a well-mixed layer (theta = theta_0) beneath a
    capping inversion of strength dtheta_k that relaxes linearly back onto the WK82
    profile over z_blend_m. The KNOB SEMANTICS (vary mixed-layer depth / cap while
    holding CAPE) follow McCaul & Cohen (2002, MWR 130, 1722-1748) and McCaul &
    Weisman (2001, MWR 129, 664-687); the piecewise construction is this module's
    own and is stated in full in `apply_cap` so it can be checked, not trusted. The
    cap edits theta ONLY; qv stays WK82's, so the cap layer becomes drier in RH terms
    (the physical direction). CAPE is HELD by solving qv_pbl for a target CAPE with
    the cap applied (`solve_qv_pbl_for_cape`) -- that is "dial CIN while holding
    CAPE" made literal.

Wind: `tanh` -- u = U_s tanh(z/z_s), WK82 section 2 (CM1's iwnd=4 is U_s=35, z_s=3 km);
      `linear` -- u = U_s min(z/z_s, 1), Rotunno, Klemp & Weisman (1988, JAS 45,
      463-485) with z_s=2.5 km (CM1's iwnd=1 is U_s=10); `none`. U_s and z_s are the
      knobs T5 could not reach. v is zero in all of them; a Galilean offset is a
      separate key because it changes the `umove` a scenario must declare.

Diagnostics (REPORTED, never fed back -- charter principle 1):
    * Surface-based and mixed-layer parcel CAPE / CIN / LCL / LFC / EL, pseudo-
      adiabatic, with the virtual-temperature correction of Doswell & Rasmussen
      (1994, WAF 9, 625-629). Saturated ascent conserves Bolton's (1980, MWR 108,
      1046-1053) pseudo-equivalent potential temperature (eq. 39); LCL temperature
      is Bolton eq. 15; saturation vapour pressure is Bolton eq. 10.
    * 0-6 km bulk shear, layer-mean wind (the `umove` estimate the T5 probes used),
      and the Bulk Richardson Number BRN = CAPE / (1/2 U^2) with U the difference
      between the density-weighted 0-6 km and 0-500 m mean winds (WK82 eq. 3;
      Moncrieff & Green 1972). WK82 section 5 / Weisman & Klemp (1984, MWR 112,
      2479-2498) place supercells at roughly 10 < BRN < 50 and multicells above ~50;
      `wk82_regime` returns that band as a PREDICTION about the environment, which
      is what a pre-registered probe falsifies. It is not a classifier of the run.
    * Precipitable water.

Every number here is a property of the ENVIRONMENT. Nothing in this module reads a
CM1 output file, and nothing it computes feeds back into the simulation.
"""
import math
from dataclasses import dataclass, field

import numpy as np

# --- constants (CM1 constants.F values, so the base state matches CM1's own) --
G = 9.81
RD = 287.04
RV = 461.5
CP = 1005.7
P00 = 1.0e5
EPS = RD / RV
KAPPA = RD / CP
T0C = 273.15
RHO_W = 1000.0
# numpy 1.26 (pipeline runtime) has trapz; numpy 2 renamed it. Both must work.
_trapz = getattr(np, "trapezoid", None) or np.trapz

# WK82 defaults (their section 2). qv_pbl 14 g/kg is the CAPE ~2200 J/kg member.
WK82_DEFAULTS = {
    "theta_sfc_k": 300.0,
    "theta_tr_k": 343.0,
    "t_tr_k": 213.0,
    "z_tr_m": 12000.0,
    "qv_pbl_gkg": 14.0,
    "p_sfc_hpa": 1000.0,
}
DEFAULT_Z_TOP_M = 22000.0     # must exceed the CM1 model top (19.75 km here)
# 50 m, not 100 m, and the reason is measured. The mixed layer ends where WK82's RH
# profile stops demanding more moisture than the qv_pbl clip allows -- an implicit KINK
# in RH(z) (at 1300 m for the 14 g/kg reference). CM1 reads the file, converts qv to RH,
# and interpolates RH LINEARLY onto its own levels (base.F:686-716), so a model level
# that straddles the kink gets a moisture error. Measured against the isnd=5 reference
# run's own base state, on CM1's 500 m levels: 100 m spacing -> 0.046 g/kg at z=1250 m,
# which is 92 % of the neutrality gate's 0.05 g/kg budget; 50 m -> 0.0048; 25 m ->
# 0.0048 (converged, so 50 m is where the interpolation stops being the limit). theta
# improves 0.0022 K -> 0.00007 K over the same change. base.F's level cap is 1 000 000,
# so 441 levels costs nothing.
DEFAULT_DZ_M = 50.0
RH_MAX = 0.995                # the base state is never allowed to be saturated. WK82's
                              # RH(z) -> 1 as z -> 0 whenever qv_pbl does not cap it,
                              # so the limit is 'not saturated', not 'comfortably dry'.

SOUNDING_KEYS = frozenset(
    list(WK82_DEFAULTS) + ["kind", "cap", "wind", "hold_cape_jkg", "z_top_m",
                           "dz_m", "_note"])
CAP_KEYS = frozenset(["z_cap_m", "dtheta_k", "z_blend_m", "mixed_below", "_note"])
WIND_KEYS = frozenset(["kind", "u_max_ms", "z_scale_m", "u_offset_ms",
                       "v_offset_ms", "_note"])


class SoundingError(Exception):
    """A sounding that would be wrong, unphysical, or silently not what was asked."""


# --- moist thermodynamics ----------------------------------------------------

def es_pa(T):
    """Saturation vapour pressure over water, Pa. Bolton (1980) eq. 10."""
    T = np.asarray(T, float)
    return 611.2 * np.exp(17.67 * (T - T0C) / (T - 29.65))


def qvs(T, p):
    """Saturation mixing ratio (kg/kg) at temperature T (K), pressure p (Pa)."""
    e = np.minimum(es_pa(T), 0.99 * np.asarray(p, float))
    return EPS * e / (p - e)


def theta_v(theta, qv):
    """Virtual potential temperature (exact form, not the 0.61 approximation)."""
    return theta * (1.0 + qv / EPS) / (1.0 + qv)


def t_lcl(T, qv, p):
    """LCL temperature of a parcel (Bolton 1980 eq. 15, via the dewpoint)."""
    e = qv * p / (EPS + qv)
    e = max(float(e), 1e-3)
    # invert Bolton eq. 10 for the dewpoint
    a = math.log(e / 611.2) / 17.67
    td = (29.65 * a - T0C) / (a - 1.0)
    td = min(td, T)
    return 1.0 / (1.0 / (td - 56.0) + math.log(T / td) / 800.0) + 56.0


def theta_e(T, qv, p, tl):
    """Pseudo-equivalent potential temperature, Bolton (1980) eq. 39. qv in kg/kg."""
    p_hpa = p / 100.0
    return (T * (1000.0 / p_hpa) ** (0.2854 * (1.0 - 0.28 * qv))
            * math.exp(qv * (1.0 + 0.81 * qv) * (3376.0 / tl - 2.54)))


def _t_moist(the, p, lo=150.0, hi=345.0):
    """Temperature on the pseudoadiabat theta_e=the at pressure p (bisection)."""
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if theta_e(mid, float(qvs(mid, p)), p, mid) > the:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


# --- analytic profiles --------------------------------------------------------

def wk82_theta(z, theta_sfc_k=300.0, theta_tr_k=343.0, t_tr_k=213.0, z_tr_m=12000.0):
    """WK82 eq. 1."""
    z = np.asarray(z, float)
    below = theta_sfc_k + (theta_tr_k - theta_sfc_k) * (z / z_tr_m) ** 1.25
    above = theta_tr_k * np.exp(G / (CP * t_tr_k) * (z - z_tr_m))
    return np.where(z <= z_tr_m, below, above)


def wk82_rh(z, z_tr_m=12000.0):
    """WK82 eq. 2."""
    z = np.asarray(z, float)
    return np.where(z <= z_tr_m, 1.0 - 0.75 * (z / z_tr_m) ** 1.25, 0.25)


def apply_cap(z, theta_ref, theta_sfc_k, z_cap_m, dtheta_k, z_blend_m, mixed_below=True):
    """The capped mixed layer, stated in full.

        z <= z_cap                : theta = theta_sfc            (if mixed_below)
                                    theta = theta_ref(z)         (otherwise)
        z_cap < z <= z_cap+z_blend: theta = theta_ref(z) + dtheta * (1 - (z-z_cap)/z_blend)
        z >  z_cap+z_blend        : theta = theta_ref(z)

    So the inversion is a jump of dtheta (plus whatever the mixed layer removed)
    right above z_cap, decaying linearly onto WK82 over z_blend. theta_ref is
    untouched above the blend, which is what keeps CAPE's upper-level share fixed.
    """
    z = np.asarray(z, float)
    if z_cap_m <= 0 or z_blend_m <= 0:
        raise SoundingError(
            f"cap needs z_cap_m > 0 and z_blend_m > 0 (got {z_cap_m}, {z_blend_m}); "
            "a zero-depth blend is a discontinuity CM1's interpolation would place "
            "wherever its own levels happen to fall.")
    if dtheta_k < 0:
        raise SoundingError(f"cap dtheta_k={dtheta_k} < 0 would be a superadiabatic "
                            "layer, not a cap.")
    th = np.array(theta_ref, float, copy=True)
    inside = (z > z_cap_m) & (z <= z_cap_m + z_blend_m)
    th[inside] = theta_ref[inside] + dtheta_k * (1.0 - (z[inside] - z_cap_m) / z_blend_m)
    if mixed_below:
        th[z <= z_cap_m] = theta_sfc_k
    return th


def wind_profile(z, kind="none", u_max_ms=0.0, z_scale_m=3000.0,
                 u_offset_ms=0.0, v_offset_ms=0.0):
    z = np.asarray(z, float)
    if kind == "none":
        u = np.zeros_like(z)
    elif kind == "tanh":
        u = u_max_ms * np.tanh(z / z_scale_m)
    elif kind == "linear":
        u = u_max_ms * np.minimum(z / z_scale_m, 1.0)
    else:
        raise SoundingError(f"unknown wind kind {kind!r} (none | tanh | linear)")
    if kind != "none" and z_scale_m <= 0:
        raise SoundingError(f"wind z_scale_m must be > 0, got {z_scale_m}")
    return u + u_offset_ms, np.zeros_like(z) + v_offset_ms


# --- hydrostatic base state --------------------------------------------------

def hydrostatic(z, theta, qv_rule, p_sfc_pa):
    """Integrate dpi/dz = -g/(cp theta_v) upward, level by level.

    qv_rule(k, T, p) -> qv at level k. qv and pressure are mutually dependent at
    each level (qv through RH*qvs(T,p), p through theta_v), so each level is fixed-
    point iterated -- 6 rounds is far past convergence for 100 m steps.
    """
    n = len(z)
    p = np.zeros(n)
    T = np.zeros(n)
    qv = np.zeros(n)
    pi = (p_sfc_pa / P00) ** KAPPA
    p[0] = p_sfc_pa
    T[0] = theta[0] * pi
    qv[0] = qv_rule(0, T[0], p[0])
    for _ in range(6):
        T[0] = theta[0] * pi
        qv[0] = qv_rule(0, T[0], p[0])
    for k in range(1, n):
        dz = z[k] - z[k - 1]
        qk = qv[k - 1]
        for _ in range(6):
            thv_mean = 0.5 * (theta_v(theta[k - 1], qv[k - 1]) + theta_v(theta[k], qk))
            pik = pi - G * dz / (CP * thv_mean)
            pk = P00 * pik ** (1.0 / KAPPA)
            Tk = theta[k] * pik
            qk = qv_rule(k, Tk, pk)
        pi, p[k], T[k], qv[k] = pik, pk, Tk, qk
    return p, T, qv


@dataclass(frozen=True)
class Profile:
    """One generated sounding, SI on a uniform z grid starting at z=0."""
    z: np.ndarray
    theta: np.ndarray
    qv: np.ndarray          # kg/kg
    u: np.ndarray
    v: np.ndarray
    p: np.ndarray           # Pa
    T: np.ndarray           # K
    params: dict = field(default_factory=dict)

    @property
    def rh(self):
        return self.qv / qvs(self.T, self.p)

    @property
    def rho(self):
        tv = self.T * (1.0 + self.qv / EPS) / (1.0 + self.qv)
        return self.p / (RD * tv)


def build(theta_sfc_k=300.0, theta_tr_k=343.0, t_tr_k=213.0, z_tr_m=12000.0,
          qv_pbl_gkg=14.0, p_sfc_hpa=1000.0, cap=None, wind=None,
          z_top_m=DEFAULT_Z_TOP_M, dz_m=DEFAULT_DZ_M):
    """Build a profile. `cap` and `wind` are dicts (see CAP_KEYS / WIND_KEYS)."""
    if z_top_m <= z_tr_m or dz_m <= 0:
        raise SoundingError(f"z_top_m={z_top_m} must exceed z_tr_m={z_tr_m}, dz_m>0")
    n = int(round(z_top_m / dz_m)) + 1
    z = np.arange(n) * dz_m
    qv_pbl = qv_pbl_gkg / 1000.0
    p_sfc = p_sfc_hpa * 100.0

    theta_ref = wk82_theta(z, theta_sfc_k, theta_tr_k, t_tr_k, z_tr_m)
    rh_ref = wk82_rh(z, z_tr_m)

    def qv_wk(k, T, p):
        return min(rh_ref[k] * float(qvs(T, p)), qv_pbl)

    p_ref, T_ref, qv_ref = hydrostatic(z, theta_ref, qv_wk, p_sfc)

    if cap:
        c = {k: v for k, v in cap.items() if not k.startswith("_")}
        unknown = set(c) - CAP_KEYS
        if unknown:
            raise SoundingError(f"cap: unrecognised key(s) {sorted(unknown)}")
        theta = apply_cap(z, theta_ref, theta_sfc_k, c["z_cap_m"], c["dtheta_k"],
                          c["z_blend_m"], c.get("mixed_below", True))

        def qv_capped(k, T, p):
            # qv is WK82's; only refuse (never clip silently) if the cooler mixed
            # layer would make that moisture saturate -- see the check below.
            return qv_ref[k]

        p, T, qv = hydrostatic(z, theta, qv_capped, p_sfc)
    else:
        theta, p, T, qv = theta_ref, p_ref, T_ref, qv_ref

    rh = qv / qvs(T, p)
    if np.any(rh > RH_MAX):
        k = int(np.argmax(rh))
        raise SoundingError(
            f"base state is SATURATED: RH={rh[k]:.3f} at z={z[k]:.0f} m (limit {RH_MAX}). "
            "A cooler mixed layer cannot hold WK82's moisture this deep: lower "
            "cap.z_cap_m, or lower qv_pbl_gkg / hold_cape_jkg. Refusing rather than "
            "clipping -- a silently drier layer is a different CAPE.")

    w = dict(wind or {"kind": "none"})
    w.pop("_note", None)
    unknown = set(w) - WIND_KEYS
    if unknown:
        raise SoundingError(f"wind: unrecognised key(s) {sorted(unknown)}")
    u, v = wind_profile(z, **w)

    params = dict(theta_sfc_k=theta_sfc_k, theta_tr_k=theta_tr_k, t_tr_k=t_tr_k,
                  z_tr_m=z_tr_m, qv_pbl_gkg=qv_pbl_gkg, p_sfc_hpa=p_sfc_hpa,
                  cap=dict(cap) if cap else None, wind=w, z_top_m=z_top_m, dz_m=dz_m)
    return Profile(z=z, theta=theta, qv=qv, u=u, v=v, p=p, T=T, params=params)


# --- parcel diagnostics ---------------------------------------------------

@dataclass(frozen=True)
class ParcelResult:
    kind: str
    cape_jkg: float
    cin_jkg: float
    lcl_m: float
    lfc_m: float          # nan if no LFC
    el_m: float           # nan if no EL
    virtual_correction: bool = True


def parcel(prof, kind="sb", ml_depth_m=500.0, virtual_correction=True):
    """Pseudo-adiabatic parcel ascent on the profile's own grid.

    kind: "sb" (surface-based) or "ml" (mixed-layer: mean theta/qv over the lowest
    ml_depth_m, lifted from the surface pressure). CIN is the negative area below
    the LFC; CAPE the positive area between LFC and EL (the highest positively
    buoyant level). With virtual_correction=False the buoyancy uses T instead of
    T_v -- kept only so a gate can prove the correction is applied.
    """
    z, th_e, qv_e, p, T_e = prof.z, prof.theta, prof.qv, prof.p, prof.T
    if kind == "sb":
        th0, qv0 = float(th_e[0]), float(qv_e[0])
    elif kind == "ml":
        m = z <= ml_depth_m
        th0, qv0 = float(th_e[m].mean()), float(qv_e[m].mean())
    else:
        raise SoundingError(f"parcel kind {kind!r} (sb | ml)")
    p0 = float(p[0])
    T0 = th0 * (p0 / P00) ** KAPPA
    tl = t_lcl(T0, qv0, p0)
    p_lcl = p0 * (tl / T0) ** (1.0 / KAPPA)
    the = theta_e(tl, qv0, p_lcl, tl)

    Tp = np.empty_like(T_e)
    qp = np.empty_like(qv_e)
    for k in range(len(z)):
        if p[k] >= p_lcl:
            Tp[k] = th0 * (p[k] / P00) ** KAPPA
            qp[k] = qv0
        else:
            Tp[k] = _t_moist(the, float(p[k]))
            qp[k] = float(qvs(Tp[k], p[k]))

    if virtual_correction:
        tv_p = Tp * (1.0 + qp / EPS) / (1.0 + qp)
        tv_e = T_e * (1.0 + qv_e / EPS) / (1.0 + qv_e)
    else:
        tv_p, tv_e = Tp, T_e
    B = G * (tv_p - tv_e) / tv_e

    # LCL height by interpolating pressure
    lcl_m = float(np.interp(-p_lcl, -p, z))
    above_lcl = z >= lcl_m
    pos = np.where((B > 0) & above_lcl)[0]
    if len(pos) == 0:
        cin = _area(z, np.minimum(B, 0.0), 0, len(z) - 1)
        return ParcelResult(kind, 0.0, cin, lcl_m, math.nan, math.nan, virtual_correction)
    k_lfc, k_el = int(pos[0]), int(pos[-1])
    cape = _area(z, np.maximum(B, 0.0), k_lfc, k_el)
    cin = _area(z, np.minimum(B, 0.0), 0, k_lfc)
    return ParcelResult(kind, cape, cin, lcl_m, float(z[k_lfc]), float(z[k_el]),
                        virtual_correction)


def _area(z, b, k0, k1):
    if k1 <= k0:
        return 0.0
    return float(_trapz(b[k0:k1 + 1], z[k0:k1 + 1]))


# --- wind diagnostics -------------------------------------------------------

def _interp(prof, arr, zq):
    return float(np.interp(zq, prof.z, arr))


def bulk_shear(prof, z_top_m=6000.0):
    du = _interp(prof, prof.u, z_top_m) - float(prof.u[0])
    dv = _interp(prof, prof.v, z_top_m) - float(prof.v[0])
    return math.hypot(du, dv)


def mean_wind(prof, z0_m=0.0, z1_m=6000.0, density_weighted=False):
    """Layer-mean (u, v). Unweighted is the umove estimate the T5 probes used."""
    m = (prof.z >= z0_m) & (prof.z <= z1_m)
    w = prof.rho[m] if density_weighted else np.ones(m.sum())
    return (float(np.average(prof.u[m], weights=w)),
            float(np.average(prof.v[m], weights=w)))


def brn(prof, cape_jkg):
    """Bulk Richardson Number, WK82 eq. 3 (density-weighted 0-6 km minus 0-500 m)."""
    u6, v6 = mean_wind(prof, 0.0, 6000.0, density_weighted=True)
    u0, v0 = mean_wind(prof, 0.0, 500.0, density_weighted=True)
    ushear2 = (u6 - u0) ** 2 + (v6 - v0) ** 2
    if ushear2 <= 0:
        return math.inf
    return cape_jkg / (0.5 * ushear2)


def wk82_regime(brn_value):
    """WK82 section 5 / WK84 bands, as a PREDICTION about the environment."""
    if brn_value < 10.0:
        return "shear-dominated (BRN < 10: updrafts sheared apart, no sustained storm)"
    if brn_value <= 50.0:
        return "supercell (10 <= BRN <= 50)"
    return "multicell (BRN > 50)"


def precipitable_water_mm(prof):
    return float(_trapz(prof.rho * prof.qv, prof.z)) / RHO_W * 1000.0


# --- holding CAPE while dialing CIN ----------------------------------------

def solve_qv_pbl_for_cape(target_jkg, tol_jkg=10.0, lo_gkg=2.0, hi_gkg=18.0,
                          parcel_kind="sb", **build_kwargs):
    """Bisect qv_pbl so the (capped) sounding's CAPE hits target_jkg.

    CAPE is monotone in qv_pbl (a gate checks this on the WK82 family), so the
    bracket is honest: if the target is not bracketed the caller is told, never
    handed the nearest endpoint. hi_gkg stays below surface saturation (qvs at
    300 K / 1000 hPa is ~22.7 g/kg; WK82 went no higher than 16, and 18 is where
    the uncapped RH(z)->1 formula starts to saturate the lowest levels, which
    build() refuses).
    """
    build_kwargs.pop("qv_pbl_gkg", None)

    def cape_at(q):
        return parcel(build(qv_pbl_gkg=q, **build_kwargs), kind=parcel_kind).cape_jkg

    c_lo, c_hi = cape_at(lo_gkg), cape_at(hi_gkg)
    if not (c_lo <= target_jkg <= c_hi):
        raise SoundingError(
            f"CAPE {target_jkg:.0f} J/kg is not bracketed by qv_pbl in "
            f"[{lo_gkg}, {hi_gkg}] g/kg (CAPE {c_lo:.0f}..{c_hi:.0f}).")
    lo, hi = lo_gkg, hi_gkg
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        c = cape_at(mid)
        if abs(c - target_jkg) <= tol_jkg:
            return mid
        if c < target_jkg:
            lo = mid
        else:
            hi = mid
    raise SoundingError(f"CAPE hold did not converge to {target_jkg} +/- {tol_jkg}")


# --- config <-> profile -------------------------------------------------------

def from_config(cfg):
    """Build from a scenario's `sim.sounding` block. Unknown keys are refused --
    the deck generator's convention: a typo must fail loudly, not be ignored."""
    d = {k: v for k, v in dict(cfg).items() if not k.startswith("_")}
    unknown = set(d) - SOUNDING_KEYS
    if unknown:
        raise SoundingError(f"sounding: unrecognised key(s) {sorted(unknown)}; "
                            f"known: {sorted(SOUNDING_KEYS - {'_note'})}")
    kind = d.pop("kind", "wk82")
    if kind != "wk82":
        raise SoundingError(f"sounding kind {kind!r}: only 'wk82' exists")
    hold = d.pop("hold_cape_jkg", None)
    kw = dict(WK82_DEFAULTS)
    kw.update(d)
    if hold is not None:
        if "qv_pbl_gkg" in d:
            raise SoundingError("sounding: declare EITHER qv_pbl_gkg OR hold_cape_jkg, "
                                "not both -- the solver overwrites qv_pbl.")
        kw["qv_pbl_gkg"] = solve_qv_pbl_for_cape(float(hold), **kw)
    return build(**kw)


def report(prof):
    """Diagnostics dict for the CLI / sidecar JSON. All units in the key names."""
    sb = parcel(prof, "sb")
    ml = parcel(prof, "ml")
    b = brn(prof, sb.cape_jkg)
    um, vm = mean_wind(prof, 0.0, 6000.0)
    return {
        "levels": int(len(prof.z)),
        "z_top_m": float(prof.z[-1]),
        "p_sfc_hpa": float(prof.p[0]) / 100.0,
        "p_at_z_tr_hpa": _interp(prof, prof.p, prof.params["z_tr_m"]) / 100.0,
        "t_at_z_tr_k": _interp(prof, prof.T, prof.params["z_tr_m"]),
        "qv_pbl_gkg": float(prof.params["qv_pbl_gkg"]),
        "max_rh": float(prof.rh.max()),
        "pwat_mm": precipitable_water_mm(prof),
        "sb": {"cape_jkg": sb.cape_jkg, "cin_jkg": sb.cin_jkg, "lcl_m": sb.lcl_m,
               "lfc_m": sb.lfc_m, "el_m": sb.el_m},
        "ml500": {"cape_jkg": ml.cape_jkg, "cin_jkg": ml.cin_jkg, "lcl_m": ml.lcl_m,
                  "lfc_m": ml.lfc_m, "el_m": ml.el_m},
        "bulk_shear_0_6km_ms": bulk_shear(prof),
        "mean_wind_0_6km_ms": [um, vm],
        "brn": b,
        "wk82_regime_prediction": wk82_regime(b),
        "params": prof.params,
    }


# --- the CM1 file ------------------------------------------------------------

def to_input_sounding(prof):
    """Render the WRF/CM1 `input_sounding` text.

    Line 1: surface pressure [hPa], surface theta [K], surface qv [g/kg].
    Then one line per level ABOVE the surface: z [m], theta [K], qv [g/kg],
    u [m/s], v [m/s]. The surface level's data rides on line 1 (WRF convention),
    so the level lines start at z = dz.
    """
    lines = [f"{prof.p[0] / 100.0:12.4f} {prof.theta[0]:12.4f} {prof.qv[0] * 1000.0:12.6f}"]
    for k in range(1, len(prof.z)):
        lines.append(f"{prof.z[k]:12.2f} {prof.theta[k]:12.4f} {prof.qv[k] * 1000.0:12.6f}"
                     f" {prof.u[k]:12.4f} {prof.v[k]:12.4f}")
    return "\n".join(lines) + "\n"


def parse_input_sounding(text):
    """Read the format back: (p_sfc_pa, theta_sfc, qv_sfc, z, theta, qv, u, v)."""
    rows = [ln.split() for ln in text.splitlines() if ln.strip()]
    if not rows or len(rows[0]) != 3:
        raise SoundingError("input_sounding: line 1 must be `p_sfc theta qv` (3 fields)")
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != 5:
            raise SoundingError(f"input_sounding line {i}: expected 5 fields, got {len(r)}")
    hdr = [float(x) for x in rows[0]]
    body = np.array([[float(x) for x in r] for r in rows[1:]], float)
    return (hdr[0] * 100.0, hdr[1], hdr[2] / 1000.0,
            body[:, 0], body[:, 1], body[:, 2] / 1000.0, body[:, 3], body[:, 4])


def write(path, prof):
    with open(path, "w", newline="\n") as f:      # LF on purpose: WSL reads it
        f.write(to_input_sounding(prof))
