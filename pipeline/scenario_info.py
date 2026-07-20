#!/usr/bin/env python3
"""Expose scenario config fields to shell scripts, via the real loader.

sim/run_scenario.sh needs the run dir, the grid line and the provenance block. It
could grep the JSON -- and then the config would have two readers that can disagree
(a `_note` string containing `"run_dir"` is all it would take). This routes the shell
through `cm1post.scenario.load`, so run_meta.txt is generated from exactly the object
the pipeline exports from.

    python3 pipeline/scenario_info.py --scenario <name> --run-dir
    python3 pipeline/scenario_info.py --scenario <name> --grid-line
    python3 pipeline/scenario_info.py --scenario <name> --provenance
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cm1post import scenario  # noqa: E402


def grid_line(sc):
    """The sim grid, in the shape the Phase 1 run_meta.txt wrote it by hand."""
    n = sc.namelist
    return (f"nx={n['nx']} ny={n['ny']} nz={n['nz']}  "
            f"dx=dy={n['dx']:.0f} m  domain={n['nx'] * n['dx'] / 1000:.2f} km")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", required=True)
    p.add_argument("--run-dir", action="store_true")
    p.add_argument("--grid-line", action="store_true")
    p.add_argument("--provenance", action="store_true",
                   help="the sim.provenance block as aligned 'key : value' lines")
    args = p.parse_args()

    try:
        sc = scenario.load(args.scenario)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.run_dir:
        print(sc.run_dir)
    if args.grid_line:
        print(grid_line(sc))
    if args.provenance:
        for k, v in sc.provenance.items():
            print(f"{k:<17}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
