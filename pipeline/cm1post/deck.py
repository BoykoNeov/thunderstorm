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

Four key CATEGORIES, and only the first lives in the scenario JSON
------------------------------------------------------------------
  1. SCENARIO IDENTITY (JSON `sim.namelist`, REQUIRED)  -- grid, timing, microphysics,
     sounding/shear/initiation. Required rather than template-defaulted so that
     generating a scenario genuinely exercises every override instead of silently
     inheriting the template's value.
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


# --- override assembly ------------------------------------------------------

def build_overrides(sc):
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
               and k not in ("umove", "vmove")]
    if unknown:
        raise DeckError(
            f"{sc.source_path}: sim.namelist has unrecognised key(s): "
            f"{', '.join(sorted(unknown))}. Add them to REQUIRED_KEYS deliberately "
            "-- a typo here would otherwise be silently ignored.")

    ov = {k: nml[k] for k in REQUIRED_KEYS}

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

    overrides = build_overrides(sc)

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
