# Phase 1 — SVT frame budget (pipeline anchor)

**Status:** decided (2026-07-14); **AMENDED against real CM1 data (2026-07-15, task 5 —
[`phase1-task5-pipeline.md`](phase1-task5-pipeline.md)).** This is the first Phase 1 number
computed, because it constrains everything upstream: export resolution, decimation, channel
packing, and the scenario-package format contract.

> ## Amendments from real data (2026-07-15)
>
> This doc was authored before any real CM1 frames existed; it sized the crop and sparsity
> from reasoning plus a synthetic fixture. Task 5 measured the real single-cell run and three
> numbers below are **superseded**. The *conclusion* — per-frame size is not the limiter —
> survived and in fact got stronger. What changed:
>
> | Was | Now (measured over all 301 frames) | Why |
> |---|---|---|
> | crop **40 × 40 × 16 km** | **52 × 52 × 18 km** (208×208×72 @ 250 m) | The real cold-pool outflow reaches **23.25 km** from centre (and 24.25 km at a 100× lower threshold) — the 20 km half-width **clipped the storm**. Anvil top hit 15.75 km vs a 16 km cap. |
> | `ice` channel = **qi** | `ice` = **qi + qs** | NSSL ptype=27 emits snow separately. Measured **qs/qi ≈ 0.29–0.53** by mass, with snow filling **as many voxels as ice** — omitting it visibly thins the anvil. Merged rather than added as a 6th channel: this keeps the 5-grid / RGBA16F+R16F layout task 3 already proved, so **no SVT import re-test was needed**. Follows the existing qg+qhl precedent; the split stays recoverable in the 3 spare channels. |
> | sparse fill **35 %** (assumed) | **≤ 12.2 %** within the crop (peak grid, peak frame) | The 35 % figure was a conservative guess. Real peak per-frame VDB is **3.36 MB**, not the ~5.7 MB estimated — an order of magnitude under the streaming ceiling. |
>
> The crop miss is the single most valuable thing the spike caught: it is exactly the
> real-vs-synthetic gap `sim/single_cell/README.md` predicted, and it would have silently
> truncated every frame of the sequence.

## Why this comes first

Phase 1 is a risk-first de-risking spike. The tightest hard constraint in the whole chain
is UE Sparse Volume Texture streaming, so we size the pipeline to it *before* building the
pipeline — not after (see the risk-first sequencing in the Phase 1 task list). Getting this
wrong is expensive: it's baked into how CM1 output is decimated and how the VDB channels are
laid out.

## The constraints (source: docs/advisor-review-2026-07-09.md; CLAUDE.md)

UE Sparse Volume Textures are **Experimental**, with hard limits:

- **≤ 2 attribute textures, ≤ 8 channels total** per SVT.
- All grids **share one transform**.
- The bounding-box **center must be static across the sequence** — pad a fixed box.
- **Streaming degrades above ~30–50 MB/frame.** That number *is* the decimation budget.

## Channel → texture mapping (fits in 2 textures / 8 channels, 5 used)

The single-cell spike ships 5 fields. NSSL `ptype=27` has a true hail category distinct from
graupel; for rendering we combine graupel+hail into one "dense frozen precip" channel and keep
the split available in a spare channel for later phases.

| Texture   | Format     | R          | G          | B          | A                     |
|-----------|------------|------------|------------|------------|-----------------------|
| **A**     | RGBA16F    | qc (cloud water) | **qi+qs (cloud ice + snow)** | qr (rain) | qg+qhl (graupel+hail) |
| **B**     | R16F       | dBZ (radar diag) | —      | —          | —                     |

> **Amended 2026-07-15:** the `ice` channel carries **qi + qs**, not qi alone (see the
> amendment table at the top), and CM1's hail variable is `qhl` (not `qh`). The grid
> **names** shipped in the VDB — `cloud`, `ice`, `rain`, `graupelhail`, `dbz` — are
> unchanged and frozen: task 3 proved UE 5.8's default grid→SVT assignment reproduces this
> exact map, so renaming would force an import re-test.

- 5 channels used of 8 → headroom for a 6th–8th field later (split hail from graupel, add
  temperature for cloud tint, or w for updraft viz) **without** re-authoring the SVT contract.
- **fp16 (2 bytes/channel)** chosen over int16-scale/offset: mixing ratios span ~3 orders of
  magnitude and fp16's ~3-decimal-digit mantissa with a wide exponent covers that natively;
  no per-field scale/offset bookkeeping in the format. int16 log-packing stays a documented
  fallback if a field ever needs it. 8-bit unorm is rejected (loses dynamic range on qc/qi).
- **Bytes per active voxel = 8 (Tex A) + 2 (Tex B) = 10 B.** (If Tex B is later promoted to
  RGBA16F to use its spare channels, that rises to 16 B/voxel — table below notes the effect.)
- This channel map is part of the **scenario-package format contract** (manifest records it;
  see `scenarios/`). UE reads the mapping from the manifest, never hardcodes it.

## Export domain (single cell, stationary, flat)

> **SUPERSEDED by measurement (2026-07-15).** The real crop is **52 × 52 × 18 km**
> (208×208×72 @ 250 m); the 40 × 40 × 16 km box below **clipped** both the outflow and the
> anvil top. The reasoning about *why* the box is fixed and centred still holds verbatim —
> only the numbers moved. Authoritative box: `pipeline/cm1post/config.py`.

A single airmass cell's meaningful cloud+precip is ~15–25 km wide and reaches the overshooting
top near 16 km. We crop the CM1 domain to a **fixed, padded 40 × 40 × 16 km box** covering the
cell's full life cycle. Because the spike cell is **stationary** (`imove=0`), its bbox center
never moves — the static-center constraint is satisfied for free (this is *why* stationary was
chosen for the spike). The pad covers max anvil spread so the box size is constant across all
frames.

## Per-frame size vs. export resolution

Dense = every voxel in the crop. Sparse = 35% active (conservative; SVT is tile-granular, so
effective fill exceeds pointwise condensate fraction). Budget ceiling: **30–50 MB/frame.**

| Export res | Grid (40×40×16 km)   | Voxels     | Dense @10 B | Sparse @35% | vs. budget        |
|------------|----------------------|------------|-------------|-------------|-------------------|
| 500 m      | 80×80×32             | 0.20 M     | 2.0 MB      | 0.7 MB      | ✓ huge headroom   |
| 333 m      | 120×120×48           | 0.69 M     | 6.9 MB      | 2.4 MB      | ✓ comfortable     |
| **250 m**  | **160×160×64**       | **1.64 M** | **16.4 MB** | **5.7 MB**  | **✓ recommended** |
| 200 m      | 200×200×80           | 3.20 M     | 32.0 MB     | 11.2 MB     | ✓ (dense at ceiling) |
| 150 m      | 267×267×107          | 7.63 M     | 76.3 MB     | 26.7 MB     | ⚠ sparse-only      |
| 125 m      | 320×320×128          | 13.1 M     | 131 MB      | 45.9 MB     | ✗ dense over; sparse at ceiling |

**Sequence total** at ~300 frames (sparse): 250 m ≈ 1.7 GB, 200 m ≈ 3.4 GB, 150 m ≈ 8 GB. This
is per-frame streaming budget, not the binding limit for the spike, but it sizes package storage.

## Decision for the spike

- **Export at 250 m isotropic** over the 40×40×16 km crop → **~5.7 MB/frame sparse (~16 MB dense
  worst case)**, ~300 frames ≈ **1.7 GB** sequence.
- Sits comfortably below the 30–50 MB/frame ceiling with room to push resolution if UE streams
  it happily — exactly what a de-risking spike wants: realistic multi-grid, few-hundred-frame
  load with margin, not a fragile at-the-limit test.

**Honest caveat (plumbing vs. physics):** the spike's CM1 run is deliberately coarse (500 m /
1 km — it's a plumbing test, not a hero run). Exporting at 250 m therefore **interpolates** the
coarse sim; it adds no physical detail. That is fine and intended here — the goal is to exercise
the VDB-writer → SVT streaming path at a realistic *data volume and frame count*, not to produce
science-grade fine structure. **Production per-frame size gets re-benchmarked** in later phases
when the sim runs at 250–333 m native and the crop may enlarge for supercells.

## What actually binds the spike

Not per-frame bytes — we have headroom. The real tests the spike must pass are:

1. **Frame count** — streaming a *few-hundred-frame* sequence without hitches (explicitly NOT a
   one-frame demo).
2. **Multi-grid mechanics** — two attribute textures sharing one transform.
3. **Static padded bbox** — center fixed across all frames.

The budget's job was to prove per-frame size is *not* the limiter at the chosen export res, and
to fix the channel layout and packing the pipeline decimation is built against. Done.
