#!/usr/bin/env python3
"""Compare all data variables of two CM1 netCDF outputs for bitwise identity."""
import sys, netCDF4, numpy as np
a = netCDF4.Dataset(sys.argv[1]); b = netCDF4.Dataset(sys.argv[2])
allbit = True; maxdiff = 0.0; nvar = 0
for v in a.variables:
    if v not in b.variables:
        continue
    da = a.variables[v][:]; db = b.variables[v][:]
    nvar += 1
    if not np.array_equal(da, db):
        allbit = False
        d = float(np.nanmax(np.abs(np.asarray(da, 'f8') - np.asarray(db, 'f8'))))
        maxdiff = max(maxdiff, d)
        print(f"  DIFF {v}: max|delta| = {d:g}")
print(f"compared {nvar} vars; bitwise_identical = {allbit}; max_abs_diff = {maxdiff:g}")
