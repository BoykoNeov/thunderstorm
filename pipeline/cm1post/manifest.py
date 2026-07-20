"""Scenario-package manifest -- the contract UE reads.

UE must be able to render the package knowing nothing about CM1: the channel->SVT
texture mapping, the transform, the units, and the per-frame storm times all live
here. UE refuses a newer major format_version (see scenarios/README.md).
"""
import json

from . import contract

# Re-exported for callers that still import it from here; the definition lives in
# contract.py because it is frozen by format_version, not chosen per scenario.
SVT_TEXTURE_MAP = contract.SVT_TEXTURE_MAP


def build(sc, frames, provenance):
    """sc: Scenario. frames: list of {index, time_s, file, bytes}."""
    return {
        "format_version": contract.FORMAT_VERSION,
        "scenario": sc.name,
        "kind": sc.kind,
        "phase": sc.phase,

        "units": {
            "length": "m",
            "note": ("All geometry is CM1-native SI: metres, z-up, right-handed. "
                     "The metres->centimetres and Y-flip conversion into UE space is "
                     "applied at ACTOR PLACEMENT in the UE app, never baked into the "
                     "data (single-conversion-site rule)."),
        },

        "volume": {
            "voxel_size_m": sc.export_voxel_m,
            "dimensions": [sc.nx, sc.ny, sc.nz],
            "origin_m": list(sc.origin_m),
            "origin_note": ("World coords of the CENTRE of voxel (0,0,0); the VDB's "
                            "shared linear transform carries this translation."),
            "bbox_center_m": [0.0, 0.0, sc.crop_z_top_m / 2.0],
            "bbox_center_static": True,
            "extent_m": {
                "x": [-sc.crop_half_width_m, sc.crop_half_width_m],
                "y": [-sc.crop_half_width_m, sc.crop_half_width_m],
                "z": [0.0, sc.crop_z_top_m],
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
                "PROVEN ON A REAL GPU 2026-07-15/16 -- the storm renders full-size "
                "(46.5 km) at the correct location under this rule "
                "(docs/session-handoff-2026-07-15-visuals.md, "
                "docs/phase1-svt-streaming-views-rootcause.md). "
                "(1) Read placement from the IMPORTED ASSET's frame transform "
                "(svt.get_frame_transform()), never from origin_m here: UE's factory "
                "trims and re-bases the box, so origin_m describes the VDB on disk, "
                "not the asset; adding it on top double-applies and lands the volume "
                "2750 m off in X/Y. Take any vertical-exaggeration pivot from the "
                "asset too. "
                "(2) On a real RHI the HeterogeneousVolumeComponent applies the "
                "asset's frame transform ITSELF (voxel scale + translation; earlier "
                "-nullrhi-derived claims to the contrary were wrong). The actor "
                "therefore carries ONLY the units conversion: actor scale = 100 "
                "(m -> cm), location = (0,0,0), rotation identity. Do NOT multiply "
                "by frame.scale3d -- that double-applies the 250 m/voxel scale and "
                "renders the volume 250x oversized. "
                "(3) OPEN -- the Y-flip (CM1 right-handed -> UE left-handed) is not "
                "yet applied or verified; the candidate is actor scale.y = -100, to "
                "be confirmed against a known-asymmetric storm feature before Phase 2 "
                "placement code ships. "
                "(4) Playback: leave the component's bIssueBlockingRequests at its "
                "engine default (false) -- blocking requests do not stream in-editor "
                "and stall the volume at lowest mip."),
        },

        "channels": {
            "order": contract.CHANNELS,
            "sources": contract.SOURCE_FIELDS,
            "thresholds": contract.THRESHOLDS,
            "threshold_note": ("Voxels at/below these values are inactive VDB "
                               "background. The padded bbox was sized to the active "
                               "region AT THESE VALUES -- lowering one without "
                               "re-sweeping the bbox can push condensate outside the "
                               "box and silently clip it."),
            "svt_texture_map": contract.SVT_TEXTURE_MAP,
        },

        "web": {
            "dir": contract.WEB_DIR,
            "manifest": contract.WEB_MANIFEST,
            "web_format_version": contract.WEB_FORMAT_VERSION,
            "consumer": "diorama/ -- the Storm Diorama web viewer (a second 'dumb "
                        "player' of this same package; see "
                        "docs/design-diorama-web-viewer-2026-07-16.md).",
            # Deliberately does NOT enumerate the per-frame files or channels: that
            # would be a census in prose, stale the moment a field is added to the
            # web export, and invisible to the structured census check in
            # pipeline/tests/test_manifest.py.
            "content": ("A RENDITION of the same volumes as vdb/, from the same "
                        "fields/regrid code path: gzipped uint8-quantized raw bricks. "
                        "See web_manifest.json for the current per-frame files, "
                        "channels and encodings. Not a substitute for vdb/ -- it is "
                        "lossily quantized for the web."),
            "authority": ("POINTER, NOT A CENSUS. Grid, encoding, per-channel qmax "
                          "and the frame list are NOT copied here; web_manifest.json "
                          "is authoritative for the rendition. Nothing is duplicated, "
                          "so nothing can drift out of sync with it."),
            "presence": ("web/ is REGENERABLE and gitignored, so it is absent from a "
                         "fresh clone until `export_scenario.py export-web` is run "
                         "(scenarios/README.md). This block declares that the "
                         "rendition BELONGS to the package -- not that the files are "
                         "on disk right now."),
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
        "source_run": sc.run_dir,
        "frame_count": len(frames),
        "frames": frames,
    }


def write(path, doc):
    # newline="\n": this file is written by the WSL pipeline but is occasionally
    # rebuilt in place from Windows (the pure-function trick in
    # pipeline/tests/test_manifest.py). Without this, Windows text mode rewrites
    # every LF as CRLF and the working file stops matching what the exporter
    # produces -- invisible to any gate that reads back in universal-newline mode.
    with open(path, "w", newline="\n") as f:
        json.dump(doc, f, indent=1)
