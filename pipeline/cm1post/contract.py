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
# newer MAJOR version -- see scenarios/README.md).
#
# Versioning rule, made explicit at the 1.1 bump so the next one is mechanical:
#   MINOR -- ADDITIVE and back-compatible. New manifest keys a 1.0 reader can ignore
#            and still render the package correctly. A 1.0-era reader MUST keep
#            working on a 1.1 package; that is what makes the bump UE-safe while the
#            UE app is deferred and cannot be re-tested.
#   MAJOR -- anything a reader cannot ignore: channel names/order, the SVT texture
#            map, encodings, the transform/units contract, package layout.
#
# 1.1 (2026-07-20, Phase 2 T2): added the manifest `web` block -- a POINTER to the
#     web rendition, declaring that `web/` belongs to the package. Purely additive;
#     no data, no channel, no encoding changed, so no SVT import re-test is implied.
# NOT bumped by Phase 2 T3 (linear-Z dbz), deliberately -- the rule above is about
#     FORMAT compatibility, and T3 changed dbz VALUES, not the format. No channel name,
#     order, encoding, texture map or layout moved; a 1.0-era reader renders a T3
#     package correctly. The method is recorded where a consumer actually looks for it,
#     `manifest.diagnostics.dbz.resampling` -- which makes a bump redundant, and a
#     version number that moves for data changes stops meaning "format".
FORMAT_VERSION = "1.1"

# Version of the web-rendition brick format (web/web_manifest.json carries this, and
# diorama/src/volume.ts refuses a newer MAJOR). Frozen by the format contract rather
# than chosen per scenario, so it lives here; webvol.py re-exports it.
# NOT bumped at package 1.1 (T2): the brick layout, quantization and reader contract
#     were byte-for-byte unchanged -- a pointer block is not a format change.
# 1.1 (2026-07-20, Phase 2 T4): added the `w` (updraft) extra field -- a NEW per-frame
#     file and a NEW manifest block. This IS additive format growth, unlike T3: T3
#     changed dbz VALUES inside existing files (data), T4 grows the file set and the
#     reader contract (format). A 1.0-era viewer ignores both and still renders, which
#     is exactly what MINOR means. Feature detection belongs on the PRESENCE of the
#     `w` block, not on this number: the version declares the generation, the key
#     declares the capability.
WEB_FORMAT_VERSION = "1.1"

# Where the web rendition lives inside a package, and what reads it. The manifest's
# `web` block is built from these; the diorama dev server resolves the same path
# (diorama/vite.config.ts -> ../scenarios/<name>/web).
WEB_DIR = "web/"
WEB_MANIFEST = "web/web_manifest.json"

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

# --- extra web-export fields (NOT SVT channels) -----------------------------
# The second export path introduced by Phase 2 T4 (plan §7). These fields ship in the
# WEB rendition only; `CHANNELS` and `SVT_TEXTURE_MAP` above stay frozen because
# changing them forces an SVT import re-test that cannot happen while the editor is
# owner-gated (and `-nullrhi` is structurally incapable of validating a render).
# Tex B keeps 3 spare channels for a deliberate, re-tested promotion later.
#
# These constants are FROZEN here rather than chosen per scenario for the same reason
# THRESHOLDS are: a per-scenario encode scale would make the same colour mean
# different m/s in different packages, silently defeating the cross-scenario
# comparison that T6 exists to enable.
#
# `w` is UNLIKE every channel above in three ways, and each one costs a decision:
#   SIGNED    -- downdrafts are the physically interesting half. The generic
#                `regrid.resample` CLIPS AT 0 and would silently delete all of them,
#                so `w` must route through `regrid.resample_signed`.
#   DENSE     -- mixing ratios are ~0 almost everywhere and earn a threshold-to-zero
#                sentinel; w is nonzero nearly everywhere. There is no sparsity to
#                exploit and no threshold: any "|w| < eps is transparent" deadband is
#                a RENDER-time decision (T8), never baked into the byte, which would
#                discard weak-w data irreversibly at the wrong layer.
#   NOT LOG   -- w spans ~1e2, not the ~1e4 of the mixing ratios, so a linear map
#                does not crush it the way it would crush the anvil.
W_ENCODE_SCALE_M_S = 80.0
"""Fixed, cross-scenario full-scale for the signed-uint8 `w` encoding (m/s).

Chosen FIXED rather than per-sequence (the `qmax` pattern) so that the same colour
means the same vertical velocity in every package -- updraft strength becomes
comparable by eye across scenarios, which is the teaching payload.

80 m/s is empirical headroom, not a round number: the Phase 1 single cell peaks at
+52.5 m/s, but the Phase 0 validated supercell reached +60.6 m/s
(docs/phase0-validation.md). A per-sequence scale would therefore ALREADY disagree
between two runs this project has made, and a 60 m/s fixed scale would already clip
one of them. Resolution is 80/127 = 0.63 m/s per code -- far finer than any
vertical velocity this app asks a viewer to read off a colour.
"""

WEB_EXTRA_FIELDS = {
    "w": {
        "cm1_var": "winterp",   # w ALREADY interpolated to scalar points by CM1:
                                # same grid as the hydrometeors, so no destaggering
                                # here. The raw staggered `w` on zf is ignored.
        "encoding": "signed-linear-uint8",
        "units": "m/s",
        "scale_m_s": W_ENCODE_SCALE_M_S,
        "diagnostic": False,    # w is a PROGNOSTIC simulation field, not a diagnostic
                                # like dbz -- it is what the model solved for.
    },
}

# Which rendered channel lands in which SVT texture/component. Task 3 confirmed UE
# 5.8's factory reproduces this assignment from grid order
# (docs/phase1-task3-svt-import.md). Tex B has 3 spare channels (G/B/A).
SVT_TEXTURE_MAP = {
    "A": {"format": "RGBA16F", "R": "cloud", "G": "ice", "B": "rain", "A": "graupelhail"},
    "B": {"format": "R16F", "R": "dbz"},
}
