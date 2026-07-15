"""Write a .densevol frame (the dense-array handoff dense2vdb consumes).

Format is defined in pipeline/vdbwriter/README.md and dense2vdb.cpp. Little-endian,
native x86 (WSL only). Channel order and per-channel thresholds are the format
contract -- both come from config, never from a caller.
"""
import struct

from . import config


def write(path, channels):
    """channels: dict name -> float32 (nz, ny, nx), C-order (x fastest)."""
    ox, oy, oz = config.ORIGIN_M
    with open(path, "wb") as f:
        f.write(b"DVOL")
        f.write(struct.pack("<I", 1))                       # version
        f.write(struct.pack("<III", config.NX, config.NY, config.NZ))
        f.write(struct.pack("<I", len(config.CHANNELS)))
        f.write(struct.pack("<f", config.EXPORT_VOXEL_M))
        f.write(struct.pack("<fff", ox, oy, oz))
        for name in config.CHANNELS:
            arr = channels[name]
            if arr.shape != (config.NZ, config.NY, config.NX):
                raise ValueError(f"{name}: shape {arr.shape} != export grid")
            nb = name.encode("ascii")
            f.write(struct.pack("<I", len(nb)))
            f.write(nb)
            f.write(struct.pack("<f", config.THRESHOLDS[name]))
            f.write(arr.tobytes())
