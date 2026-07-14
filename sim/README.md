# sim/

Scenario configs, CM1 namelists, and WSL run scripts.

CM1 raw output (netCDF) is written to **WSL ext4**, never through `/mnt/*`, and is
never committed (regenerable, disposable by design). Only finished scenario packages
are copied out to durable storage.

_Empty until Phase 0 (build CM1 in WSL; run the canonical Weisman–Klemp supercell).
Do not start a phase without explicit go from the owner._
