#!/usr/bin/env python3
"""Drive the CM1 -> VDB scenario export.

    python3 export_scenario.py bbox   --run <dir>            # verify the padded box
    python3 export_scenario.py export --run <dir> --out <dir> [--frames a:b]

`bbox` re-measures the union active region over every frame and checks it against
the box locked in cm1post/config.py. Run it whenever a threshold, a source field, or
the CM1 deck changes -- it is the guard against silently clipping the storm.

`export` writes frame_NNNNN.vdb + manifest.json. Each frame goes
netCDF -> channels -> resample -> .densevol -> dense2vdb -> .vdb, and the
intermediate .densevol is deleted unless --keep-densevol.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm1post import config, densevol, fields, manifest, regrid

DEFAULT_RUN = "/home/boiko/thunderstorm/runs/singlecell"
DEFAULT_DENSE2VDB = "/home/boiko/thunderstorm/vdbwriter_build/dense2vdb"


def parse_range(spec, n):
    if not spec:
        return list(range(n))
    a, _, b = spec.partition(":")
    return list(range(int(a or 0), int(b or n)))


def cmd_bbox(args):
    files = fields.frame_files(args.run)
    print(f"sweeping {len(files)} frames at the LOCKED export thresholds")
    print(f"  thresholds: {config.THRESHOLDS}")
    cm1_x, cm1_y, cm1_z = fields.read_grid(files[0])

    half = 0.0
    ztop = 0.0
    peak_active, peak_i = 0, -1
    for i, path in enumerate(files):
        ch, t = fields.build_channels(path)
        m = fields.active_mask(ch)
        n = int(m.sum())
        if n > peak_active:
            peak_active, peak_i = n, i
        if n:
            zi, yi, xi = np.where(m)
            half = max(half, abs(cm1_x[xi.min()]), abs(cm1_x[xi.max()]),
                       abs(cm1_y[yi.min()]), abs(cm1_y[yi.max()]))
            ztop = max(ztop, cm1_z[zi.max()])
        if i % 60 == 0:
            print(f"  frame {i:3d} t={t/60:5.1f}min active={n/m.size*100:6.3f}%")

    print("\n=== union active region at export thresholds ===")
    print(f"  horizontal half-width : {half/1000:7.3f} km   box: {config.CROP_HALF_WIDTH_M/1000:.3f} km"
          f"   margin {(config.CROP_HALF_WIDTH_M-half)/1000:+.3f} km")
    print(f"  top                   : {ztop/1000:7.3f} km   box: {config.CROP_Z_TOP_M/1000:.3f} km"
          f"   margin {(config.CROP_Z_TOP_M-ztop)/1000:+.3f} km")
    print(f"  peak active frame     : {peak_i} ({peak_active} CM1 voxels)")

    ok = half <= config.CROP_HALF_WIDTH_M and ztop <= config.CROP_Z_TOP_M
    print(f"\n{'PASS -- box contains every frame' if ok else 'FAIL -- box CLIPS the storm'}")
    return 0 if ok else 1


def cmd_export(args):
    files = fields.frame_files(args.run)
    idx = parse_range(args.frames, len(files))
    os.makedirs(args.out, exist_ok=True)
    vdb_dir = os.path.join(args.out, "vdb")
    os.makedirs(vdb_dir, exist_ok=True)

    cm1_x, cm1_y, cm1_z = fields.read_grid(files[0])
    query = regrid.build_query(cm1_x, cm1_y, cm1_z)  # identical every frame
    print(f"export grid {config.NX}x{config.NY}x{config.NZ} @ {config.EXPORT_VOXEL_M:.0f} m"
          f"  origin {config.ORIGIN_M}")
    print(f"exporting {len(idx)} frames -> {vdb_dir}")

    records = []
    t0 = time.time()
    for n, i in enumerate(idx):
        path = files[i]
        ch, storm_t = fields.build_channels(path)
        res = {name: regrid.resample(arr, cm1_x, cm1_y, cm1_z, query)
               for name, arr in ch.items()}

        stem = f"frame_{i:05d}"
        dv = os.path.join(vdb_dir, stem + ".densevol")
        vdb = os.path.join(vdb_dir, stem + ".vdb")
        densevol.write(dv, res)
        r = subprocess.run([args.dense2vdb, dv, vdb], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAIL frame {i}: {r.stderr.strip()}", file=sys.stderr)
            return 1
        if not args.keep_densevol:
            os.remove(dv)

        nbytes = os.path.getsize(vdb)
        records.append({"index": i, "time_s": storm_t,
                        "file": f"vdb/{stem}.vdb", "bytes": nbytes})
        if n % 20 == 0 or n == len(idx) - 1:
            el = time.time() - t0
            print(f"  [{n+1:3d}/{len(idx)}] {stem} t={storm_t/60:5.1f}min "
                  f"{nbytes/1e6:5.2f} MB  ({el/(n+1):.1f} s/frame)")

    prov = read_provenance(args.run)
    doc = manifest.build(scenario=args.scenario, source_run=args.run,
                         frames=records, provenance=prov)
    manifest.write(os.path.join(args.out, "manifest.json"), doc)

    tot = sum(r["bytes"] for r in records)
    peak = max(records, key=lambda r: r["bytes"])
    print(f"\ndone in {time.time()-t0:.0f} s")
    print(f"  frames     : {len(records)}")
    print(f"  total      : {tot/1e9:.2f} GB")
    print(f"  mean/frame : {tot/len(records)/1e6:.2f} MB")
    print(f"  PEAK frame : {peak['index']} at {peak['bytes']/1e6:.2f} MB "
          f"(SVT streaming budget: 30-50 MB/frame)")
    return 0


def read_provenance(run_dir):
    """Record what produced the data (charter: seed, build, ranks, decomposition)."""
    prov = {"cm1_version": "cm1r21.1",
            "build_doc": "docs/phase0-cm1-build.md",
            "namelist": "sim/single_cell/namelist.input",
            "microphysics": "NSSL 2-moment, ptype=27 (true hail category)",
            "sounding": "Weisman-Klemp analytic (isnd=5)",
            "shear": "none (iwnd=0) -- the zero-shear pulse-cell baseline",
            "initiation": "warm bubble (iinit=1), no random perturbations (irandp=0)",
            "domain_motion": "stationary (imove=0)"}
    cfg = os.path.join(run_dir, "cm1_config.txt")
    if os.path.exists(cfg):
        prov["cm1_config"] = "cm1_config.txt present in source run"
    return prov


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bbox", help="verify the padded box against every frame")
    b.add_argument("--run", default=DEFAULT_RUN)
    b.set_defaults(func=cmd_bbox)

    e = sub.add_parser("export", help="write the VDB sequence + manifest")
    e.add_argument("--run", default=DEFAULT_RUN)
    e.add_argument("--out", required=True)
    e.add_argument("--frames", help="index range a:b (default all)")
    e.add_argument("--scenario", default="single_cell_500m")
    e.add_argument("--dense2vdb", default=DEFAULT_DENSE2VDB)
    e.add_argument("--keep-densevol", action="store_true")
    e.set_defaults(func=cmd_export)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
