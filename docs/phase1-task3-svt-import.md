# Phase 1 task 3 — synthetic VDB sequence → UE 5.8 SVT (import + pin-blessing)

**Status:** autonomous half **COMPLETE / PASS (2026-07-14)**. Visual streaming
playback remains an **owner-gated** editor check (see "Handoff" below). This task
*blesses the OpenVDB pin* — it is the acceptance test the vdbwriter README's
"pending" note pointed at.

## What this task had to prove

From `docs/phase1-svt-budget.md` and `docs/advisor-review-2026-07-09.md`, the spike's
binding tests are **not** per-frame bytes (we have headroom) but:

1. **Format compat** — UE 5.8's bundled OpenVDB reads the `.vdb` files the pipeline
   writes (file-format **v225**).
2. **Multi-grid mechanics** — our 5 grids land in ≤ 2 attribute textures / ≤ 8 channels,
   all sharing one transform.
3. **Full-length sequence** — a *few-hundred-frame* animated SVT builds without the
   "long import time / editor instability on multi-hundred-frame multi-grid sequences"
   failure the advisor review flagged (explicitly **not** a one-frame demo).

## Result 1 — format v225 compat is dispositive at the header (no UE run needed)

UE 5.8 bundles **`openvdb-13.0.0`** at
`W:\UE_5.8\Engine\Source\ThirdParty\OpenVDB\Deploy\openvdb-13.0.0`. Its `version.h`
declares the **identical `OPENVDB_FILE_VERSION = 225`** that our conda-forge openvdb
13.0.0 writer emits. Same serializer version + same Blosc compression ⇒ UE's reader
decodes exactly what we write. There is no version skew. This alone answers the narrow
"does v225 read" question — but the project *defined* acceptance empirically, so we ran
the import too.

## Result 2 — headless import works; the import/build half is autonomous

UE 5.8's `USparseVolumeTextureFactory`
(`Engine/Source/Editor/SparseVolumeTexture`) is a `UFactory`, drivable from Python via
`unreal.AssetImportTask`. Under a commandlet / `-ExecutePythonScript`, the factory's
`bIsUnattended` path fires (`SparseVolumeTextureFactory.cpp:436`): **no Slate dialog**,
falls back to `DefaultImportOptions`. Two behaviors make a plain automated import
"just work" for our data:

- **Sequence auto-detection** (`FindOpenVDBSequenceFileNames`): a filename ending in a
  digit before `.vdb` is treated as a sequence; the base name (`frame_`) is matched
  against siblings and ordered by numeric suffix. Our `frame_00000.vdb …
  frame_00299.vdb` → detected as one 300-frame sequence → `bIsSequence = true` →
  **animated** SVT.
- **Default grid assignment** (`ComputeDefaultOpenVDBGridAssignment`): no grid is named
  `density`, so the fallback packs the 5 float grids sequentially into 2 attribute
  textures × 4 components at Float16 — **Attr A = cloud/ice/rain/graupelhail, Attr B =
  dbz**. This reproduces the `phase1-svt-budget.md` channel map with **zero custom
  options**.

## Result 3 — full 300-frame build, measured

Headless import of all 300 v225 frames (`import_full.py`), then clean read-back
(`verify_svt.py`):

| Metric | Value |
|---|---|
| Asset class | `AnimatedSparseVolumeTexture` |
| `get_num_frames()` | **300** |
| `volume_resolution` | **160 × 160 × 64** (our export grid) |
| `format_a` | **PF_FLOAT_RGBA** (RGBA16F) — cloud/ice/rain/graupelhail |
| `format_b` | **PF_R16F** — dbz |
| Import wall time | **21.1 s** (warm project) |
| Built `.uasset` on disk | **331 MB** (~1.10 MB/frame avg) |

The 21 s import time **refutes** the "long import / instability on multi-hundred-frame
multi-grid sequences" risk on this data. The RGBA16F + R16F formats are the exact
two-texture layout the budget doc specified.

> **Readback footnote:** the correct API is `get_num_frames()` (there is **no**
> `get_frame_count`). An early full-run log line showed `frame_count = None` purely
> because the probe script called the wrong method name; the asset always held 300
> frames (confirmed by `verify_svt.py` and the 331 MB size).

## What is still owner-gated (Handoff)

The **import/build** half is done and autonomous. The **visual streaming playback** half
needs the editor GUI and human eyes — it cannot be validated headless:

1. Open `SvtProbe` in the UE 5.8 editor.
2. Place a **Heterogeneous Volume** actor; assign a material with a **Sparse Volume
   Texture** sampler bound to `/Game/SVT/frame`; enable the material's **Animated SVT**
   / frame-driving input.
3. Scrub / play all 300 frames and watch for: streaming **hitches**, correct
   condensate/dBZ appearance, and static-bbox stability (center must not drift).
4. Confirm the ~30–50 MB/frame **runtime** streaming budget is respected (the 331 MB
   on-disk figure is compressed; runtime GPU per-frame is the number that matters, and
   is only observable at playback).

## Reproduction artifacts (not committed — under `M:\claud_projects\temp`)

- `svt_probe/` — throwaway UE 5.8 project (`SvtProbe.uproject`, PythonScriptPlugin only),
  10-frame probe (`import_probe.py`), staged frames 130–139.
- `svt_seq_full/` — full 300-frame staged VDBs (`vdb/`), `import_full.py`,
  `verify_svt.py`, and logs.
- Source VDBs live in WSL at `/home/boiko/thunderstorm/synthetic_seq/` (regenerable via
  `pipeline/vdbwriter/gen_synthetic.py` + `dense2vdb`).

Per project convention the throwaway UE project is **not** promoted to `unreal/` — the
real playback app is scaffolded later in Phase 1, now that we know exactly what SVT
import needs.
