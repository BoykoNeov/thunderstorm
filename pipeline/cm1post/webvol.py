"""Write the web-viewer volume export (diorama/ consumes this).

Per-frame format (design: docs/design-diorama-web-viewer-2026-07-16.md):
gzipped raw bricks, no container header -- everything the reader needs lives in
web_manifest.json. Files per frame (the set GROWS -- T4 added `w`; the manifest's
frame records are authoritative, this list is orientation):

  fNNNN.rgba.gz  interleaved uint8 RGBA = (cloud, ice, rain, graupelhail),
                 x fastest, then y, then z -- exactly WebGL texImage3D order
                 for a (NX, NY, NZ) 3D texture.
  fNNNN.dbz.gz   uint8 R, same order (diagnostic layer, optional to load).
  fNNNN.w.gz     uint8 R, same order -- vertical velocity, SIGNED, so it gets its
                 own plane and its own encoding rather than a slot in the rgba
                 interleave (contract.WEB_EXTRA_FIELDS).
  fNNNN.cref.gz  uint8 R, 2D (NX, NY), x fastest -- composite reflectivity, a PLAN
                 product with no z axis at all (contract.WEB_PLAN_FIELDS). Same file
                 shape as the above, different RANK; the manifest says which.

Quantization is a per-channel LOG map: mixing ratios span ~1e-4..1e-2 kg/kg and a
linear byte map would crush the anvil into 2-3 codes.

  q <= threshold        -> 0
  q in (thr, qmax]      -> 1 + round(254 * log(q/thr) / log(qmax/thr))

The decode (viewer, mirrored in a vitest test) is
  q = thr * (qmax/thr) ** ((v - 1) / 254)          for v > 0.

qmax is the per-channel maximum over the WHOLE sequence, measured on the CM1
source grid: linear resampling can only decrease a maximum, so the source-grid
max is a safe (>=) bound for every resampled frame, and one cheap scan pass
replaces a two-pass export. dBZ is mapped linearly (it is already a log-scale
quantity) over (thr, dbzmax].

This module quantizes already-exported render channels -- presentation-side
decimation in the same category as the charter's int16 packing. No science here.
"""
import gzip
import json
import os

import numpy as np

from . import contract

# Re-exported for callers that still import it from here; the definition lives in
# contract.py because it is frozen by the format contract, not chosen per scenario
# (the same reason SVT_TEXTURE_MAP moved there in T1).
WEB_FORMAT_VERSION = contract.WEB_FORMAT_VERSION

# Mixing-ratio channels, in the fixed RGBA plane order of the .rgba.gz files.
RGBA_CHANNELS = ["cloud", "ice", "rain", "graupelhail"]

GZIP_LEVEL = 6


def encode_log_u8(q, thr, qmax):
    """float32 field -> uint8 log-quantized (0 = below threshold)."""
    if qmax <= thr:
        return np.zeros(q.shape, dtype=np.uint8)
    v = np.zeros(q.shape, dtype=np.uint8)
    m = q > thr
    if m.any():
        t = np.log(q[m] / thr) / np.log(qmax / thr)
        v[m] = np.clip(np.rint(1.0 + 254.0 * t), 1, 255).astype(np.uint8)
    return v


def encode_linear_u8(q, thr, vmax):
    """float32 field -> uint8 linear-quantized over (thr, vmax] (for dBZ)."""
    if vmax <= thr:
        return np.zeros(q.shape, dtype=np.uint8)
    v = np.zeros(q.shape, dtype=np.uint8)
    m = q > thr
    if m.any():
        t = (q[m] - thr) / (vmax - thr)
        v[m] = np.clip(np.rint(1.0 + 254.0 * t), 1, 255).astype(np.uint8)
    return v


def encode_signed_u8(w, scale):
    """SIGNED float32 field -> uint8 linear, symmetric about code 128 (Phase 2 T4).

    v = 128 + round(127 * clip(w, -scale, +scale) / scale)   ->  codes 1..255

    Symmetric-about-128 rather than an affine map over the observed [wmin, wmax],
    and that is the whole design decision. An affine map would use every code, but
    w = 0 would land on a FRACTIONAL code, so no byte decodes to exactly zero and
    the updraft/downdraft boundary -- the one feature a viewer actually reads off
    this field -- would sit at a rounded, scenario-dependent place and paint a thin
    band of false vertical motion along it. Pinning 0 to an exact integer code costs
    only the unused negative headroom.

    `scale` is FIXED cross-scenario (contract.W_ENCODE_SCALE_M_S), so the same code
    means the same m/s in every package. Clipping first means code 0 never occurs:
    the representable range is exactly [-scale, +scale] on codes 1..255, with no
    sentinel value to confuse a decoder. Values beyond the scale would be clipped,
    so the exporter checks the observed range against it and says so loudly.
    """
    ww = np.clip(w.astype(np.float64), -scale, scale)
    return np.clip(np.rint(128.0 + 127.0 * ww / scale), 0, 255).astype(np.uint8)


def decode_signed_u8(v, scale):
    """Inverse of encode_signed_u8 (reference decode; T8's GLSL will mirror this)."""
    return (v.astype(np.float64) - 128.0) / 127.0 * scale


def decode_log_u8(v, thr, qmax):
    """Inverse of encode_log_u8 (reference decode; the GLSL mirrors this)."""
    q = np.zeros(v.shape, dtype=np.float64)
    m = v > 0
    q[m] = thr * (qmax / thr) ** ((v[m].astype(np.float64) - 1.0) / 254.0)
    return q


def write_frame(out_dir, index, channels):
    """channels: dict name -> uint8 (nz, ny, nx). Returns manifest record fields."""
    rgba = np.stack([channels[c] for c in RGBA_CHANNELS], axis=-1)  # (z,y,x,4)
    rgba_path = os.path.join(out_dir, f"f{index:04d}.rgba.gz")
    with gzip.open(rgba_path, "wb", compresslevel=GZIP_LEVEL) as f:
        f.write(np.ascontiguousarray(rgba).tobytes())

    dbz_path = os.path.join(out_dir, f"f{index:04d}.dbz.gz")
    with gzip.open(dbz_path, "wb", compresslevel=GZIP_LEVEL) as f:
        f.write(np.ascontiguousarray(channels["dbz"]).tobytes())

    rec = {
        "rgba": os.path.basename(rgba_path),
        "dbz": os.path.basename(dbz_path),
        "rgba_bytes": os.path.getsize(rgba_path),
        "dbz_bytes": os.path.getsize(dbz_path),
    }

    # Extra fields (T4): separate single-plane files, so a viewer that does not
    # implement a layer never downloads it. `w` is signed and cannot ride in the
    # 4-channel rgba plane, which is why this is a file rather than a component.
    #
    # Plan fields (T5) are written by the same loop but from a separate dict: the
    # file shape is identical (one gzipped uint8 plane), only the RANK of what is
    # inside differs, and that is declared in the manifest block, not the filename.
    for name in list(contract.WEB_EXTRA_FIELDS) + list(contract.WEB_PLAN_FIELDS):
        path = os.path.join(out_dir, f"f{index:04d}.{name}.gz")
        with gzip.open(path, "wb", compresslevel=GZIP_LEVEL) as f:
            f.write(np.ascontiguousarray(channels[name]).tobytes())
        rec[name] = os.path.basename(path)
        rec[f"{name}_bytes"] = os.path.getsize(path)

    return rec


def build_manifest(sc, frames, qmax, observed=None):
    """web_manifest.json contents -- the whole reader contract."""
    return {
        "web_format_version": WEB_FORMAT_VERSION,
        "package_format_version": contract.FORMAT_VERSION,
        "source_run": sc.run_dir,
        "grid": {
            "nx": sc.nx, "ny": sc.ny, "nz": sc.nz,
            "voxel_m": sc.export_voxel_m,
            # World coords (CM1 SI metres) of the CENTRE of voxel (0,0,0).
            "origin_m": list(sc.origin_m),
        },
        "volume": {
            "layout": "rgba8, x fastest, then y, then z (WebGL texImage3D order)",
            "channels": [
                {
                    "name": c,
                    "plane": i,
                    "encoding": "log-uint8",
                    "threshold": contract.THRESHOLDS[c],
                    "qmax": qmax[c],
                    "units": "kg/kg",
                }
                for i, c in enumerate(RGBA_CHANNELS)
            ],
        },
        "dbz": {
            "encoding": "linear-uint8",
            "threshold": contract.THRESHOLDS["dbz"],
            "vmax": qmax["dbz"],
            "units": "dBZ",
            "diagnostic": True,
        },
        "extra_fields": {
            name: {
                "file_suffix": f".{name}.gz",
                "encoding": spec["encoding"],
                "units": spec["units"],
                "cm1_var": spec["cm1_var"],
                "diagnostic": spec["diagnostic"],
                # The decode, stated in full so a reader never has to guess it.
                "scale": spec["scale_m_s"],
                "decode": ("value = (byte - 128) / 127 * scale; codes 1..255 span "
                           "[-scale, +scale] and byte 128 is EXACTLY zero, so the "
                           "updraft/downdraft boundary is exact rather than rounded."),
                "scale_note": ("FIXED across all scenarios, not fitted per sequence: "
                               "the same colour means the same m/s in every package, "
                               "which is what makes updraft strength comparable "
                               "between scenarios by eye. Values are CLIPPED to "
                               "+/-scale on encode; the exporter verifies the "
                               "observed range fits."),
                # Recorded so a legend can state the REAL range of this sequence,
                # which the fixed scale deliberately does not tell you.
                "observed_min": (observed or {}).get(name, {}).get("min"),
                "observed_max": (observed or {}).get(name, {}).get("max"),
                "crop_caveat": (
                    "This field is cropped to the SAME box as the hydrometeor "
                    "volumes, and that box was sized to the CONDENSATE (see the "
                    "package manifest's threshold_note). Vertical motion exists "
                    "outside it: broad, weak environmental subsidence around the "
                    "storm is not included. The storm-scale updraft and downdraft "
                    "core are -- see docs/phase2-plan-2026-07-20.md for the measured "
                    "fraction. The box was NOT resized for this field: it is shared "
                    "with the VDB rendition, whose bbox centre must stay static "
                    "across the sequence for the UE SVT contract."),
            }
            for name, spec in contract.WEB_EXTRA_FIELDS.items()
        },
        # 2D plan products (T5). A SEPARATE block from extra_fields, not a `dims` key
        # inside it: a reader must know the rank before it touches the bytes, and a
        # reader that branches wrongly uploads a (ny*nx) buffer into a 3D texture and
        # renders garbage rather than failing. See contract.WEB_PLAN_FIELDS.
        "plan_fields": {
            name: {
                "file_suffix": f".{name}.gz",
                "encoding": spec["encoding"],
                "units": spec["units"],
                "cm1_var": spec["cm1_var"],
                "diagnostic": spec["diagnostic"],
                # Rank and layout, stated because this block's whole reason to exist
                # separately is that they differ from the volume blocks above.
                "dims": ["y", "x"],
                "layout": ("uint8 R, x fastest then y -- a (NX, NY) 2D plane. NOT a "
                           "volume: this is a plan (map) product, already collapsed "
                           "over the column."),
                "threshold": contract.THRESHOLDS[spec["threshold_from"]],
                "vmax": qmax[spec["vmax_from"]],
                "decode": ("value = threshold + (byte - 1) / 254 * (vmax - threshold) "
                           "for byte > 0; byte 0 means BELOW threshold (no echo). "
                           "Identical to the dbz decode, deliberately."),
                "scale_note": (
                    "threshold and vmax are SHARED with the 3D dbz layer, so one byte "
                    "means one dBZ in both and a single colormap serves both. This is "
                    "exact, not approximate: CM1's cref was measured bitwise identical "
                    "to dbz.max(axis=0) over all frames, so the two fields have the "
                    "same sequence maximum by identity."),
                "observed_min": (observed or {}).get(name, {}).get("min"),
                "observed_max": (observed or {}).get(name, {}).get("max"),
                "view_independence_note": (
                    "COMPOSITE REFLECTIVITY: the maximum dBZ in each vertical column, "
                    "independent of the viewing direction. This is the standard radar "
                    "plan product and is NOT the same thing as the viewer's 3D dBZ "
                    "layer, which is a maximum along the VIEW RAY and therefore "
                    "changes as the camera orbits. Both ship in this package; a UI "
                    "must label them distinctly."),
                "crop_caveat": (
                    "Horizontally this field is cropped to the SAME box as the "
                    "volumes, and above the shared dBZ threshold that crop is lossless "
                    "by construction: cref exceeds the threshold at (x,y) exactly when "
                    "some dbz in that column does, and the box is sized to contain "
                    "every such voxel. Vertically, cref is CM1's full-column maximum "
                    "while the exported volume stops at the box top -- but MEASURED "
                    "over all 301 frames of this run, the peak dBZ anywhere above the "
                    "box top is 0.0000, so that truncation costs cref exactly nothing "
                    "here. See docs/phase2-plan-2026-07-20.md; re-measure for a "
                    "scenario with a deeper storm or a lower box."),
                "vs_volume_note": (
                    "cref can still read slightly HOTTER than the column maximum of "
                    "the 3D dbz layer, by up to ~2 dB in this run. That is not an "
                    "inconsistency: cref is max-then-resample while a column max of "
                    "the volume is resample-then-max, and the former dominates "
                    "whenever the strongest echo sits at different heights in "
                    "neighbouring columns. cref is the correct composite reflectivity; "
                    "the column max of a resampled volume is not."),
            }
            for name, spec in contract.WEB_PLAN_FIELDS.items()
        },
        "frames": frames,
    }


def write_manifest(path, doc):
    with open(path, "w", newline="\n") as f:  # LF always -- see manifest.write()
        json.dump(doc, f, indent=1)
