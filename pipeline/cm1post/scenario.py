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
    crop_half_width_m: float
    crop_z_top_m: float

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
    def ny(self):
        return self.nx

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
        provenance=sim.get("provenance", {}),
        namelist=sim.get("namelist", {}),
        sounding=sim.get("sounding", {}),
        source_path=path,
        provisional_box=bool(exp.get("_provisional", False)),
    )
    _validate(sc, path)
    return sc


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
    for label, span in (("crop_half_width_m", 2 * sc.crop_half_width_m),
                        ("crop_z_top_m", sc.crop_z_top_m)):
        n = span / sc.export_voxel_m
        if abs(n - round(n)) > 1e-9:
            raise ValueError(
                f"{path}: {label}={span/2 if 'half' in label else span} is not an "
                f"integer number of {sc.export_voxel_m} m voxels (got {n}) -- the "
                "exported box would silently differ from the declared one")
