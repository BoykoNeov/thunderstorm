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
                "Read placement from the IMPORTED ASSET's frame transform "
                "(svt.get_frame_transform()), never from origin_m here. Adding origin_m "
                "on top double-applies it and lands the volume 2750 m off in X/Y. "
                "Likewise take any vertical-exaggeration pivot from the asset, not from "
                "bbox_center_m. NOTE (measured 2026-07-15, docs/phase1-task5-pipeline.md): "
                "UE does NOT auto-apply that frame transform -- "
                "HeterogeneousVolumeComponent lays the volume out at 1 voxel = 1 UE unit, "
                "so an actor left at identity renders a 1.9 m storm at the world origin. "
                "The actor must apply the asset's frame transform AND the units "
                "conversion: scale = frame.scale3d * 100 (m->cm), location = "
                "frame.translation * 100 with Y negated. That is the single conversion "
                "site; it reads the asset, not this manifest."),
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
