"""Scenario-package manifest -- the contract UE reads.

UE must be able to render the package knowing nothing about CM1: the channel->SVT
texture mapping, the transform, the units, and the per-frame storm times all live
here. UE refuses a newer major format_version (see scenarios/README.md).
"""
import json

from . import config

# Which rendered channel lands in which SVT texture/component. Task 3 confirmed UE
# 5.8's factory reproduces this assignment from grid order (docs/phase1-task3-svt-import.md).
SVT_TEXTURE_MAP = {
    "A": {"format": "RGBA16F", "R": "cloud", "G": "ice", "B": "rain", "A": "graupelhail"},
    "B": {"format": "R16F", "R": "dbz"},
}


def build(scenario, source_run, frames, provenance):
    """frames: list of {index, time_s, file, bytes}."""
    return {
        "format_version": config.FORMAT_VERSION,
        "scenario": scenario,
        "kind": "single_cell",
        "phase": "phase1-spike",

        "units": {
            "length": "m",
            "note": ("All geometry is CM1-native SI: metres, z-up, right-handed. "
                     "The metres->centimetres and Y-flip conversion into UE space is "
                     "applied at ACTOR PLACEMENT in the UE app, never baked into the "
                     "data (single-conversion-site rule)."),
        },

        "volume": {
            "voxel_size_m": config.EXPORT_VOXEL_M,
            "dimensions": [config.NX, config.NY, config.NZ],
            "origin_m": list(config.ORIGIN_M),
            "origin_note": ("World coords of the CENTRE of voxel (0,0,0); the VDB's "
                            "shared linear transform carries this translation."),
            "bbox_center_m": [0.0, 0.0, config.CROP_Z_TOP_M / 2.0],
            "bbox_center_static": True,
            "extent_m": {
                "x": [-config.CROP_HALF_WIDTH_M, config.CROP_HALF_WIDTH_M],
                "y": [-config.CROP_HALF_WIDTH_M, config.CROP_HALF_WIDTH_M],
                "z": [0.0, config.CROP_Z_TOP_M],
            },
            "ue_import_note": (
                "These numbers describe the VDB ON DISK. UE 5.8's SVT factory does NOT "
                "import the padded box as authored: it unions the active voxels across "
                "the whole sequence, tightens the volume to that union, and re-bases the "
                "transform translation by exactly trimmed_voxels * voxel_size. Measured "
                "on this package (docs/phase1-task5-pipeline.md): 208x208x72 @ origin "
                "-25875 arrives as 186x186x65 @ -23125, z-centre 8125 (not 9000). No data "
                "is lost -- only empty pad -- and the index->world mapping is preserved "
                "exactly, so the active volume lands at identical CM1 world coordinates."),
            "ue_placement_rule": (
                "WARNING -- UNPROVEN AS OF 2026-07-15. Do not implement Phase 2 placement "
                "from this field yet; see docs/phase1-task5-pipeline.md 'Render "
                "investigation'. The volume DOES NOT RENDER on a real GPU at any density "
                "(swept 2e-4..1e6), so no placement claim below has been confirmed by "
                "looking at a storm. Two parts are known: "
                "(1) SOLID -- read placement from the IMPORTED ASSET's frame transform "
                "(svt.get_frame_transform()), never from origin_m here. UE's factory "
                "trims and re-bases the box, so origin_m describes the VDB on disk, not "
                "the asset; adding it on top double-applies and lands the volume 2750 m "
                "off in X/Y. Take any vertical-exaggeration pivot from the asset too. "
                "(2) BROKEN -- the transform the actor must then apply. UE does not "
                "auto-apply the asset's frame transform (HeterogeneousVolumeComponent "
                "lays the volume out at 1 voxel = 1 UE unit), so the actor carries it, "
                "but the mapping as previously written here is WRONG: negating "
                "frame.translation.y MOVES the box instead of MIRRORING it (the volume "
                "extends +Y from its corner), landing the storm ~46 km off-axis -- "
                "measured bounds centre y = +4637500 cm where x centred at ~125 cm. "
                "Mirroring the far corner (location.y = -(translation.y + span_y) * 100) "
                "is the likely fix, UNVERIFIED. The scale (frame.scale3d * 100, i.e. "
                "25000x) is also a live suspect for the invisible volume. "
                "What survives regardless: the conversion happens at ONE site, and it "
                "reads the asset, not this manifest."),
        },

        "channels": {
            "order": config.CHANNELS,
            "sources": config.SOURCE_FIELDS,
            "thresholds": config.THRESHOLDS,
            "threshold_note": ("Voxels at/below these values are inactive VDB "
                               "background. The padded bbox was sized to the active "
                               "region AT THESE VALUES -- lowering one without "
                               "re-sweeping the bbox can push condensate outside the "
                               "box and silently clip it."),
            "svt_texture_map": SVT_TEXTURE_MAP,
        },

        "diagnostics": {
            "dbz": {
                "source": "CM1 output_dbz=1, computed by the NSSL 2-moment scheme "
                          "(ptype=27) from its own hydrometeor distributions.",
                "citation": "Mansell, Ziegler & Bruning (2010), J. Atmos. Sci. 67, "
                            "276-299; Ziegler (1985), J. Atmos. Sci. 42, 1487-1509.",
                "feedback": "none -- diagnostic only, never fed back into the simulation",
                "caveat": ("dBZ is logarithmic; the 500->250 m resample interpolates in "
                           "dB rather than linear Z, which slightly smooths gradients at "
                           "echo edges. Acceptable for a plumbing spike; revisit if dBZ "
                           "is ever used quantitatively in the UI."),
            },
        },

        "provenance": provenance,
        "source_run": source_run,
        "frame_count": len(frames),
        "frames": frames,
    }


def write(path, doc):
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
