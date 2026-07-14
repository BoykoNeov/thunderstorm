#!/usr/bin/env python3
"""Generate a synthetic single-cell storm as a .densevol sequence.

This is a PLUMBING fixture, not physics. Its only job is to exercise the
VDB-writer -> UE SVT path at a realistic data volume, channel count, frame
count, and sparsity BEFORE the real CM1->pipeline chain exists (risk-first
Phase 1 sequencing). The fields are hand-shaped envelopes, clearly fake.

Grid + channels match docs/phase1-svt-budget.md exactly:
  250 m isotropic over a fixed, padded 40 x 40 x 16 km box -> 160 x 160 x 64,
  channels: cloud, ice, rain, graupelhail, dbz.
The cell is stationary and centered, so the padded bbox center is static across
all frames (the SVT static-center constraint is satisfied by construction).

Writes frame_00000.densevol ... in the output dir. See dense2vdb.cpp for the
binary format.
"""
import argparse
import os
import struct
import numpy as np

CHANNELS = ["cloud", "ice", "rain", "graupelhail", "dbz"]
# Per-channel activity thresholds (below -> inactive background in the VDB).
THRESHOLDS = {
    "cloud": 1.0e-4,       # kg/kg
    "ice": 1.0e-4,
    "rain": 1.0e-4,
    "graupelhail": 1.0e-4,
    "dbz": 5.0,            # dBZ
}


def life_cycle(frac):
    """Amplitude envelope over the run: grow, mature, decay. frac in [0,1]."""
    # Smooth asymmetric bell: quick tower growth, longer decay.
    grow = np.clip(frac / 0.30, 0.0, 1.0)
    decay = np.clip((1.0 - frac) / 0.55, 0.0, 1.0)
    return float(min(grow, 1.0) * (0.15 + 0.85 * decay))


def build_frame(nx, ny, nz, voxel, frac):
    """Return dict channel->float32 array shape (nz, ny, nx)."""
    amp = life_cycle(frac)
    # World coords (meters) of voxel centers.
    xs = (np.arange(nx) + 0.5) * voxel
    ys = (np.arange(ny) + 0.5) * voxel
    zs = (np.arange(nz) + 0.5) * voxel
    cx, cy = xs[-1] * 0.5, ys[-1] * 0.5  # stationary cell at horizontal center
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")  # (nx,ny,nz)
    r2 = (X - cx) ** 2 + (Y - cy) ** 2

    # Cloud tower: base ~1 km, top rises with growth then holds.
    top = 3000.0 + 11000.0 * np.clip(frac / 0.35, 0.0, 1.0)  # m
    base = 1000.0
    core_r = 4000.0 + 2000.0 * amp  # horizontal core radius (m)
    tower = np.exp(-r2 / (2 * core_r ** 2))
    zprof = np.clip((Z - base) / 800.0, 0, 1) * np.clip((top - Z) / 1500.0, 0, 1)
    cloud = amp * 3.0e-3 * tower * zprof

    # Anvil ice near the top, spreads wide at maturity.
    anvil_r = 6000.0 + 9000.0 * amp
    anvil = np.exp(-r2 / (2 * anvil_r ** 2))
    zice = np.exp(-((Z - (top - 1500.0)) ** 2) / (2 * 1800.0 ** 2))
    ice = amp * 1.2e-3 * anvil * zice

    # Rain: below cloud base, onset after the tower forms.
    rain_amp = amp * np.clip((frac - 0.12) / 0.2, 0.0, 1.0)
    rcol = np.exp(-r2 / (2 * (core_r * 0.8) ** 2))
    zrain = np.clip((4000.0 - Z) / 3500.0, 0, 1)
    rain = rain_amp * 4.0e-3 * rcol * zrain

    # Graupel/hail: mid-level core during the mature phase.
    gh_amp = amp * np.exp(-((frac - 0.45) ** 2) / (2 * 0.15 ** 2))
    gcol = np.exp(-r2 / (2 * (core_r * 0.6) ** 2))
    zgh = np.exp(-((Z - 6000.0) ** 2) / (2 * 2500.0 ** 2))
    graupelhail = gh_amp * 3.0e-3 * gcol * zgh

    # dBZ diagnostic proxy from rain + graupel/hail (fake but monotone).
    z_lin = 1.0e5 * rain + 3.0e5 * graupelhail  # arbitrary reflectivity units
    with np.errstate(divide="ignore"):
        dbz = 10.0 * np.log10(np.maximum(z_lin, 1e-3))
    dbz = np.clip(dbz, 0.0, 70.0)

    out = {"cloud": cloud, "ice": ice, "rain": rain,
           "graupelhail": graupelhail, "dbz": dbz}
    # Transpose (nx,ny,nz) -> (nz,ny,nx) so C-order flatten is x-fastest.
    return {k: np.ascontiguousarray(v.transpose(2, 1, 0), dtype="<f4") for k, v in out.items()}


def write_densevol(path, frame, nx, ny, nz, voxel, origin):
    with open(path, "wb") as f:
        f.write(b"DVOL")
        f.write(struct.pack("<I", 1))
        f.write(struct.pack("<III", nx, ny, nz))
        f.write(struct.pack("<I", len(CHANNELS)))
        f.write(struct.pack("<f", voxel))
        f.write(struct.pack("<fff", *origin))
        for name in CHANNELS:
            nb = name.encode("ascii")
            f.write(struct.pack("<I", len(nb)))
            f.write(nb)
            f.write(struct.pack("<f", THRESHOLDS[name]))
            f.write(frame[name].tobytes())  # (nz,ny,nx) C-order == x-fastest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="synthetic_seq", help="output directory")
    ap.add_argument("--nx", type=int, default=160)
    ap.add_argument("--ny", type=int, default=160)
    ap.add_argument("--nz", type=int, default=64)
    ap.add_argument("--voxel", type=float, default=250.0, help="voxel size (m)")
    ap.add_argument("--frames", type=int, default=300)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    origin = (0.0, 0.0, 0.0)  # fixed padded box; same for every frame
    for i in range(args.frames):
        frac = i / max(args.frames - 1, 1)
        frame = build_frame(args.nx, args.ny, args.nz, args.voxel, frac)
        p = os.path.join(args.out, f"frame_{i:05d}.densevol")
        write_densevol(p, frame, args.nx, args.ny, args.nz, args.voxel, origin)
        if i % 25 == 0 or i == args.frames - 1:
            print(f"  wrote {p} (life={life_cycle(frac):.2f})")
    print(f"done: {args.frames} frames in {args.out}/")


if __name__ == "__main__":
    main()
