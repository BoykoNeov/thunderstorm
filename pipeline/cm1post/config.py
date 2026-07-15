"""Export contract for the Phase 1 single-cell scenario package.

Every number here is load-bearing and traceable to a doc:
  - channel map / packing / export res : docs/phase1-svt-budget.md
  - static padded bbox                 : the UE SVT hard constraint (CLAUDE.md)
  - crop extent                        : measured union bbox over ALL 301 real
                                         frames (docs/phase1-task5-pipeline.md)

Nothing here may be tuned per-frame: the SVT contract requires one transform and a
static bbox center for the whole sequence.
"""

# Scenario-package format contract version (manifest carries this; UE refuses a
# newer major version). Bumped when the package layout or channel map changes.
FORMAT_VERSION = "1.0"

# --- channel map (docs/phase1-svt-budget.md) --------------------------------
# Grid NAMES are frozen: task 3 proved UE 5.8's default grid->SVT assignment
# reproduces this map exactly (Tex A RGBA16F = cloud/ice/rain/graupelhail,
# Tex B R16F = dbz). Changing a name would force an SVT import re-test.
CHANNELS = ["cloud", "ice", "rain", "graupelhail", "dbz"]

# What each rendered channel is MADE OF, in CM1/NSSL ptype=27 terms.
# Two channels merge physically-similar categories that read as one thing in a
# volume render (the split stays recoverable in the 3 spare SVT channels):
#   ice         = qi (cloud ice) + qs (snow)   -- one glaciated "anvil" category.
#                 Not optional: measured qs/qi ~ 0.29-0.53 by mass and snow fills
#                 as many voxels as ice, so dropping qs visibly thins the anvil.
#   graupelhail = qg (graupel)   + qhl (hail)  -- one "dense frozen precip".
SOURCE_FIELDS = {
    "cloud": ["qc"],
    "ice": ["qi", "qs"],
    "rain": ["qr"],
    "graupelhail": ["qg", "qhl"],
    "dbz": ["dbz"],  # NOT summed -- diagnostic, taken straight from CM1
}

# Channels that are summed mixing ratios (kg/kg) vs. the dBZ diagnostic.
DIAGNOSTIC_CHANNELS = {"dbz"}

# --- activity thresholds ----------------------------------------------------
# ONE set of thresholds, used for BOTH the bbox sweep and the densevol export.
# They must never diverge: the padded box is sized to the active region AT THESE
# VALUES, so exporting at a lower (more inclusive) threshold would silently push
# condensate outside the box and clip it. The bbox tool imports these constants
# and builds channels through the same code path as the exporter.
THRESHOLDS = {
    "cloud": 1.0e-4,       # kg/kg (0.1 g/kg -- conventional visible cloud edge)
    "ice": 1.0e-4,
    "rain": 1.0e-4,
    "graupelhail": 1.0e-4,
    "dbz": 5.0,            # dBZ
}

# --- export grid ------------------------------------------------------------
# 250 m isotropic (docs/phase1-svt-budget.md). HONEST CAVEAT: the sim ran at
# 500 m, so this UPSAMPLES 2x and adds no physical detail. That is intended --
# the spike tests the writer->SVT streaming path at realistic data volume and
# frame count, not science-grade fine structure.
EXPORT_VOXEL_M = 250.0

# Fixed padded box, in CM1 world coordinates (SI metres, origin at domain centre).
# Horizontal: measured union half-width was 24.25 km at THRESH=1e-6 (a superset of
# the 1e-4 export threshold), so 26 km pads it with margin. The cell is centred and
# stationary (imove=0), so a symmetric box keeps the bbox CENTRE STATIC AT (0,0) --
# the SVT constraint is satisfied by construction, not by luck.
# Vertical: measured union top was 16.75 km; padded to 18 km (a 1-voxel margin was
# judged too tight against threshold sensitivity).
CROP_HALF_WIDTH_M = 26000.0
CROP_Z_TOP_M = 18000.0

# Derived grid dimensions -> 208 x 208 x 72.
NX = int(round(2 * CROP_HALF_WIDTH_M / EXPORT_VOXEL_M))
NY = NX
NZ = int(round(CROP_Z_TOP_M / EXPORT_VOXEL_M))

# World coords of the CENTRE of voxel (0,0,0). dense2vdb post-translates the
# shared transform by this, so the VDB carries true CM1 coordinates (SI metres).
# The metres->centimetres + Y-flip conversion to UE space is applied at ACTOR
# PLACEMENT, not here -- see docs/phase1-task3-svt-import.md.
#
# OpenVDB's linear transform maps index -> world at voxel CENTRES, so the origin
# is derived (not hand-set) to make the centres symmetric about x=y=0. This is
# what pins the bbox centre to exactly (0,0) for every frame -- the SVT
# static-centre constraint. Horizontal extremes land at +/-25875 m, still outside
# the measured 24250 m union half-width.
ORIGIN_M = (
    -(NX - 1) / 2.0 * EXPORT_VOXEL_M,   # -25875.0
    -(NY - 1) / 2.0 * EXPORT_VOXEL_M,   # -25875.0
    EXPORT_VOXEL_M / 2.0,               # 125.0 -- first cell centre above ground
)
