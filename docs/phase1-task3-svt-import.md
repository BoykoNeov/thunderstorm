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
  `density`, so the fallback packs the grids sequentially into 2 attribute textures ×
  4 components at Float16, **in VDB grid file order**. Grid identity was traced end to
  end (not merely the 4+1 format shape):
  - `gen_synthetic.py` writes channels `[cloud, ice, rain, graupelhail, dbz]`;
    `dense2vdb.cpp` pushes one FloatGrid per channel **in that order**; OpenVDB
    preserves write order; UE's `GetOpenVDBGridInfo` iterates `Stream.getGrids()` and
    assigns `Index` 0,1,2,… **without sorting**
    (`SparseVolumeTextureOpenVDBUtility.cpp:225`).
  - ⇒ **Tex A (RGBA16F): R=cloud, G=ice, B=rain, A=graupelhail; Tex B (R16F): R=dbz** —
    reproducing the `phase1-svt-budget.md` channel map exactly.
  - **Caveat (mechanism):** this correct mapping comes from UE's *default file-order*
    assignment, which reads **no manifest**. That is in tension with the project
    contract ("UE reads the mapping from the manifest, never hardcodes it"). Driving the
    import with explicit `UOpenVDBImportOptionsObject` options from the scenario manifest
    is a **real-pipeline TODO** (task 5) — for the spike, matching file order is
    sufficient and was verified.

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

## Result 4 — static-bbox-center binding test passes (autonomously, not owner-gated)

`phase1-svt-budget.md` names three binding tests; frame-count and multi-grid are covered
above. The third — **bbox center must be static across the sequence** — has teeth here
because our sparsity comes from *thresholding*, so the active AABB **grows** as the anvil
spreads (frame 0 = narrow tower, frame ~150 = wide mature anvil). Two independent
confirmations that UE nonetheless produces a static box:

1. **Code:** the animated-import branch computes **one union** `VolumeBoundsMin/Max`
   across all frames via `ParallelFor` + `ExpandVolumeBounds`
   (`SparseVolumeTextureFactory.cpp:566–624`), then passes that *same* `VolumeBoundsMin`
   into every frame's `ConvertOpenVDBToSparseVolumeTexture` (`:684`). The per-frame
   growth is absorbed into one fixed box.
2. **Asset API (`transform_check.py`):** `AnimatedSparseVolumeTexture` exposes a
   **single shared `get_frame_transform()`** (no per-frame overload), so per-frame center
   drift is not even representable. Measured: translation **(0, 0, 0)**, scale3d
   **(250, 250, 250)**, volume_resolution **160×160×64**.

> **Units-contract note (not a task-3 issue):** scale3d = 250 is the raw OpenVDB voxel
> size (250 **m**) carried straight into the SVT transform. The CM1-meters → UE-cm (and
> Y-flip) conversion is applied at **actor placement**, which is where the pipeline's
> single coordinate/units module lives — a UE-app concern, not an import concern.

> **Readback footnote:** the correct API is `get_num_frames()` (there is **no**
> `get_frame_count`). An early full-run log line showed `frame_count = None` purely
> because the probe script called the wrong method name; the asset always held 300
> frames (confirmed by `verify_svt.py` and the 331 MB size).

## Binding-tests scorecard

| Binding test (`phase1-svt-budget.md`) | Status | Evidence |
|---|---|---|
| Format v225 read by UE | ✅ PASS | bundled openvdb 13.0.0, FILE_VERSION 225; 300-frame import |
| Frame-count (few-hundred, not 1) | ✅ PASS | `get_num_frames()` = 300; import 21 s |
| Multi-grid ≤ 2 tex / ≤ 8 ch, one transform | ✅ PASS | RGBA16F + R16F; grid identity traced (Result 2) |
| Static bbox center across sequence | ✅ PASS | union box + single shared transform (Result 4) |
| **Visual streaming playback** | ⏳ owner-gated | needs editor GUI (below) |

## What is still owner-gated (Handoff)

Only the **visual streaming playback** half needs the editor GUI and human eyes — it
cannot be validated headless:

1. Open `SvtProbe` in the UE 5.8 editor (`M:\claud_projects\temp\svt_probe\`).
2. Place a **Heterogeneous Volume** actor; assign a material with a **Sparse Volume
   Texture** sampler bound to `/Game/SVT/frame`; enable the material's **Animated SVT**
   / frame-driving input.
3. Scrub / play all 300 frames and watch for streaming **hitches** and correct
   condensate/dBZ appearance (channel binding is R=cloud, G=ice, B=rain, A=graupelhail
   in Tex A; R=dbz in Tex B — see Result 2).
4. Confirm the ~30–50 MB/frame **runtime** streaming budget is respected (the 331 MB
   on-disk figure is compressed; runtime GPU per-frame is the number that matters, and
   is only observable at playback).
5. Apply the meters→cm units conversion when setting the actor transform (see the
   units-contract note in Result 4).

## Reproduction artifacts (not committed — under `M:\claud_projects\temp`)

- `svt_probe/` — throwaway UE 5.8 project (`SvtProbe.uproject`, PythonScriptPlugin only),
  10-frame probe (`import_probe.py`), staged frames 130–139.
- `svt_seq_full/` — full 300-frame staged VDBs (`vdb/`), `import_full.py` (build),
  `verify_svt.py` (frame count / formats), `transform_check.py` (static-bbox), and logs.
- Source VDBs live in WSL at `/home/boiko/thunderstorm/synthetic_seq/` (regenerable via
  `pipeline/vdbwriter/gen_synthetic.py` + `dense2vdb`).

Per project convention the throwaway UE project is **not** promoted to `unreal/` — the
real playback app is scaffolded later in Phase 1, now that we know exactly what SVT
import needs.
