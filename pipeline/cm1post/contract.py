"""The scenario-package FORMAT CONTRACT -- frozen, identical for every scenario.

This module holds everything that is fixed by `format_version` rather than chosen
per scenario. The split from `scenario.py` is the central design decision of the
Phase 2 scenario system (docs/phase2-plan-2026-07-20.md §4), and it exists to stop a
frozen quantity from drifting per scenario:

  * Channel NAMES and ORDER are frozen because task 3 proved UE 5.8's default
    grid->SVT assignment reproduces this exact map (docs/phase1-task3-svt-import.md).
    Renaming or reordering a channel forces an SVT import re-test.
  * THRESHOLDS are frozen because the padded bbox is SIZED at these values. A
    per-scenario override would decouple the bbox sweep from the export and silently
    clip the storm -- exactly the class of error the Phase 1 spike caught twice
    (docs/phase1-completion-2026-07-20.md §3).

Per-scenario geometry (voxel size, crop box, run dir) lives in `scenario.py`.
"""

# Scenario-package format contract version (the manifest carries this; UE refuses a
# newer MAJOR version). Bumped when the package layout or channel map changes.
FORMAT_VERSION = "1.0"

# --- channel map (docs/phase1-svt-budget.md) --------------------------------
CHANNELS = ["cloud", "ice", "rain", "graupelhail", "dbz"]

# What each rendered channel is MADE OF, in CM1/NSSL ptype=27 terms.
# Two channels merge physically-similar categories that read as one thing in a
# volume render (the split stays recoverable in the 3 spare SVT channels):
#   ice         = qi (cloud ice) + qs (snow)   -- one glaciated "anvil" category.
#                 Not optional: measured qs/qi ~ 0.29-0.53 by mass and snow fills
#                 as many voxels as ice, so dropping qs visibly thins the anvil.
#                 (The Phase 1 spike caught `ice = qi` silently dropping snow.)
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

# Which rendered channel lands in which SVT texture/component. Task 3 confirmed UE
# 5.8's factory reproduces this assignment from grid order
# (docs/phase1-task3-svt-import.md). Tex B has 3 spare channels (G/B/A).
SVT_TEXTURE_MAP = {
    "A": {"format": "RGBA16F", "R": "cloud", "G": "ice", "B": "rain", "A": "graupelhail"},
    "B": {"format": "R16F", "R": "dbz"},
}
