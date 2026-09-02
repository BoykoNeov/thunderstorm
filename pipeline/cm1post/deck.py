"""CM1 deck generation: scenario JSON -> namelist.input.

The other half of the Phase 2 scenario system (docs/phase2-plan-2026-07-20.md §4).
The pipeline reads a scenario config to EXPORT; this module uses the same config to
SIMULATE, so a scenario cannot be run with one geometry and exported with another.

Design: TEMPLATE + OVERRIDES, never full generation
---------------------------------------------------
The validated deck carries ~8 KB of parameters that must not drift -- numerics,
boundary conditions, SGS constants, the NSSL microphysics block. Regenerating those
from scratch would put every one of them at risk to gain nothing. So the base
template is a committed, validated deck and a scenario declares only what it
CHANGES.

Substitution is LINE-ANCHORED TEXT REPLACEMENT, not parse-and-re-emit. Two reasons,
both learned the hard way elsewhere in this repo:

  * Anchoring on `^\\s*KEY\\s*=` is what stops `dz` from clobbering `dz_bot`/`dz_top`
    and `dx` from clobbering `dx_inner`/`dx_outer`. A substring match here corrupts
    the deck SILENTLY -- it still runs, just not the simulation you asked for.
  * Every line we do not touch stays byte-identical. A parse-and-re-emit pass would
    have to round-trip `rdalpha = 3.3333333333e-3`, `ccn = 0.6e9` and the inline `!`
    comments in &nssl2mom_params through float formatting, and would rewrite 400
    lines to change 17.

Key CATEGORIES -- the first lives in the scenario JSON, the fifth optionally, and
the sixth is not a namelist key at all (see ISND_EXTERNAL below)
--------------------------------------------------------------------------------
  1. SCENARIO IDENTITY (JSON `sim.namelist`, REQUIRED)  -- grid, timing, microphysics,
     sounding/shear/initiation. Required rather than template-defaulted so that
     generating a scenario genuinely exercises every override instead of silently
     inheriting the template's value.

     One of these is SEMANTIC: the scenario declares `seed`, which is substituted
     into CM1's `var7`. The indirection is deliberate -- a raw `"var7": 3.0` in a
     scenario file tells a future reader nothing, and the seed has to carry a real
     name into provenance. See `_seed_to_var7` for why the mapping validates rather
     than just casts.
  2. GEOMETRY-DERIVED (computed here) -- dx_inner/tot_x_len/dy_inner/tot_y_len follow
     from nx/dx/ny/dy. Inert while stretch_x/stretch_y are 0, but kept consistent so
     they are not a landmine for the first stretched-grid scenario.
  3. MOTION-COUPLED (computed or required) -- umove/vmove are forced to 0 when
     imove=0. When imove=1 they are a Bunkers estimate, not derivable, so the JSON
     must supply them.
  4. OUTPUT BLOCK (template DNA, verbatim) -- deliberately NOT generated from
     contract.SOURCE_FIELDS. The validated deck writes considerably more than the
     export reads (tke, km/kh, uh, vort, lcl/lfc/pwat...), and those extras are used
     by the validation and analysis scripts. The contract is applied as an
     ASSERTION instead (`check_output_flags`): every field the exporter needs must
     have its output flag on. As a check that is real safety; as a generator it
     would quietly shrink the deck.
"""
import os
import re

from . import contract

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "sim", "templates",
)
DEFAULT_TEMPLATE = os.path.join(TEMPLATE_DIR, "base.namelist.input")

# Category 1. A scenario MUST declare all of these -- see the module docstring for
# why they are required rather than defaulted.
REQUIRED_KEYS = [
    # grid
    "nx", "ny", "nz", "dx", "dy", "dz",
    # timing / output cadence
    "timax", "tapfrq", "dtl", "adapt_dt",
    # storm design: sounding, shear, initiation, rotation, domain motion
    "isnd", "iwnd", "iinit", "irandp", "icor", "imove", "iorigin",
    # seed-driven outcome variation (Phase 3 T4) -- semantic name, emitted as var7
    "seed",
    # microphysics
    "ptype", "ihail",
    # terrain / vertical grid mode
    "terrain_flag", "itern", "stretch_z",
]

# Category 4. CM1 output flags the pipeline depends on. Checked, never generated.
#   output_q       -- the hydrometeor mixing ratios in contract.SOURCE_FIELDS
#   output_dbz     -- the dbz diagnostic channel, and cref (composite reflectivity)
#   output_winterp -- updraft w already interpolated to scalar points (Phase 2 T4)
REQUIRED_OUTPUT_FLAGS = {
    "output_q": "hydrometeor mixing ratios (qc/qi/qs/qr/qg/qhl)",
    "output_dbz": "dbz diagnostic channel + cref composite reflectivity",
    "output_winterp": "updraft w on scalar points (selectable field)",
}

# Category 5. OPTIONAL run-control overrides -- substituted into the template when
# the scenario declares them, otherwise the template value stands. Unlike
# REQUIRED_KEYS these are NOT part of a scenario's identity: the same storm runs with
# or without them; they tune run robustness, not physics. Each must already exist in
# the template so line-anchored substitution has a line to replace.
#   rstfrq -- restart-file cadence (s). The template default (-3600 = restarts off)
#             is fine for the short Phase 1/2 runs, but the charter marks restarts
#             "safely skippable only on short 2-3 h runs"; the Phase 3 (~4.5 h) and
#             Phase 3T (15-30 h) runs set it positive so a mid-run crash costs time,
#             not a full re-run.
#   sbc, nbc -- south/north lateral boundary condition (1=periodic, 2=open-radiative,
#             3/4=rigid). The template runs 2 on all four sides, which is right for a
#             compact storm. It is WRONG for a line: CM1's iinit=8 line thermal has no
#             y term in its `beta` and no y-extent parameter anywhere (the geometry is
#             hardcoded in init3d.F), so the line necessarily spans the whole domain in
#             y. With open y boundaries its ends are an artifact and no containment
#             criterion can be satisfied; periodic y is the standard along-line
#             configuration for squall-line simulations and makes the same line the
#             INTENDED setup. Category 5 rather than 5-with-physics because it changes
#             the domain's topology, not the storm's environment.
OPTIONAL_KEYS = ("rstfrq", "sbc", "nbc")

# Category 6. THE EXTERNAL SOUNDING (Phase 3 T5s, docs/plan-science-hurdles-2026-09-02.md).
# Not a namelist key at all: with isnd=7 CM1 reads the base state (theta, qv, u, v)
# from a text file `input_sounding` in the run dir, which cm1post.sounding renders
# from the scenario's `sim.sounding` block. That file is the second scenario input
# and run_scenario.sh records its sha256 beside the binary's. The generator's job
# here is the COUPLING: the block and isnd=7 must appear together, and iwnd must
# be 0 so the deck cannot look like it declares a shear profile CM1 does not apply
# (the wind comes from the file). Whether CM1 really ignores iwnd at isnd=7 is
# verified on the box by the base-state neutrality gate; requiring 0 is safe under
# either reading -- if iwnd DID apply, 0 would zero the winds and the gate fires.
ISND_EXTERNAL = 7


class DeckError(Exception):
    """A scenario that would produce a wrong or unrunnable deck."""


# --- Fortran value formatting ----------------------------------------------

def format_value(value):
    """Render a JSON value as Fortran namelist text."""
    if isinstance(value, bool):            # before int -- bool IS an int in Python
        return ".true." if value else ".false."
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Integral floats keep a trailing .0 so CM1 reads them as REAL, not INTEGER.
        return f"{value:.1f}" if value == int(value) else repr(value)
    raise DeckError(f"cannot render {value!r} ({type(value).__name__}) as Fortran")


# --- namelist parsing (for gates and assertions, never for emitting) --------

_ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse(text):
    """Parse a namelist into {key: normalised value}.

    Deliberately tolerant and one-key-per-line: it exists to COMPARE decks, not to
    reproduce them. Comments and key order are dropped, which is exactly the
    "modulo comments and key ordering" the reproduction gate is specified against.
    """
    out = {}
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()
        if not line or line.startswith("&") or line == "/":
            continue
        m = _ASSIGN.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).rstrip(",").strip()
        out[key.lower()] = _normalise(val)
    return out


def _normalise(val):
    low = val.lower()
    if low in (".true.", ".t.", "true"):
        return True
    if low in (".false.", ".f.", "false"):
        return False
    try:
        return float(val)
    except ValueError:
        return val


def values_equal(a, b, tol=1e-9):
    """Compare two parsed namelist values, with tolerance for floats.

    Needed because the committed decks carry values like 3.3333333333e-3 and 0.6e9
    that are not exactly representable and must not be compared as text.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, float) and isinstance(b, float):
        if a == b:
            return True
        scale = max(abs(a), abs(b), 1.0)
        return abs(a - b) <= tol * scale
    return a == b


# --- the seed (Category 1, semantic) ----------------------------------------

# The CM1 namelist key that carries the seed. See sim/cm1-patches/README.md: stock
# cm1r21.1 has NO seed knob at all (`use_truly_random_pert` is a compile-time
# `logical, parameter`), so `irandp=1` draws the SAME perturbation field every run.
# The project's fork enables CM1's own commented-out hook, in which `var7` advances
# the PRNG stream by nint(var7)*nk*(ny+2)*(nx+2) draws before the perturbations are
# drawn. `var7` is an EXISTING CM1 key (&param8), which is what keeps "the namelist
# is the sole scenario input" true across the fork.
SEED_NAMELIST_KEY = "var7"


def _seed_to_var7(seed, irandp, path):
    """Validate a scenario's `seed` and render it as CM1's var7 value.

    Three rejections, each of which would otherwise be SILENT -- the deck would
    generate, CM1 would run for hours, and the result would not be the ensemble
    member that was asked for:

      * NEGATIVE seed -- `do n=1,nint(-5.0)` is a zero-trip loop, so seed -5 does
        not error in CM1, it silently ALIASES to seed 0. Two "different" members
        would come back bitwise identical.
      * NON-INTEGER seed -- `nint()` rounds, so 1.4 and 0.6 both alias to 1.
      * seed > 0 while irandp = 0 -- the advance loop lives inside
        `IF( irandp.eq.1 )THEN`, so with random perturbations switched off the seed
        is read, broadcast, and ignored. This is the trap most likely to be hit in
        practice: copying a seeded scenario from an unseeded one and changing only
        the seed produces N identical storms.
    """
    if isinstance(seed, bool) or not isinstance(seed, (int, float)):
        raise DeckError(
            f"{path}: seed must be a non-negative integer, got {seed!r} "
            f"({type(seed).__name__}).")
    if float(seed) != int(seed):
        raise DeckError(
            f"{path}: seed={seed} is not an integer. CM1 applies nint() to it, so "
            "1.4 and 0.6 would both alias to seed 1 -- two scenarios that read as "
            "distinct would produce the same storm.")
    s = int(seed)
    if s < 0:
        raise DeckError(
            f"{path}: seed={s} is negative. The CM1 advance is `do n=1,nint(var7)`, "
            "which is ZERO-TRIP for a negative value -- this would not fail, it "
            "would silently alias to seed 0.")
    if s > 0 and int(irandp) == 0:
        raise DeckError(
            f"{path}: seed={s} with irandp=0. The seed advance lives inside "
            "`IF( irandp.eq.1 )THEN`, so with random perturbations off the seed is "
            "silently ignored and every 'variant' reproduces the same storm. Set "
            "irandp=1 to vary outcomes, or seed=0 to declare this run unseeded.")
    # float, never int: the template line reads `var7 = 0.0,` and format_value(0)
    # emits "0" -- an int here would rewrite the line and break the byte-identity
    # gates for every existing scenario. Same trap the OPTIONAL_KEYS cast avoids.
    return float(s)


# --- override assembly ------------------------------------------------------

def _match_template_type(key, value, template_lines):
    """Cast an optional override to the Fortran type the TEMPLATE declares.

    CM1's namelist variables are typed, and a REAL written into an INTEGER slot is
    a hard read error at startup, not a subtle wrongness. Rather than keeping a
    hand-maintained type table that can drift, the type is read from the template
    line the value will replace -- the same source of truth the rest of the
    generator uses. Unfound key -> float, matching the pre-existing behaviour;
    generate()'s `hits != 1` guard is what actually catches a missing line.
    """
    if template_lines is not None:
        pat = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(\S+?),?\s*$", re.IGNORECASE)
        for line in template_lines:
            m = pat.match(line)
            if m:
                raw = m.group(1)
                is_int = not any(c in raw for c in ".eEdD")
                return int(value) if is_int else float(value)
    return float(value)


def build_overrides(sc, template_lines=None):
    """All four categories, resolved into one {key: value} map."""
    nml = dict(sc.namelist)
    nml.pop("_note", None)

    missing = [k for k in REQUIRED_KEYS if k not in nml]
    if missing:
        raise DeckError(
            f"{sc.source_path}: sim.namelist is missing required key(s): "
            f"{', '.join(missing)}. These define the scenario and are deliberately "
            "NOT defaulted from the template -- see cm1post/deck.py.")

    unknown = [k for k in nml if not k.startswith("_") and k not in REQUIRED_KEYS
               and k not in ("umove", "vmove") and k not in OPTIONAL_KEYS]
    if unknown:
        raise DeckError(
            f"{sc.source_path}: sim.namelist has unrecognised key(s): "
            f"{', '.join(sorted(unknown))}. Add them to REQUIRED_KEYS (or "
            "OPTIONAL_KEYS) deliberately -- a typo here would otherwise be "
            "silently ignored.")

    ov = {k: nml[k] for k in REQUIRED_KEYS}

    # Category 6 -- external sounding coupling (both directions, plus iwnd).
    _check_sounding_coupling(sc, nml)

    # Category 1, semantic -- `seed` is declared by name and emitted as var7. Popped
    # rather than left in place: there is no `seed =` line in the template, so a
    # stray `seed` override would trip the hits != 1 guard in generate().
    ov[SEED_NAMELIST_KEY] = _seed_to_var7(ov.pop("seed"), nml["irandp"], sc.source_path)

    # Category 5 -- optional run-control passthrough (rstfrq, sbc, nbc). Present ->
    # the scenario's value wins; absent -> the template default stands untouched, so
    # scenarios that omit these reproduce byte-for-byte (the T1c gate is unaffected).
    #
    # The cast is NOT blanket float(). It was, for rstfrq (a CM1 REAL, template line
    # `rstfrq = -3600.0`), and that silently emitted `sbc = 1.0` into an INTEGER
    # namelist variable -- which gfortran rejects outright, so the run would have
    # died at startup rather than produced a wrong storm. The Fortran type belongs
    # to the CM1 variable, not to the JSON, so it is read off the TEMPLATE line:
    # a template value written without a decimal point is an integer key.
    for k in OPTIONAL_KEYS:
        if k in nml:
            ov[k] = _match_template_type(k, nml[k], template_lines)

    # Category 2 -- geometry-derived. Inert at stretch_x/y = 0, kept consistent.
    ov["dx_inner"] = float(nml["dx"])
    ov["dy_inner"] = float(nml["dy"])
    ov["tot_x_len"] = float(nml["nx"]) * float(nml["dx"])
    ov["tot_y_len"] = float(nml["ny"]) * float(nml["dy"])

    # Category 3 -- motion-coupled.
    if int(nml["imove"]) == 0:
        for k in ("umove", "vmove"):
            if k in nml and float(nml[k]) != 0.0:
                raise DeckError(
                    f"{sc.source_path}: imove=0 (stationary domain) but {k}="
                    f"{nml[k]}. A non-zero translation with imove=0 is a "
                    "contradiction; it would also break the static SVT bbox centre.")
        ov["umove"] = 0.0
        ov["vmove"] = 0.0
    else:
        for k in ("umove", "vmove"):
            if k not in nml:
                raise DeckError(
                    f"{sc.source_path}: imove={nml['imove']} requires an explicit "
                    f"'{k}' (a Bunkers storm-motion estimate -- not derivable).")
            ov[k] = float(nml[k])

    return ov


def _check_sounding_coupling(sc, nml):
    has_block = bool(getattr(sc, "sounding", None))
    external = int(nml["isnd"]) == ISND_EXTERNAL
    if external and not has_block:
        raise DeckError(
            f"{sc.source_path}: isnd={ISND_EXTERNAL} (external sounding) but the "
            "scenario has no sim.sounding block. CM1 would start, look for "
            "input_sounding, and die -- or worse, read a stale one left in run_dir "
            "from another scenario. Declare the environment in sim.sounding.")
    if has_block and not external:
        raise DeckError(
            f"{sc.source_path}: sim.sounding is declared but isnd={nml['isnd']}. "
            f"CM1 reads input_sounding only at isnd={ISND_EXTERNAL}; at any other "
            "value the declared environment is silently NOT the one simulated.")
    if external and int(nml["iwnd"]) != 0:
        raise DeckError(
            f"{sc.source_path}: isnd={ISND_EXTERNAL} with iwnd={nml['iwnd']}. The "
            "wind profile comes from input_sounding; declare iwnd=0 so the deck does "
            "not advertise an analytic shear profile that is not what runs.")


# --- generation -------------------------------------------------------------

def _substitute(lines, key, value):
    """Replace KEY's value in place, anchored on the whole key.

    Returns (new_lines, hits). Anchoring is the point: `^\\s*dz\\s*=` must not match
    ` dz_bot   = 125.0,`.
    """
    pat = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)(\S.*?)(,?)(\s*)$", re.IGNORECASE)
    text = format_value(value)
    hits = 0
    out = []
    for line in lines:
        m = pat.match(line)
        if not m:
            out.append(line)
            continue
        hits += 1
        head, old, comma, tail = m.groups()
        # Keep the template's column alignment where the new value still fits.
        pad = max(0, len(old) - len(text))
        out.append(f"{head}{' ' * pad}{text}{comma}{tail}")
    return out, hits


def generate(sc, template_path=None):
    """Render this scenario's namelist.input. Returns (text, overrides)."""
    path = template_path or DEFAULT_TEMPLATE
    with open(path) as f:
        lines = f.read().splitlines()

    overrides = build_overrides(sc, lines)

    for key, value in overrides.items():
        lines, hits = _substitute(lines, key, value)
        if hits != 1:
            raise DeckError(
                f"{os.path.basename(path)}: key '{key}' matched {hits} line(s), "
                "expected exactly 1. The template and the scenario schema have "
                "drifted apart -- refusing to emit a deck that may be missing an "
                "override.")

    text = "\n".join(lines) + "\n"
    check_output_flags(text, path)
    return text, overrides


def check_output_flags(text, label="deck"):
    """Assert the deck writes every CM1 field the exporter reads.

    The contract is applied here as a CHECK, not as a generator -- see the module
    docstring. This catches the failure mode where a scenario runs for hours and
    only then turns out to have written no dbz.
    """
    parsed = parse(text)
    off = []
    for flag, why in sorted(REQUIRED_OUTPUT_FLAGS.items()):
        if not parsed.get(flag):
            off.append(f"{flag}=0 -- needed for {why}")
    if off:
        raise DeckError(
            f"{label}: the pipeline could not export this run:\n  "
            + "\n  ".join(off))
    return sorted(REQUIRED_OUTPUT_FLAGS)


def describe_sources():
    """The CM1 variables the export contract reads, for the CLI's report."""
    seen = []
    for ch in contract.CHANNELS:
        for v in contract.SOURCE_FIELDS[ch]:
            if v not in seen:
                seen.append(v)
    return seen
