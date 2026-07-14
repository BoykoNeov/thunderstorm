# sim/single_cell/ — Phase 1 single-cell scenario

The CM1 deck that produces the **real** single-cell dataset for the Phase 1
pipeline de-risking spike (netCDF → pipeline → VDB sequence → UE SVT). This is
the physics counterpart to the synthetic fixture in
[`pipeline/vdbwriter/gen_synthetic.py`](../../pipeline/vdbwriter/gen_synthetic.py):
once the pipeline is proven on synthetic frames, it is re-run on **this** output.

**Coarse by design.** Per the charter, the Phase 1 spike is *plumbing, not
physics*: 500 m is adequate to resolve one pulse cell and cheap to regenerate.
Production resolution (333 m default) is a Phase 2/3 concern; nothing here is a
science claim.

## Storm design — how "single cell" emerges from the simulation

Physics through simulation (charter principle #1): the single-cell regime is
**not** scripted — it falls out of the environment.

| Lever | Value | Why |
|---|---|---|
| `isnd=5` | Weisman–Klemp analytic sounding | Same buoyant thermodynamics as the Phase 0 supercell. |
| `iwnd=0` | **zero winds (no shear)** | This is the whole story. Zero shear + moderate CAPE + a warm bubble = a classic short-lived **pulse / air-mass cell** (the WK zero-shear baseline). Shear is what would organize it into multicell/supercell. **Deliberately *zero*, not merely weak** (the pre-plan said "weak shear"): zero is the cleanest single-cell baseline *and* it guarantees the static SVT bounding-box center. A token weak-shear variant (`iwnd=1` RKW-type) is a trivial re-run if the owner wants slightly more realism. |
| `iinit=1` | warm bubble | One bubble = one cell. Geometry is hardcoded in `init3d.F` (h-radius 10 km, v-radius 1.4 km, +1.0 K, centered) — the same trigger the validated supercell used. |
| `imove=0` | stationary domain | No mean wind to advect the cell; it grows and decays in place. Makes the padded SVT bounding-box center **static by construction** (the UE SVT hard constraint). |
| `irandp=0` | no random perturbations | A clean single cell, deterministic. (Low-level noise would seed spurious secondary cells — that is a *multicell* design lever, Phase 3.) |
| `icor=0` | no Coriolis | Short-lived cell; rotation irrelevant. |

Expected life cycle over `timax=3600 s` (60 min): tower by ~10 min, first
precip ~15 min, **a clean pulse cell for ~25–30 min, then likely cold-pool /
gust-front secondary cells spreading radially** off the outflow. That secondary
development is expected physics (zero shear + a cold pool), not a bug — and it's
fine for a plumbing run, but it means (a) the "single cell" story is really the
first ~30 min, and (b) the real active-volume footprint may spread **wider** than
the synthetic fixture's centered ~35%, so the SVT per-frame budget
([`docs/phase1-svt-budget.md`](../../docs/phase1-svt-budget.md)) must be
**re-checked against these real frames** — surfacing exactly that real-vs-synthetic
gap is what the spike is for. The warm bubble sits at the domain center
(`iorigin=2` → `centerx=centery=0`), so the cell is centered in the 80 km box
with ~40 km to every boundary — the outflow stays interior for the full hour.

## Grid & output

- **Horizontal:** `nx=ny=160`, `dx=dy=500 m` → **80 × 80 km**, flat
  (`terrain_flag=.false.`, `itern=0`), open-radiative lateral BCs.
- **Vertical:** `nz=40`, `stretch_z=0` → **uniform dz = 500 m**, model top
  **20 km**. ✅ *Verified from the output* (`zh` scalar levels 0.25…19.75 km,
  `zf` 0…20 km, constant 0.5 km spacing). Note: with `stretch_z=0` CM1 uses the
  **`param1 dz=500`** value and `nz`, giving `40×500 = 20 km` — the
  **`param6 ztop=18000` is ignored** in this mode. (Earlier inference of
  "≈450 m = ztop/nz" was wrong; corrected against the actual grid, per the
  advisor's "verify, don't assert" flag.) The Rayleigh damping layer
  (`zd=15 km`) sits comfortably below the 20 km top. This matches the committed,
  validated Phase 0 decks (`sim/validation`, `sim/benchmark/decks` — all
  `stretch_z=0` uniform) and `docs/phase0-validation.md`, which already records
  "dz=500 m (uniform)". A **stretched** vertical grid (finer near-surface
  resolution — a charter wall-clock/fidelity lever) is a deliberate Phase 2/3
  upgrade, not something to introduce untested on the first plumbing run.
  - Minor: `phase0-validation.md` lists `ztop=18 km`; the *effective* top with
    `stretch_z=0` is `nz×dz = 20 km` (the `param6 ztop` is inert in this mode).
- **Microphysics:** NSSL 2-moment `ptype=27` (true hail category), `ihail=1`.
  Emits the individual species the pipeline maps to SVT channels. **NSSL output
  variable names** (confirmed from the frames): `qc` cloud water, `qi` cloud
  ice, `qs` snow, `qr` rain, `qg` graupel, **`qhl` hail** (note: `qhl`, *not*
  `qh` — with number/volume `chl`/`vhl`), plus diagnostic `dbz` (and `cref`
  composite reflectivity). ✅ Hail verified active: `qhl` reaches ~5 g/kg by
  t≈50 min.
- **Time stepping:** `adapt_dt=1` (charter default; CFL-adaptive, still
  deterministic), `dtl=3.0 s` initial.
- **Output:** `output_format=2` (netCDF), `output_filetype=2` (**one file per
  output time** — the natural unit for a per-frame VDB pipeline, and it avoids
  the single-file size limit), `tapfrq=12 s` → **~301 frames** over 60 min.
  This is the "few-hundred-frame" sequence the Phase 1 SVT spike requires.

## Run

```bash
# from Windows:
wsl -d Ubuntu -- bash /mnt/m/claud_projects/thunderstorm/sim/single_cell/run.sh
```

`run.sh` copies the validated `cm1r21.1` binary and this namelist into
`/home/boiko/thunderstorm/runs/singlecell/` (WSL **ext4** — raw output never
goes through `/mnt/*`), writes `run_meta.txt` (binary sha256, rank count,
decomposition — charter reproducibility contract), and runs `mpirun -np 8`
(locked by the Phase 0 benchmark gate). Estimated compute: well under an hour
(500 m / 80 km / NSSL is far cheaper than the 120 km production benchmark).

Raw `cm1out_*.nc` is **disposable** and never committed (charter data policy);
only the finished scenario package (Phase 1 task 5) is durable.

## Run outcome (verified 2026-07-14)

301 frames + `cm1out_stats.nc`, ~6.1 GB raw in WSL ext4, **18 min** wall at
`np=8` (~2.3 core-hours), all ranks terminated normally (the
`IEEE_UNDERFLOW/DENORMAL` notes are CM1's standard benign FP flags). A clean,
vigorous pulse cell with the expected life cycle:

| t (min) | peak w (m/s) | max dBZ | hail `qhl` | phase |
|---|---|---|---|---|
| 0–15 | 0.8 → 5.9 | 0 | 0 | warm-bubble rise |
| 20 | 25 | 16 | 0 | first precip; graupel begins |
| 25–30 | 46 → **53** | 44 → 51 | onset | **mature updraft peak** |
| 35–50 | 33 → 44 | 59 → **71** | 0.6 → 4.7 g/kg | hail core falls; **secondary gust-front cells** |
| 60 | 22 | 63 | decaying | decay |

The updraft re-invigoration after ~30 min and the widening high-dBZ area are the
cold-pool secondary cells the advisor flagged — expected physics, and exactly
the real-vs-synthetic footprint spread to re-check against the SVT budget.

## What this feeds

`cm1out_*.nc` → pipeline (Phase 1 task 5): derived fields, regrid to Cartesian,
decimation, `.densevol` per frame → `dense2vdb` → VDB sequence + surface
textures + MetPy plots + manifest → scenario package → UE SVT playback.

**SVT channel mapping for the pipeline** (5 channels, per
[`docs/phase1-svt-budget.md`](../../docs/phase1-svt-budget.md)):
`cloud=qc`, `ice=qi+qs` (cloud ice + snow), `rain=qr`,
`graupelhail=qg+qhl` (graupel + hail), `dbz=dbz`.
