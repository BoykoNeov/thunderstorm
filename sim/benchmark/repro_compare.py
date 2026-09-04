#!/usr/bin/env python3
"""Compare all data variables of two CM1 netCDF outputs for bitwise identity.

The comparison is on DECODED variable arrays, never on file bytes: netCDF-4
files can differ byte-wise for benign reasons (creation attributes, chunk
layout, deflate nondeterminism) while holding identical data.

Used by the Phase 0 reproducibility gate (sim/benchmark/repro.sh) and, from
2026-09-04, by sim/probes/compare_raced.py -- which imports compare_files()
rather than reimplementing it, so the two cannot drift apart.
"""
import sys

import netCDF4
import numpy as np


def compare_files(path_a, path_b, report=print):
    """Compare every shared data variable of two CM1 netCDF files.

    Returns (all_bitwise_identical, max_abs_diff, n_vars_compared).
    """
    a = netCDF4.Dataset(path_a)
    b = netCDF4.Dataset(path_b)
    try:
        allbit = True
        maxdiff = 0.0
        nvar = 0
        for v in a.variables:
            if v not in b.variables:
                continue
            da = a.variables[v][:]
            db = b.variables[v][:]
            nvar += 1
            if not np.array_equal(da, db):
                allbit = False
                d = float(np.nanmax(np.abs(np.asarray(da, 'f8') - np.asarray(db, 'f8'))))
                maxdiff = max(maxdiff, d)
                if report is not None:
                    report(f"  DIFF {v}: max|delta| = {d:g}")
        return allbit, maxdiff, nvar
    finally:
        a.close()
        b.close()


if __name__ == "__main__":
    allbit, maxdiff, nvar = compare_files(sys.argv[1], sys.argv[2])
    print(f"compared {nvar} vars; bitwise_identical = {allbit}; max_abs_diff = {maxdiff:g}")
