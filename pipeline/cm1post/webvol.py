"""Write the web-viewer volume export (diorama/ consumes this).

Per-frame format (design: docs/design-diorama-web-viewer-2026-07-16.md):
gzipped raw bricks, no container header -- everything the reader needs lives in
web_manifest.json. Two files per frame:

  fNNNN.rgba.gz  interleaved uint8 RGBA = (cloud, ice, rain, graupelhail),
                 x fastest, then y, then z -- exactly WebGL texImage3D order
                 for a (NX, NY, NZ) 3D texture.
  fNNNN.dbz.gz   uint8 R, same order (diagnostic layer, optional to load).

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

    return {
        "rgba": os.path.basename(rgba_path),
        "dbz": os.path.basename(dbz_path),
        "rgba_bytes": os.path.getsize(rgba_path),
        "dbz_bytes": os.path.getsize(dbz_path),
    }


def build_manifest(sc, frames, qmax):
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
        "frames": frames,
    }


def write_manifest(path, doc):
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
