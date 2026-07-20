#!/usr/bin/env python3
"""Drive the CM1 -> VDB scenario export.

    python3 export_scenario.py bbox       --scenario <name>              # verify the box
    python3 export_scenario.py export     --scenario <name> --out <dir> [--frames a:b]
    python3 export_scenario.py export-web --scenario <name> --out <dir> [--frames a:b]

`--scenario` names a config in sim/scenarios/ (or is a path to one). That JSON is the
single source of truth for the export geometry and the source run; `--run` overrides
only the run directory, for exporting a re-run of the same scenario from elsewhere.

`bbox` re-measures the union active region over every frame and checks it against
the box declared in the scenario config. Run it whenever a threshold, a source field,
or the CM1 deck changes -- it is the guard against silently clipping the storm.

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

from cm1post import contract, densevol, fields, manifest, regrid, scenario, webvol

DEFAULT_SCENARIO = "single_cell_500m"
DEFAULT_DENSE2VDB = "/home/boiko/thunderstorm/vdbwriter_build/dense2vdb"


def parse_range(spec, n):
    if not spec:
        return list(range(n))
    a, _, b = spec.partition(":")
    return list(range(int(a or 0), int(b or n)))


def cmd_bbox(args):
    sc = load_scenario(args)
    files = fields.frame_files(sc.run_dir)
    print(f"scenario {sc.name} ({sc.kind})  run {sc.run_dir}")
    print(f"sweeping {len(files)} frames at the LOCKED export thresholds")
    print(f"  thresholds: {contract.THRESHOLDS}")
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
    print(f"  horizontal half-width : {half/1000:7.3f} km   box: {sc.crop_half_width_m/1000:.3f} km"
          f"   margin {(sc.crop_half_width_m-half)/1000:+.3f} km")
    print(f"  top                   : {ztop/1000:7.3f} km   box: {sc.crop_z_top_m/1000:.3f} km"
          f"   margin {(sc.crop_z_top_m-ztop)/1000:+.3f} km")
    print(f"  peak active frame     : {peak_i} ({peak_active} CM1 voxels)")

    ok = half <= sc.crop_half_width_m and ztop <= sc.crop_z_top_m
    print(f"\n{'PASS -- box contains every frame' if ok else 'FAIL -- box CLIPS the storm'}")
    return 0 if ok else 1


def cmd_export(args):
    sc = load_scenario(args)
    files = fields.frame_files(sc.run_dir)
    idx = parse_range(args.frames, len(files))
    os.makedirs(args.out, exist_ok=True)
    vdb_dir = os.path.join(args.out, "vdb")
    os.makedirs(vdb_dir, exist_ok=True)

    cm1_x, cm1_y, cm1_z = fields.read_grid(files[0])
    query = regrid.build_query(sc, cm1_x, cm1_y, cm1_z)  # identical every frame
    print(f"scenario {sc.name} ({sc.kind})  run {sc.run_dir}")
    print(f"export grid {sc.describe_grid()}")
    print(f"exporting {len(idx)} frames -> {vdb_dir}")

    records = []
    t0 = time.time()
    for n, i in enumerate(idx):
        path = files[i]
        ch, storm_t = fields.build_channels(path)
        # dbz is logarithmic -- it resamples in linear Z (see regrid.resample_dbz).
        res = {name: (regrid.resample_dbz if name in contract.DIAGNOSTIC_CHANNELS
                      else regrid.resample)(sc, arr, cm1_x, cm1_y, cm1_z, query)
               for name, arr in ch.items()}

        stem = f"frame_{i:05d}"
        dv = os.path.join(vdb_dir, stem + ".densevol")
        vdb = os.path.join(vdb_dir, stem + ".vdb")
        densevol.write(dv, sc, res)
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

    doc = manifest.build(sc, frames=records, provenance=read_provenance(sc))
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


def cmd_export_web(args):
    """netCDF -> uint8 log-quantized gzipped bricks for the diorama web viewer.

    Same fields/regrid path as the VDB export (one threshold, shared code -- the
    bbox invariant holds by construction). See cm1post/webvol.py for the format.
    """
    sc = load_scenario(args)
    files = fields.frame_files(sc.run_dir)
    idx = parse_range(args.frames, len(files))
    os.makedirs(args.out, exist_ok=True)

    cm1_x, cm1_y, cm1_z = fields.read_grid(files[0])

    # Pass 1: per-channel maxima over the whole sequence, on the CM1 source grid
    # (a safe >= bound for every linearly-resampled frame -- see webvol.py).
    # Still a bound for dbz under the linear-Z resample: an interpolated Z never
    # exceeds the largest contributing Z, so the resampled dBZ never exceeds the
    # source frame's max dBZ.
    print(f"scenario {sc.name} ({sc.kind})  run {sc.run_dir}")
    print(f"scanning {len(files)} frames for per-channel maxima")
    qmax = {c: 0.0 for c in contract.CHANNELS}
    # Extra fields (T4) are SIGNED, so a max alone is not a range -- track both ends.
    observed = {n: {"min": float("inf"), "max": float("-inf")}
                for n in contract.WEB_EXTRA_FIELDS}
    t0 = time.time()
    for i, path in enumerate(files):
        ch, _ = fields.build_channels(path)
        for c, arr in ch.items():
            qmax[c] = max(qmax[c], float(arr.max()))
        for n in contract.WEB_EXTRA_FIELDS:
            a = fields.read_extra(path, n)
            observed[n]["min"] = min(observed[n]["min"], float(a.min()))
            observed[n]["max"] = max(observed[n]["max"], float(a.max()))
        if i % 60 == 0:
            print(f"  frame {i:3d}  ({(time.time()-t0)/(i+1):.2f} s/frame)")
    print("  qmax: " + "  ".join(f"{c}={qmax[c]:.4g}" for c in contract.CHANNELS))
    for n, o in observed.items():
        print(f"  {n}: observed {o['min']:+.2f} .. {o['max']:+.2f} "
              f"{contract.WEB_EXTRA_FIELDS[n]['units']}")

    # The fixed encode scale is only honest if the data actually fits inside it.
    # Clipping here would be silent and irreversible, so it is an ERROR, not a
    # warning -- the correct response is a deliberate contract change (which also
    # re-scales every existing package's colours), never a quietly truncated export.
    for n, o in observed.items():
        scale = contract.WEB_EXTRA_FIELDS[n]["scale_m_s"]
        if max(abs(o["min"]), abs(o["max"])) > scale:
            print(f"\nFAIL: {n} range {o['min']:+.2f}..{o['max']:+.2f} exceeds the "
                  f"fixed encode scale +/-{scale} (contract.W_ENCODE_SCALE_M_S).\n"
                  "      Encoding would CLIP the peak of the field. Raise the scale "
                  "in contract.py deliberately -- it is cross-scenario, so this "
                  "re-scales every package's colours and every legend.",
                  file=sys.stderr)
            return 1

    query = regrid.build_query(sc, cm1_x, cm1_y, cm1_z)
    print(f"export grid {sc.describe_grid()}")
    print(f"exporting {len(idx)} frames -> {args.out}")

    records = []
    t0 = time.time()
    for n, i in enumerate(idx):
        ch, storm_t = fields.build_channels(files[i])
        enc = {}
        for c in webvol.RGBA_CHANNELS:
            res = regrid.resample(sc, ch[c], cm1_x, cm1_y, cm1_z, query)
            enc[c] = webvol.encode_log_u8(res, contract.THRESHOLDS[c], qmax[c])
        res = regrid.resample_dbz(sc, ch["dbz"], cm1_x, cm1_y, cm1_z, query)
        enc["dbz"] = webvol.encode_linear_u8(res, contract.THRESHOLDS["dbz"], qmax["dbz"])
        # Extra fields (T4). `w` is SIGNED: resample_signed, never resample -- the
        # latter's clip at 0 would erase every downdraft (see regrid.resample_signed).
        for name, spec in contract.WEB_EXTRA_FIELDS.items():
            res = regrid.resample_signed(sc, fields.read_extra(files[i], name),
                                         cm1_x, cm1_y, cm1_z, query)
            enc[name] = webvol.encode_signed_u8(res, spec["scale_m_s"])

        rec = webvol.write_frame(args.out, i, enc)
        rec.update({"index": i, "time_s": storm_t})
        records.append(rec)
        if n % 20 == 0 or n == len(idx) - 1:
            el = time.time() - t0
            print(f"  [{n+1:3d}/{len(idx)}] f{i:04d} t={storm_t/60:5.1f}min "
                  f"{rec['rgba_bytes']/1e6:5.2f} MB  ({el/(n+1):.1f} s/frame)")

    doc = webvol.build_manifest(sc, records, qmax, observed=observed)
    webvol.write_manifest(os.path.join(args.out, "web_manifest.json"), doc)

    # Sum every *_bytes key, so an added extra field cannot silently fall out of
    # the reported total (the payload budget must count what actually ships).
    tot = sum(v for r in records for k, v in r.items() if k.endswith("_bytes"))
    peak = max(records, key=lambda r: r["rgba_bytes"])
    print(f"\ndone in {time.time()-t0:.0f} s")
    print(f"  frames     : {len(records)}")
    print(f"  total      : {tot/1e9:.3f} GB")
    print(f"  mean/frame : {tot/len(records)/1e6:.2f} MB")
    print(f"  PEAK rgba  : frame {peak['index']} at {peak['rgba_bytes']/1e6:.2f} MB")
    return 0


def load_scenario(args):
    """Resolve the Scenario for this invocation (--run overrides only the run dir)."""
    return scenario.load(args.scenario, run_dir_override=getattr(args, "run", None))


def read_provenance(sc):
    """Record what produced the data (charter: seed, build, ranks, decomposition).

    The science description is declared in the scenario config; only facts that can
    be observed in the run directory are added here.
    """
    prov = dict(sc.provenance)
    cfg = os.path.join(sc.run_dir, "cm1_config.txt")
    if os.path.exists(cfg):
        prov["cm1_config"] = "cm1_config.txt present in source run"
    return prov


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("--scenario", default=DEFAULT_SCENARIO,
                       help="scenario name in sim/scenarios/, or a path to its JSON")
        p.add_argument("--run", default=None,
                       help="override the scenario's run_dir (same scenario, other run)")

    b = sub.add_parser("bbox", help="verify the padded box against every frame")
    add_common(b)
    b.set_defaults(func=cmd_bbox)

    e = sub.add_parser("export", help="write the VDB sequence + manifest")
    add_common(e)
    e.add_argument("--out", required=True)
    e.add_argument("--frames", help="index range a:b (default all)")
    e.add_argument("--dense2vdb", default=DEFAULT_DENSE2VDB)
    e.add_argument("--keep-densevol", action="store_true")
    e.set_defaults(func=cmd_export)

    w = sub.add_parser("export-web",
                       help="write the diorama web-viewer bricks + web_manifest")
    add_common(w)
    w.add_argument("--out", required=True)
    w.add_argument("--frames", help="index range a:b (default all)")
    w.set_defaults(func=cmd_export_web)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
