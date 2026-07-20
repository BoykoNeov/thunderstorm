"""Write a .densevol frame (the dense-array handoff dense2vdb consumes).

Format is defined in pipeline/vdbwriter/README.md and dense2vdb.cpp. Little-endian,
native x86 (WSL only). Channel order and per-channel thresholds are the format
contract -- both come from `contract`, never from a caller. Grid geometry comes
from the Scenario.
"""
import struct

from . import contract


def write(path, sc, channels):
    """channels: dict name -> float32 (nz, ny, nx), C-order (x fastest)."""
    ox, oy, oz = sc.origin_m
    with open(path, "wb") as f:
        f.write(b"DVOL")
        f.write(struct.pack("<I", 1))                       # version
        f.write(struct.pack("<III", sc.nx, sc.ny, sc.nz))
        f.write(struct.pack("<I", len(contract.CHANNELS)))
        f.write(struct.pack("<f", sc.export_voxel_m))
        f.write(struct.pack("<fff", ox, oy, oz))
        for name in contract.CHANNELS:
            arr = channels[name]
            if arr.shape != (sc.nz, sc.ny, sc.nx):
                raise ValueError(f"{name}: shape {arr.shape} != export grid")
            nb = name.encode("ascii")
            f.write(struct.pack("<I", len(nb)))
            f.write(nb)
            f.write(struct.pack("<f", contract.THRESHOLDS[name]))
            f.write(arr.tobytes())
