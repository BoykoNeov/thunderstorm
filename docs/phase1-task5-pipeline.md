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

1. **In-editor visual streaming playback (OWNER) — BLOCKED: the volume does not render.**
   See "Render investigation (2026-07-15) — UNRESOLVED" below. On a real GPU (D3D12,
   RTX 5090) the volume is **absent from the frame** at every Density Scale from 2e-4 to
   **1e6**, correctly bound, placed and lit throughout. A density sweep spanning ten
   decades changing nothing means the ray marcher is integrating ~zero density — so this
   is not a tuning knob, it is a real defect somewhere between the material, the actor
   scale, and the capture method. **Do not open the level expecting a storm.**
2. **The UE placement rule is WRONG as written and must not be trusted by Phase 2.**
   Two errors found on 2026-07-15, both while setting the scene up:
   - **The Y-flip is broken.** Negating the frame transform's translation *moves* the box
     instead of *mirroring* it: the volume extends in +Y from its corner, so flipping only
     the corner lands the storm ~46 km off-axis (measured `bounds_origin.y = +4,637,500 cm`
     where x centred at ~125 cm). Mirroring the far corner
     (`location.y = -(translation.y + span_y) * 100`) is the likely fix — **unverified**.
   - **The ×100 scale itself is now in question**, not merely unconfirmed. A 25000× actor
     scale is a live suspect for the invisible volume (see below), and a control at scale 1
     is what would separate the two. Until the render works, treat the whole rule as
     unproven.
   `volume.ue_placement_rule` in the manifest has been amended to say so.
3. **Where the package lives (OWNER).** The charter requires deciding LFS vs out-of-repo
   "before the first package ships". This one is 0.46 GB — comfortably over the 10 MB
   plain-git line. It currently lives in WSL at
   `/home/boiko/thunderstorm/scenario_out/single_cell_500m/` and is regenerable in 7.5
   minutes from the CM1 run, so nothing is at risk while the decision is open.
4. ~~**Python env lockfile**~~ — **DONE (2026-07-15): `pipeline/ENVIRONMENT.md` +
   `pipeline/env-vdb.yml`.** Recorded as two separate envs in each one's native form,
   with **no `requirements.txt`**: system python3 is `EXTERNALLY-MANAGED` and pip-free, so
   a pip pin file would advertise a `pip install -r` reproducibility that does not exist.
   Worth knowing: the micromamba `vdb` env is a **runtime** dependency of `export` (not
   build-time-only — `dense2vdb` dynamically links its libs), and its python 3.14.6 is a
   *different interpreter* from the pipeline's 3.12.3; they never meet because the handoff
   is a file plus a subprocess. Spike-grade — `--explicit`/apt-pin hardening is Phase 2.

## Render investigation (2026-07-15) — UNRESOLVED

**The volume does not render.** Not "renders wrong" — absent, on a real GPU, with the
scene otherwise drawing correctly (default-level geometry, gizmo and engine banners all
appear in the captures; only the storm is missing).

### The thing that actually matters: `-nullrhi` cannot check a renderer

Everything below was found in one sitting *after* switching from `-nullrhi` to a real
D3D12 device. The prior session's build script reported **`verdict = READY`, six checks
PASS**, and every one of those checks was true of an in-memory object and false of the
artefact on disk. Under `-nullrhi` nothing renders, so nothing that only matters when
rendering can fail — a missing light costs nothing, an unsaved level costs nothing. The
checks were self-consistent and measured the wrong thing.

**Four defects `-nullrhi` reported as PASS:**

| Defect | How it passed |
|---|---|
| The level **never saved**. `new_level()` returned `False` (the map already existed), so every actor was spawned into a throwaway `/Temp/Untitled_1` world; `save_current_level()` then returned `False` and the return value was never read. The `.umap` on disk stayed stale for 35 minutes while builds reported success. | Checks inspected live objects, not the saved file. Fix: `EditorLoadingAndSavingUtils.save_map(world, path)` (returns `True`) + verify by re-loading **in a separate process**. |
| **No lights.** `new_level_from_template(TimeOfDay_Default)` contributed nothing; the saved level held exactly one actor. The template was chosen *specifically* to avoid an unlit volume. | An unlit volumetric is invisible only when something renders it. |
| **`set_actor_label` does not persist** through save — the actor came back labelled `HeterogeneousVolume`, not `StormVolume`, so a label lookup returned `None`. | Nothing looked the actor up from disk. |
| A density sweep fired **451 `HighResShot` requests** instead of 6 (the state machine ran off the end of its list; the `IndexError` was raised *after* the request, so it re-fired every tick) and wrote **zero** PNGs — while logging `SWEEP: DONE`. | The log said DONE. Nobody checked for the files. |

### What is ruled out

- **Density Scale.** Swept `2e-4 → 1e0 → 1e2 → 1e4 → 1e6`. Ten decades, no change, still
  black. A sweep that wide changing *nothing* means the marcher integrates ~zero density,
  which rules out calibration as the *cause* — and kills the "if it's blank, raise Density
  Scale" advice this doc previously gave.
- **Lighting / camera framing** — the rest of the scene renders; the camera is aimed at the
  volume's centre and its bounds are correct (46.5 × 46.5 × 16.25 km = 186×186×65 @ 250 m).
- **Trace distance** — a real find but **not the cause**: `r.HeterogeneousVolumes.MaxTraceDistance`
  defaults to **30000 cm = 300 m**, against our 46.5 km volume seen from 51 km. Raising it
  to 200 km changed nothing. **Keep this recorded anyway**: the default is tuned for
  metre-scale VFX puffs and *will* matter for a km-scale storm once the volume renders at all.

### Still open (ranked)

1. **Capture artifact.** The captures show the skydome banner repeated 3× — `HighResShot`
   was **tiling**, and tiled capture is known to drop some volumetric passes. If so,
   "renders nothing" is an artefact of *how I looked*, and the owner's live viewport was
   always the right instrument.
2. **The material samples the wrong attribute.** The static switches (`Density (Attributes A)`,
   `Clamp SVT Density`, `StaticSparseVolumeTexture`) were set **without verifying the names
   exist** — `set_material_instance_static_switch_parameter_value` no-ops silently on a bad
   name, the same silent-failure class as `save_current_level`.
3. **The 25000× actor scale defeats the marcher.** `scale3d(250) × 100`. Auto `StepSize(-1)`
   is plausibly computed in the component's *local* space (1 voxel = 1 unit), so the ray
   quits before reaching the dense core.
4. **`playing=False` samples an unstreamed frame.** An `AnimatedSparseVolumeTexture` may only
   stream during playback, so a pinned `frame=255` in a static view can be legitimately empty.

### The one ask that beats more of this

**Drag `/Game/SVT_REAL/frame` from the Content Browser straight into the viewport.** That
builds the engine's own default volume actor + material — the canonical path, which Python
refused (`spawn_actor_from_object` returns `None` for an SVT, with and without `-nullrhi`).
It separates "my hand-rolled material instance is wrong" from "km-scale volumes don't render"
in a single look, and it is the one thing that cannot be done headless.

## Doing the visual check (OWNER) — currently BLOCKED, see above

**The scene below does not currently show a storm.** The steps and UI walkthrough are kept
because they are correct *mechanically* and are what you would use once the render defect is
found — but the previous claim that this was "pre-built and asserted, just look at it" was
wrong, and the assertions behind it could not have caught any of the four defects above.

```
W:\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe ^
  M:\claud_projects\temp\svt_probe\SvtProbe\SvtProbe.uproject
```
Then open **`/Game/Maps/SvtPlayback`** (Content Browser → `Maps` → `SvtPlayback`). The volume
actor is labelled `StormVolume` in the level built by `build_v7.py` — earlier builds left it
as `HeterogeneousVolume`.

Scene contents (rebuilt by `M:\claud_projects\temp\task5\build_v7.py`, verified from a
separate process by `verify_v7.py`: 78 actors, lights present, volume bound, span 46.5 km):

| | |
|---|---|
| Volume | `/Game/SVT_REAL/frame` — 301-frame `AnimatedSparseVolumeTexture`, 186×186×65 |
| Material | `MI_SvtPlayback`, instance of `/Engine/EngineMaterials/SparseVolumeMaterial` |
| Playback | 25 fps, looping → **~12 s per simulated hour** |
| Size in world | **46.5 km** across (`span_x_km = 46.5`) |
| Level | from the `TimeOfDay_Default` template — an empty level has no light, and an unlit volumetric renders as nothing |

If the viewport is static, toggle **Realtime** (the viewport's clock icon, or `Ctrl+R`) —
without it the editor does not tick and the volume will sit on one frame, which looks
exactly like streaming being broken.

### Finding your way around (no UE experience assumed)

The editor's four panels: **Content Browser** (bottom — the project's files),
**Viewport** (centre — the 3D view), **Outliner** (top right — every actor in the level),
**Details** (bottom right — the selected actor's properties). If one is missing, they are
all under the **Window** menu.

1. **Launch.** Easiest is to double-click `SvtProbe.uproject` in Explorer at
   `M:\claud_projects\temp\svt_probe\SvtProbe\` — same as the command above. First open
   takes a while (shader compile); a "Compiling Shaders" counter in the bottom-right is
   normal, let it finish before judging anything.
2. **Open the map.** Content Browser → left tree → **Content** → **Maps** → double-click
   **SvtPlayback**. (Ignore whatever level opens by default.)
3. **Find the storm.** In the **Outliner**, click **StormVolume**. Then move the mouse
   over the viewport and press **F** — "frame selected" flies the camera to it. Pressing F
   with the cursor outside the viewport does nothing.
4. **Realtime.** Top-left of the viewport there is a row of icons; the **clock** toggles
   Realtime. Or hover the viewport and press `Ctrl+R`. **Do this first** — it is the single
   most likely reason the volume looks frozen.
5. **Fly.** Hold **right mouse button** in the viewport and steer with the mouse; **WASD**
   while holding it moves (Q/E = down/up). Still holding RMB, the **scroll wheel** changes
   fly speed — 46.5 km is large, so wind it up. The **camera icon** at the viewport's top
   right has the same speed setting as a slider.
6. **Scrub to the storm's peak.** With `StormVolume` selected, the **Details** panel has a
   *Heterogeneous Volume* section: untick **Playing**, then set **Frame** to `255`. Tick
   **Playing** again to resume the loop.
7. **Density Scale** (only if it looks blank or like a solid block). Content Browser →
   **Content** → **SVT_REAL** → double-click **MI_SvtPlayback**. In the Material Instance
   editor, the left **Parameter Groups** list has **Density Scale**; **tick its checkbox**
   to enable the override (greyed-out means it is inherited and your typing is ignored),
   then edit the number. The viewport updates live. **Ctrl+S** to keep a value.

**What to judge** (this is the part only you can do):

1. **Smoothness** — the actual question. Do the 301 frames advance without hitching,
   popping, or arriving visibly late as the storm grows and per-frame size climbs toward
   the 3.51 MB peak?
2. **Scale** — does the storm read **~46.5 km** across? This is free verification of a
   *provisional* finding (below): the ×100 conversion was measured under `-nullrhi`, which
   cannot prove what a real GPU does. **1.9 m or 4650 km means the placement rule is
   wrong**, not the streaming.
3. **Shape** — a storm rather than a boxy artefact; and given error #2 above, does the
   anvil look right now that snow is in `ice`?

### If you see nothing (or a solid block), read this before concluding "broken"

A blank viewport has several causes and only one of them is streaming. In order of
likelihood:

- **Density Scale is a guess.** Our channels are mixing ratios ~1e-3 kg/kg; the stock
  material is built for density grids ~0–1 and knows nothing about our units. Left at its
  default `1.0`, optical depth across a 10 km path would be ~5000 — an opaque black block.
  I set **`Density Scale = 2e-4`** on `MI_SvtPlayback` to put τ near 1, but that rests on
  an assumed UE extinction convention. **If it is blank, raise it; if it is an opaque
  block, lower it** — sweep it in decades (1e-5 → 1e-2). That is material tuning, **not**
  a streaming failure.
- **The loop starts before the storm exists.** Frame 0 is **2937 bytes** against 3.2 MB at
  the end — a warm bubble in a clear domain. Near-nothing at t=0 is *correct*. The storm
  develops over the loop and peaks around **frame 255** (t≈51 min). Scrub there before
  judging.
- **Colour is meaningless.** The default material maps our channels onto generic
  albedo/extinction; density comes from Tex A's R channel (cloud). This checks
  *streaming*, not final look — the real material is Phase 4.
- **Camera speed.** 46.5 km is big; raise the viewport speed or you will feel stuck.

### Finding (PROVISIONAL): UE does not auto-apply the SVT frame transform

Setting the scene up surfaced this, and it **sharpens the placement rule** (item 2). The
first build placed the actor at identity and its bounds came back **186 × 186 × 65 cm** —
a 1.9 m storm. `HeterogeneousVolumeComponent` lays the volume out at **1 voxel = 1 UE
unit** and *appears to ignore the asset's frame transform entirely*.

**This is measured under `-nullrhi`, and that is exactly what `-nullrhi` cannot settle.**
Whether the component folds `frame.scale3d` into its world bounds on a real GPU is a
render-path question. If it *does*, the ×100 below is 100× oversized and the volume is
4650 km wide with the camera inside it. The scale half is solid — 186 cm → 46.5 km, and
resolution/transform read back correctly, so the SVT data genuinely loaded — but the
conclusion is provisional until the owner's check confirms the storm reads ~46.5 km. The
manifest's `ue_placement_rule` is worded as provisional for the same reason: a wrong pin
here double-applies in Phase 2.

So "the asset carries the placement" is true only in the sense that it is the **source you
read it from** — UE will not apply it for you. The actor must apply the frame transform
**and** the units conversion together:

```
scale    = frame.scale3d   * 100          # 250 m/voxel -> 25 000 cm/voxel
location = frame.translation * 100        # with Y negated (CM1 right-handed -> UE left-handed)
```
which yields the correct 46.5 km span. This is still exactly one conversion site, and it
still reads the **asset**, not the manifest's `origin_m` — the double-apply trap is
unchanged. `volume.ue_placement_rule` in the manifest has been corrected to say so
explicitly, since the earlier wording ("applies ONLY the units conversion") could be read
as "UE places it for you", which is false.

## Reproduction

Pipeline code is committed (`pipeline/cm1post/`, `pipeline/export_scenario.py`; usage in
`pipeline/README.md`). Regenerate with `export_scenario.py bbox` (the gate) then
`export` — 7.5 min for 301 frames.

Not committed (regenerable, under `M:\claud_projects\temp\task5\`): `vdb/` staged frames,
`import_real.py` (the headless UE import + transform check, expectations annotated with
UE's trim behaviour), `regen_manifest.py`, `build_playback_level.py` (the owner's
playback scene), and logs. UE-side output is `/Game/SVT_REAL` + `/Game/Maps/SvtPlayback`
in the throwaway `svt_probe` project; per convention it is not promoted to `unreal/`.

The playback scene is **rebuildable at any time** — re-run:
```
cd M:\claud_projects\temp\svt_probe\SvtProbe
W:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe SvtProbe.uproject ^
  -ExecutePythonScript="M:\claud_projects\temp\task5\build_playback_level.py" ^
  -unattended -nosplash -nullrhi
```
It prints `PLAYBACK:` lines to `SvtProbe\Saved\Logs\SvtProbe.log` (**not** stdout) and
ends in `verdict = READY`. Two API notes for whoever touches it next:
`spawn_actor_from_object()` — the content-browser-drag actor factory — **refuses an SVT
from Python** (with and without `-nullrhi`), hence the explicit material instance; and the
static switch **`StaticSparseVolumeTexture` must be false**, or the animated frames are
sampled through the static path and never advance.
