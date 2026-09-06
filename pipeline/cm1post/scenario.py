"""Per-scenario configuration, loaded from sim/scenarios/<name>.json.

Everything here VARIES between scenarios. Everything frozen by the package format
lives in `contract.py` -- see docs/phase2-plan-2026-07-20.md §4 for why that line is
drawn where it is.

The JSON file is the single source of truth: it feeds both the CM1 deck generator
(`sim/scenarios/` -> namelist.input) and this post-processor, so a scenario cannot
be simulated with one geometry and exported with another.
"""
import json
import os
from dataclasses import dataclass, field, replace

SCHEMA_VERSION = "1.0"

# Repo-root-relative default location of scenario configs.
SCENARIO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "sim", "scenarios",
)


@dataclass(frozen=True)
class Scenario:
    """One scenario's identity, source run, and export geometry."""

    name: str
    kind: str                     # single_cell | multicell | supercell
    phase: str                    # which project phase produced it
    description: str
    run_dir: str                  # CM1 output dir (WSL ext4 -- never /mnt/*)

    export_voxel_m: float
    crop_half_width_m: float          # HALF-EXTENT IN X (across-line, for a line)
    crop_z_top_m: float

    # HALF-EXTENT IN Y. Absent (None) means "same as x" -- a square box, which is
    # what every compact storm wants and what the schema assumed outright until the
    # squall line needed otherwise. A squall line is compact ACROSS the line and
    # spans the whole domain ALONG it, so one number cannot describe it: the only
    # legal square box for a line is the full domain, i.e. the largest possible
    # package, mostly empty (docs/plan-science-hurdles-2026-09-02.md 4.4).
    #
    # It is optional rather than required so every existing config stays valid and
    # every existing package stays byte-identical -- the manifest already carried
    # `dimensions` and `extent_m.x/.y` as separate keys, so only the VALUES become
    # unequal, not the wire shape. That is why FORMAT_VERSION does not move.
    crop_half_depth_m: float = None

    provenance: dict = field(default_factory=dict)
    namelist: dict = field(default_factory=dict)
    source_path: str = ""

    # Optional `sim.sounding` block: the environment for CM1 `isnd=7`, rendered to
    # `input_sounding` by cm1post.sounding. Empty for the analytic-sounding
    # scenarios (isnd=5). deck.py enforces the coupling both ways -- a block at
    # isnd!=7 is a sounding CM1 would never read, and isnd=7 without one is a run
    # that dies at startup looking for a file nobody generated.
    sounding: dict = field(default_factory=dict)

    # True while `export` still holds placeholder numbers. The crop box is an
    # OUTPUT of the run, not an input: it is measured from that run's own
    # active-voxel union (Phase 1 learned this the expensive way -- a box copied
    # from elsewhere CLIPPED the real cold-pool outflow, and the export succeeded
    # anyway). A new scenario therefore needs a loadable config BEFORE its box can
    # exist, so the placeholder is legal -- but `require_measured_box` must gate
    # every consumer that would bake it into a package.
    provisional_box: bool = False

    # --- derived export grid ------------------------------------------------
    # These were module constants in the Phase 1 config.py; they are derived here
    # so a scenario cannot declare a grid inconsistent with its own crop box.

    @property
    def nx(self):
        return int(round(2 * self.crop_half_width_m / self.export_voxel_m))

    @property
    def half_depth_m(self):
        """The y half-extent, resolved. Defaults to the x half-width (square box)."""
        return (self.crop_half_width_m if self.crop_half_depth_m is None
                else self.crop_half_depth_m)

    @property
    def ny(self):
        return int(round(2 * self.half_depth_m / self.export_voxel_m))

    @property
    def nz(self):
        return int(round(self.crop_z_top_m / self.export_voxel_m))

    @property
    def origin_m(self):
        """World coords (CM1 SI metres) of the CENTRE of voxel (0,0,0).

        OpenVDB's linear transform maps index -> world at voxel CENTRES, so the
        origin is DERIVED (never hand-set) to make the centres symmetric about
        x=y=0. This is what pins the bbox centre to exactly (0,0) for every frame
        -- the SVT static-centre constraint, satisfied by construction rather than
        by luck. dense2vdb post-translates the shared transform by this, so the VDB
        carries true CM1 coordinates in SI metres.

        The metres->centimetres and Y-flip conversion into UE space is applied at
        ACTOR PLACEMENT, never here (single-conversion-site rule).
        """
        return (
            -(self.nx - 1) / 2.0 * self.export_voxel_m,
            -(self.ny - 1) / 2.0 * self.export_voxel_m,
            self.export_voxel_m / 2.0,   # first cell centre above ground
        )

    def describe_grid(self):
        ox, oy, oz = self.origin_m
        return (f"{self.nx}x{self.ny}x{self.nz} @ {self.export_voxel_m:.0f} m"
                f"  origin ({ox:.1f}, {oy:.1f}, {oz:.1f})")


def _require(doc, key, path):
    if key not in doc:
        raise ValueError(f"{path}: missing required key '{key}'")
    return doc[key]


def load(name_or_path, run_dir_override=None):
    """Load a scenario by NAME (looked up in sim/scenarios/) or by explicit path."""
    path = name_or_path
    if not os.path.isfile(path):
        path = os.path.join(SCENARIO_DIR, f"{name_or_path}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"no scenario config for '{name_or_path}' "
            f"(looked for {name_or_path} and {path})")

    with open(path) as f:
        doc = json.load(f)

    got = doc.get("schema_version")
    if got != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {got!r} != {SCHEMA_VERSION!r} "
            "(this loader does not migrate scenario configs)")

    exp = _require(doc, "export", path)
    sim = _require(doc, "sim", path)

    sc = Scenario(
        name=_require(doc, "name", path),
        kind=_require(doc, "kind", path),
        phase=doc.get("phase", ""),
        description=doc.get("description", ""),
        run_dir=run_dir_override or _require(sim, "run_dir", path),
        export_voxel_m=float(_require(exp, "voxel_m", path)),
        crop_half_width_m=float(_require(exp, "crop_half_width_m", path)),
        crop_z_top_m=float(_require(exp, "crop_z_top_m", path)),
        # Optional. Absent -> None -> square (see the field comment). Read with
        # `.get` rather than `_require` precisely so no existing config moves.
        crop_half_depth_m=(None if exp.get("crop_half_depth_m") is None
                           else float(exp["crop_half_depth_m"])),
        provenance=sim.get("provenance", {}),
        namelist=sim.get("namelist", {}),
        sounding=sim.get("sounding", {}),
        source_path=path,
        provisional_box=bool(exp.get("_provisional", False)),
    )
    _validate(sc, path)
    return sc


# CM1 lateral boundary-condition codes (README.namelist). The template runs 2 --
# open/radiative -- on all four sides, which is right for a compact storm; see
# deck.py's OPTIONAL_KEYS note on sbc/nbc for why a LINE needs 1 instead.
BC_PERIODIC = 1
BC_OPEN = 2

# Which namelist keys bound each horizontal axis, and which keys give its extent.
_AXES = {
    "x": {"walls": ("wbc", "ebc"), "n": "nx", "d": "dx"},
    "y": {"walls": ("sbc", "nbc"), "n": "ny", "d": "dy"},
}


def periodic_axes(sc):
    """{"x": bool, "y": bool} -- periodicity, read from the scenario's NAMELIST.

    Deliberately not a flag in the `export` block. "This axis is periodic, so its
    extent is the whole domain by construction" is a claim about the simulation,
    and an `export`-block assertion of it would be a placeholder wearing a
    different hat -- exactly what `require_measured_box` exists to refuse. Reading
    it from the same namelist that gets rendered into the deck makes the claim
    unfalsifiable-by-editing: change the boundary condition and the export rule
    changes with it. Same pattern as deck.py's Category 6 coupling check.
    """
    out = {}
    for axis, spec in _AXES.items():
        lo_k, hi_k = spec["walls"]
        lo = int(sc.namelist.get(lo_k, BC_OPEN))
        hi = int(sc.namelist.get(hi_k, BC_OPEN))
        if (lo == BC_PERIODIC) != (hi == BC_PERIODIC):
            raise ValueError(
                f"{sc.source_path}: {lo_k}={lo}, {hi_k}={hi} -- periodicity is a "
                f"property of the {axis} AXIS, not of one wall. Declare both as "
                f"{BC_PERIODIC} (periodic) or neither.")
        out[axis] = lo == BC_PERIODIC
    return out


def domain_half_m(sc, axis):
    """Half-extent of the CM1 DOMAIN along `axis`, in metres, from the namelist.

    The domain spans nx*dx and the scenarios run iorigin=2 (centred coordinates),
    so it reaches +/- nx*dx/2. This is the only honest export extent for a
    periodic axis -- see `check_periodic_extents`.
    """
    spec = _AXES[axis]
    for k in (spec["n"], spec["d"]):
        if k not in sc.namelist:
            raise ValueError(
                f"{sc.source_path}: sim.namelist has no '{k}', so the {axis} domain "
                "extent is unknown and a periodic-axis export cannot be checked.")
    return float(sc.namelist[spec["n"]]) * float(sc.namelist[spec["d"]]) / 2.0


def check_periodic_extents(sc):
    """On a periodic axis the export extent must be the FULL DOMAIN.

    This is the measurement rule T5 section 11.7 flagged and the 2026-09-02 plan
    section 4.4 scoped. Two halves:

    (a) It is a VALID MEASURED ROUTE. `export_scenario.py bbox` measures the
        active-voxel union and demands the box contain it. On a periodic axis the
        union IS the domain -- CM1's iinit=8 line thermal has no y term, so the
        line spans y by construction -- and that is the intended setup, not a
        storm escaping. Without this rule a line could never clear the gate.

    (b) It is a REAL GATE, not a waiver. Anything SMALLER than the full domain on
        a periodic axis is a crop with no outside to crop to: it cuts a structure
        that wraps, and the resulting package advertises edges that are an
        artifact of the box. So the extent is not merely allowed to be the full
        domain -- it is REQUIRED to be, and a mismatch is an error.

    A non-periodic axis is untouched: its extent is measured, and the sweep's
    containment check is the gate.
    """
    per = periodic_axes(sc)
    for axis, half in (("x", sc.crop_half_width_m), ("y", sc.half_depth_m)):
        if not per[axis]:
            continue
        full = domain_half_m(sc, axis)
        if abs(half - full) > 1e-6:
            key = "crop_half_width_m" if axis == "x" else "crop_half_depth_m"
            raise ValueError(
                f"{sc.source_path}: {axis} is PERIODIC "
                f"({'/'.join(_AXES[axis]['walls'])}={BC_PERIODIC}) but the export "
                f"box declares {key}={half:.1f} m against a domain half-extent of "
                f"{full:.1f} m. A periodic axis has no outside: any smaller box "
                "cuts a structure that wraps, and the package would ship edges "
                "that are an artifact of the crop. Set it to the full domain.")


def box_verdict(sc, half_x, half_y, ztop):
    """Per-axis PASS/FAIL for a measured active-voxel union. PURE -- no I/O.

    Split out of `cmd_bbox` so it can be tested without a CM1 run, and split
    PER AXIS because the collapsed version was wrong. It used to be one scalar:

        half = max(half, |x_min|, |x_max|, |y_min|, |y_max|)

    -- which is exactly right while `ny == nx` and silently wrong the moment they
    differ. On a periodic-y squall line the y union IS the whole domain, so the
    collapsed maximum reports the full-domain half-extent as "the" half-width and
    then demands a SQUARE box that large: the largest possible package, mostly
    empty (docs/plan-science-hurdles-2026-09-02.md 4.4), reached through the
    measurement rather than through the schema. Neither the plan nor T5 11.7 named
    this one; it is the sweep's own version of the same square-by-construction bug.

    Returns [(label, measured_m, box_m, ok, note), ...].
    """
    per = periodic_axes(sc)
    rows = []
    for axis, label, measured, box in (
            ("x", "x half-width", half_x, sc.crop_half_width_m),
            ("y", "y half-depth", half_y, sc.half_depth_m)):
        if per[axis]:
            # PERIODIC: containment is not the question. The union reaches the wall
            # by construction (that is what periodic means), and the only honest box
            # is the full domain -- see check_periodic_extents.
            full = domain_half_m(sc, axis)
            ok = abs(box - full) <= 1e-6
            rows.append((label, measured, box, ok,
                         f"PERIODIC -- full domain by construction ({full/1000:.3f} km)"))
        else:
            rows.append((label, measured, box, measured <= box, "measured union"))
    rows.append(("top", ztop, sc.crop_z_top_m, ztop <= sc.crop_z_top_m,
                 "measured union"))
    return rows


def require_measured_box(sc):
    """Refuse to proceed while the crop box is still a placeholder.

    Called by anything that BAKES the box into a durable artifact (the exporter).
    Deck generation deliberately does NOT call this: generating the deck is what
    produces the run the box gets measured from, so demanding a measured box there
    would be a chicken-and-egg deadlock for every new scenario.
    """
    if sc.provisional_box:
        raise ValueError(
            f"{sc.source_path}: export box is still marked \"_provisional\": true. "
            "Run the scenario, measure its own active-voxel union with the bbox "
            "sweep, write the result back into `export`, and drop the flag. "
            "Exporting now would ship a box measured from a DIFFERENT storm -- "
            "which succeeds silently and clips whatever falls outside it.")
    # Not a placeholder, but the sweep alone cannot police a periodic axis: there
    # the extent is fixed by the boundary condition, not by the storm.
    check_periodic_extents(sc)


def with_export_voxel(sc, voxel_m, path=None):
    """A copy of `sc` exporting on a COARSER Cartesian grid, re-validated.

    Presentation-side decimation for the web viewer only -- the same category as
    webvol.py's quantization ("no science here"). Same run, same fields, same
    encodings, fewer voxels.

    It deliberately does NOT live in the scenario JSON. That file exists so "a
    scenario cannot be simulated with one geometry and exported with another"
    (module docstring), and a second config duplicating the `sim` block to change
    one export number would be a second file claiming that guarantee while free to
    drift from it: edit the parent's namelist and the copy silently keeps the old
    one while still advertising the same provenance. The factor is recorded instead
    where a reader actually looks -- `web/web_manifest.json`, which IS tracked in
    git for web packages (2026-07-22 amendment) and is the grid a reader loads.

    nx/ny/nz and origin_m are PROPERTIES derived from voxel_m and the crop box, so
    they all follow from this one substitution -- there is no second place to keep
    in step. `_validate` then refuses any voxel size that does not divide the
    declared box into whole voxels, which is what stops `int(round(...))` from
    silently producing an off-by-one grid for a box the manifest still declares.
    """
    sc2 = replace(sc, export_voxel_m=float(voxel_m))
    _validate(sc2, path or sc.source_path)
    return sc2


def _validate(sc, path):
    """Catch geometry that would silently produce a wrong package."""
    if sc.export_voxel_m <= 0:
        raise ValueError(f"{path}: voxel_m must be > 0")

    # A non-integer voxel count means the declared crop box is NOT the box that
    # gets exported -- the rounding would move the extent without saying so.
    if sc.crop_half_depth_m is not None and sc.crop_half_depth_m <= 0:
        raise ValueError(f"{path}: crop_half_depth_m must be > 0 when declared")

    for label, span in (("crop_half_width_m", 2 * sc.crop_half_width_m),
                        ("crop_half_depth_m", 2 * sc.half_depth_m),
                        ("crop_z_top_m", sc.crop_z_top_m)):
        n = span / sc.export_voxel_m
        if abs(n - round(n)) > 1e-9:
            raise ValueError(
                f"{path}: {label}={span/2 if 'half' in label else span} is not an "
                f"integer number of {sc.export_voxel_m} m voxels (got {n}) -- the "
                "exported box would silently differ from the declared one")
