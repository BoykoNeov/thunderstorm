# Phase 1 task 5 — real CM1 → pipeline → VDB sequence

**Status:** **COMPLETE (2026-07-15).** Real 301-frame single-cell sequence exported from
CM1 and imported into UE 5.8 as a 301-frame `AnimatedSparseVolumeTexture`. Peak frame
**3.51 MB** against a 30–50 MB/frame budget. The spike caught **two silent contract
errors** the synthetic fixture could not (below) — which is the entire reason it existed.
The **in-editor visual streaming playback check remains owed by the owner** (unchanged
from task 3 — it is not observable headless).

The task the whole spike was built toward: point the proven VDB writer at **real CM1
output** instead of the synthetic fixture, and produce a scenario package. Task 3 proved
the writer→UE SVT link on hand-shaped fake fields; this closes the real-vs-synthetic gap
`sim/single_cell/README.md` and `pipeline/vdbwriter/README.md` both explicitly deferred
to here.

## What this task had to prove

1. Real CM1 netCDF → the 5-channel render stack, with derived quantities computed in the
   pipeline (charter: "UE is a dumb player").
2. The padded bbox **actually contains the real storm** for every frame, with a static
   centre.
3. Per-frame size on **real** frames sits under the SVT streaming budget — the number
   `pipeline/vdbwriter/README.md` called "the binding per-frame test".
4. The whole 301-frame sequence converts without failures, and ships with a manifest UE
   can read.

## The headline: the synthetic fixture was hiding two real errors

Both were caught by measuring the real data before exporting it, and both would have
silently corrupted the sequence.

### 1. The locked 40 × 40 km crop clipped the storm

`docs/phase1-svt-budget.md` sized the export box at 40 × 40 × 16 km from reasoning about
"a single airmass cell". The real zero-shear cell does what `sim/single_cell/README.md`
predicted: its cold pool spawns secondary cells that spread **radially** off the outflow.
Measured union active region over all 301 frames:

| | measured | old box | new box |
|---|---|---|---|
| horizontal half-width | **23.25 km** (24.25 km at a 100× lower threshold) | 20 km → **CLIPS by 3.25 km** | **26 km** (+2.75 km margin) |
| top | **15.75 km** | 16 km → 1 voxel of margin | **18 km** (+2.25 km margin) |

The failure mode is nasty precisely because it is *silent*: the export succeeds, every
frame validates, and the storm just has its outflow sliced off at a square boundary.

### 2. The `ice` channel was dropping snow

NSSL `ptype=27` emits `qs` (snow) as a category distinct from `qi` (cloud ice); the
locked channel map listed `ice = qi` alone. Measured on real frames:

| frame | t | `sum(qs)/sum(qi)` | qs active voxels | qi active voxels |
|---|---|---|---|---|
| 120 | 24 min | 0.53 | 3 088 | 2 828 |
| 180 | 36 min | 0.29 | 20 304 | 20 456 |
| 240 | 48 min | 0.45 | 34 408 | 34 080 |

Snow fills **as many voxels as ice**. A pulse cell's anvil is largely snow, so shipping
`ice = qi` would have rendered a visibly thin anvil — and it would have looked plausible
enough to not get questioned.

**Fix: `ice = qi + qs`**, merged rather than added as a 6th channel. The reasoning is
load-bearing, not stylistic:

- It keeps the **5-grid / RGBA16F + R16F layout task 3 already proved**, so the SVT
  import mapping needed **zero re-test**. A 6th channel would mean promoting Tex B to
  RG16F and re-running task 3's import validation — new risk for a distinction that reads
  as one glaciated "anvil" category in a volume render anyway.
- It follows the **existing precedent**: the map already merges `qg + qhl` into
  `graupelhail` for exactly this reason.
- Nothing is foreclosed — the ice/snow split stays recoverable in the **3 spare
  channels** if a later phase wants a precip-type teaching layer. Radar stays independent
  in `dbz`.

(Also corrected: CM1's hail variable is **`qhl`**, not `qh` as the budget doc had it.)

## Design decisions

### dBZ comes from CM1, not from a reimplementation

The deck runs `output_dbz = 1`, so **the NSSL scheme computes reflectivity from its own
hydrometeor distributions** and CM1 writes it. That is strictly better than a
post-hoc parameterization: it is consistent with the microphysics that actually ran,
rather than a second, disagreeing estimate of the same quantity.

Provenance (charter: every parameterization cites its paper) — Mansell, Ziegler & Bruning
(2010), *J. Atmos. Sci.* **67**, 276–299; Ziegler (1985), *J. Atmos. Sci.* **42**,
1487–1509. It is **diagnostic only** and never feeds back into the simulation; the
manifest labels it as such.

**Honest caveat:** dBZ is logarithmic, and the 500→250 m resample interpolates in dB
rather than converting to linear Z first. This slightly smooths gradients at echo edges.
Acceptable for a plumbing spike; revisit if dBZ is ever used quantitatively in the UI.
Recorded in the manifest, not just here.

### The VDB carries CM1-native SI metres

The shared transform's translation is the true CM1 world coordinate of voxel (0,0,0)'s
centre — `(-25875, -25875, 125)` m. The metres→centimetres and Y-flip conversion into UE
space happens at **actor placement**, the single conversion site
(`docs/phase1-task3-svt-import.md`). Nothing in the pipeline converts units.

The origin is **derived, not hand-set**: OpenVDB's linear transform maps index → world at
voxel *centres*, so making the centres symmetric about x=y=0 is what pins the bbox centre
to exactly (0,0). Combined with a stationary cell (`imove=0`), the SVT static-centre
constraint holds **by construction** rather than by luck.

### Linear interpolation, deliberately

`regrid.py` uses `RegularGridInterpolator` (linear). Cubic resampling — including
`scipy.ndimage.map_coordinates`' **default** `order=3` — overshoots at sharp echo edges
and manufactures **negative mixing ratios**: water no simulation produced, in a project
whose first principle is physics through simulation. Output is clamped at ≥0 as a second
guard. This run is flat with verified-uniform 500 m levels (`stretch_z=0`), so no
terrain-following interpolation is needed; `regrid.py` is where that lands in Phase 3.

### One threshold, enforced by shared code

The padded box is only valid at the thresholds it was measured with. If the exporter used
a lower (more inclusive) threshold than the bbox sweep, condensate would fall outside the
box and clip — reintroducing error #1 through the back door. The guard is structural: the
`bbox` and `export` commands both build channels through `fields.build_channels` and read
`config.THRESHOLDS`, so they **cannot** drift apart. The thresholds ship in the manifest.

### UE trims the padded box and re-bases the origin

The pipeline emits CM1-native world coordinates, so the shared transform carries a
**nonzero translation** — a path task 3 never tested (its synthetic frames sat at origin
(0,0,0)). It behaves, but not the way the box was authored:

| | authored VDB | as imported by UE 5.8 |
|---|---|---|
| resolution | 208 × 208 × 72 | **186 × 186 × 65** |
| translation | (−25875, −25875, 125) | **(−23125, −23125, 125)** |
| scale | 250 | 250.000 ✓ |
| bbox centre z | 9000 | **8125** |

UE's factory **unions the active voxels across the whole sequence**, tightens the volume
to that union, and re-bases the translation by exactly `trimmed_voxels × voxel_size` —
11 empty voxels per side in x/y (11 × 250 = 2750 m), 7 off the top, none off the bottom
(rain reaches the ground).

**This is correct, not lossy.** −23125 is the centre of voxel 11, whose outer face sits
at −23250 m — the *exact* union half-width the `bbox` sweep measured over all 301 frames.
The index→world mapping is preserved exactly: the active volume lands at identical CM1
world coordinates with or without the pad. Only empty pad was dropped.

Two consequences worth having written down:

- **The padding is for the exporter, not for UE.** It guarantees no frame is clipped and
  keeps the *authored* centre at (0,0); UE then derives its own box regardless. The SVT
  static-centre constraint holds structurally — one transform and one resolution for the
  whole sequence — which is stronger than what the padding bought.
- **Phase 3 caveat:** the imported box being centred at (0,0) here is a *consequence of
  this stationary cell's active region being symmetric* (11 trimmed each side), not
  something the pad forces. A moving or asymmetric storm will hand UE a box **not**
  centred on the origin, which complicates a Y-flip taken about the origin. Not a problem
  to fix now; a thing to know before terrain/supercell scenarios.

## Results

| | |
|---|---|
| Frames | **301** (0–3600 s storm time, 12 s interval) |
| Sequence total | **0.46 GB** |
| Mean / frame | **1.52 MB** |
| **Peak frame** | **3.51 MB** (frame 255, t = 51 min) — **~10× under** the 30–50 MB/frame streaming budget |
| Export wall time | 450 s (1.5 s/frame) |
| UE import | 11.6 s → 301-frame `AnimatedSparseVolumeTexture`, 173.5 MB uasset |
| Texture formats | Tex A `PF_FLOAT_RGBA`, Tex B `PF_R16F` — as contracted |

All four things the task had to prove hold: real netCDF → the 5-channel stack; the box
contains the storm in every frame with a static centre; real per-frame size is far under
budget; and 301/301 frames converted and imported with a manifest UE can read.

The peak-frame number retires the last open sizing question in
`docs/phase1-svt-budget.md`: at 3.51 MB, per-frame size is **not** the limiter, and there
is room to raise export resolution if playback wants it.

## What is still owed

1. **In-editor visual streaming playback (OWNER).** Unchanged from
   `docs/phase1-task3-svt-import.md` — every non-visual binding test passes headless, but
   whether 301 frames *stream smoothly and look right* is only observable with a GPU and
   a human. This is now testable on **real storm data** (`/Game/SVT_REAL` in the
   `svt_probe` project), which is a better test than task 3's synthetic fixture.
2. **The UE placement rule must survive into the Phase 2 app.** The manifest describes
   the VDB on disk; the imported asset holds tightened values. The app takes placement
   from the **asset's frame transform** and applies **only** the units conversion.
   Adding manifest `origin_m` on top double-applies it and lands the volume **2750 m off
   in X/Y**. Recorded as `volume.ue_placement_rule` in the manifest itself, where the
   code that could get it wrong will be looking.
3. **Where the package lives (OWNER).** The charter requires deciding LFS vs out-of-repo
   "before the first package ships". This one is 0.46 GB — comfortably over the 10 MB
   plain-git line. It currently lives in WSL at
   `/home/boiko/thunderstorm/scenario_out/single_cell_500m/` and is regenerable in 7.5
   minutes from the CM1 run, so nothing is at risk while the decision is open.
4. **Python env lockfile** (`CLAUDE.md` pinned-versions, "TBD Phase 1"). The pipeline
   currently runs on system `python3` + numpy/scipy/netCDF4, with OpenVDB reached only
   through `dense2vdb`. Worth pinning before Phase 2 builds on it.

## Reproduction

Pipeline code is committed (`pipeline/cm1post/`, `pipeline/export_scenario.py`; usage in
`pipeline/README.md`). Regenerate with `export_scenario.py bbox` (the gate) then
`export` — 7.5 min for 301 frames.

Not committed (regenerable, under `M:\claud_projects\temp\task5\`): `vdb/` staged frames,
`import_real.py` (the headless UE import + transform check, expectations annotated with
UE's trim behaviour), `regen_manifest.py`, and logs. UE-side output is
`/Game/SVT_REAL` in the throwaway `svt_probe` project; per convention it is not promoted
to `unreal/`.
