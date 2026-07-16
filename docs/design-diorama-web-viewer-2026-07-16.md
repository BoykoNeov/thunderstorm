# Design: "Storm Diorama" — isometric toy-scale web viewer (2026-07-16)

**Status: DESIGN — approved direction, not yet built.** Owner picked the venue
(standalone web viewer), the data source (real CM1 scenario), and asked for this doc
before any code.

## 1. What this is

A second visualization axis, alongside the realistic UE5 playback app (which stays
untouched and continues later): a **miniature diorama** — a stylized, toy-like,
low-poly island seen from a high isometric camera, with the **real simulated storm**
towering over it as a raymarched volumetric cloud, complete with sun self-shadowing,
a storm shadow sweeping the ground, rain/hail curtains, and (later) lightning from
the pipeline's event list. Aesthetic reference: pastel stock-art dioramas (soft teal
water, flat-shaded mountains, tiny houses) — but the cloud is not clip-art, it is the
NSSL single-cell run playing back at full data resolution.

**Precedent:** `M:\claud_projects\Black hole` (Black Hole Lab) — TypeScript + WebGL2,
no engine, per-pixel raymarching in GLSL with pure, unit-tested CPU mirrors of the
shader math. That architecture is proven (visually and methodologically) and is
adopted wholesale here.

**Explicitly rejected assumption:** "browser = low-res, few frames." That constraint
applies to a *self-contained single-file artifact*, not to a local app with a dev
server. Served from disk, WebGL2 3D textures handle the full 208×208×72 grid at all
301 frames trivially; the RTX 5090 is orders of magnitude past what the march needs.

## 2. Charter alignment

- **"UE is a dumb player" generalizes to "viewers are dumb players."** The diorama
  viewer is a *second* dumb player of the same scenario package. All science stays in
  `pipeline/`; the viewer computes nothing physical — it maps precomputed fields to
  light. Adding this axis requires **zero** changes to `sim/` and no new physics.
- **Legibility over photorealism.** The diorama *is* the legibility play: a storm you
  can hold in your hand. Storm-time clock, honest scale chip (see §7), and the same
  annotation philosophy apply.
- **Vertical exaggeration** stays a render-time-only knob (1×–3×), never baked into
  data — identical convention to UE.
- **Diagnostics are labeled.** A dBZ radar-volume mode is a natural later layer; it
  renders from the `dbz` channel and is labeled diagnostic, as everywhere else.
- **Frame interpolation:** the open Phase 1 decision (output interval vs playback
  smoothness) gets its first concrete answer on this axis: **shader crossfade between
  adjacent frames** (two 3D textures bound, `mix()` by fractional storm time). 12 s
  output interval × crossfade looks continuous under any UI time compression. If it
  holds up visually, that's evidence for the same choice in UE.

## 3. Where it lives

New top-level folder **`diorama/`** in this repo (charter layout gains one line).
Vite + TypeScript + WebGL2 + vitest, **no engine, no three.js** — matching Black Hole
Lab. Raw WebGL2 is sufficient: one raymarch fullscreen pass, one low-poly mesh pass,
one instanced-particle pass, one post pass. If scene management ever genuinely hurts,
three.js is the named fallback — but the default is no-engine.

Node/npm only as dev tooling; nothing here touches the Python pipeline envs.

## 4. Data path — one new exporter output, no new science

The VDB sequence is the UE-facing format; browsers don't speak VDB. The pipeline
gains a **web volume export** (`export_scenario.py export --format web`, or a sibling
`export-web` subcommand) that reuses the *identical* `fields.build_channels` +
`regrid` path (invariant: bbox and export share one threshold/code path) and writes:

```
scenario_out/<name>/web/
  volume/f0000.bin.gz … f0300.bin.gz   # per-frame quantized bricks
  web_manifest.json                    # dims, channel map, quantization, timing
```

**Per-frame format:** the four hydrometeor channels (`cloud`, `ice`, `rain`,
`graupelhail`) quantized to **uint8 with a per-channel log mapping** (mixing ratios
span ~1e-4…1e-2 kg/kg; linear uint8 would crush the anvil). The mapping constants
live in `web_manifest.json`, and the browser undoes the log map in-shader (or bakes
extinction directly — decided in slice 1; the manifest records whichever contract
ships). `dbz` exports as a fifth optional plane for the later radar mode.

- Raw: 208×208×72 × 4 ch × 1 B ≈ 12.5 MB/frame. Gzipped (the field is mostly zeros —
  the VDB equivalent averaged 1.52 MB fp16): expect **~1–2 MB/frame, ~0.5 GB total**,
  same order as the VDB sequence.
- Browser decode: native `DecompressionStream('gzip')` in a worker — no JS inflate
  dependency.
- GPU residency: a **ring buffer of decoded RGBA8 3D textures** (e.g. 16 frames
  ahead), uploads off the render thread via the worker → `texSubImage3D`. Full-
  sequence residency (301 × 12.5 MB ≈ 3.7 GB) would even fit in 32 GB VRAM, but the
  ring is the design — it must also work on lesser GPUs.

Quantization is presentation-side decimation of already-exported channels — same
category as the int16 packing the charter already sanctions, no new physics. The
uint8 log-map round-trip error gets a unit test with stated bounds.

**Coordinate contract:** the web export carries the same CM1-native SI metres and the
same `ORIGIN_M` convention as the VDB (config.py is the single source). WebGL is
right-handed like CM1 — **no Y flip**; the metres → diorama-scene scale factor is
applied at scene placement in exactly one module (`src/scene.ts`), mirroring the
"conversion lives in ONE module" rule.

## 5. Rendering design

### 5.1 The storm (the centerpiece)

Fullscreen raymarch pass, GLSL, structured like Black Hole Lab's scene shader:

- Ray–box intersect against the volume bounds, fixed-step march (~192–256 steps at
  default quality) sampling the RGBA8 3D texture with hardware trilinear filtering.
- **Extinction** per species, mirroring the UE material's proven weights
  (`M_StormVolume`: 1.0 cloud / 0.10 ice / 0.02 rain / 0.005 graupelhail × a global
  extinction scale, default tuned by sweep). Same numbers, one cited source
  (docs/phase1-svt-custom-material-2026-07-16.md), so the two axes stay visually
  consistent.
- **Sun single scattering with a real shadow march:** at each sample, a secondary
  march toward the sun (~24–32 coarser steps) accumulates optical depth → the cloud
  self-shadows: dark flat base, bright cauliflower top, glowing anvil rim. This is
  the "beautiful raytracing and shadows" ask, and it's the standard technique —
  cheap on this GPU.
- Henyey–Greenstein phase (forward lobe ~0.6 + small back lobe), a "powder"/beer
  term for puffy edges, and an ambient sky term with a vertical gradient so shadowed
  undersides read blue-grey, not black (the lesson of the UE self-shadow-black fight).
- **Temporal crossfade:** two frame textures bound; `mix(sampleA, sampleB, fract)`
  by fractional storm time (§2).
- Tone map + soft bloom reused conceptually from Black Hole Lab's HDR pipeline.

### 5.2 The diorama staging

- **Island:** procedural low-poly heightfield → flat-shaded mesh (computed once on
  CPU, vitest-able), pastel palette from the reference image: green plateau, sand
  rim, painted mountains, teal water plane with a simple animated normal ripple.
  The island is **decorative staging, not sim terrain** — the Phase 1 scenario is
  flat — and the doc/UI must never imply otherwise. When Phase 3 terrain scenarios
  exist, the island mesh can be built from the scenario's real terrain heightfield
  instead; the staging slot is designed for that swap.
- **Storm shadow on the ground:** where a primary ray hits island/water, march from
  the hit point toward the sun through the volume → the storm's shadow sweeps the
  toy landscape as it evolves. Highest-value single effect for the miniature
  illusion.
- **Camera:** orbit controls (reuse Black Hole Lab's `camera.ts` pattern), high
  elevation (~30–40°), long focal length blending toward orthographic for the
  isometric read.
- **Tilt-shift DOF** post pass (blur ramp by distance from a horizontal focus band) —
  the classic miniature-faking cue — plus a pastel background gradient instead of a
  physical sky.
- **Diorama scale:** the 52 km domain renders as a tabletop object. This is pure
  presentation scaling in `scene.ts`; data stays SI. Houses/trees are garnish and
  deliberately out of scale (a true-scale house would be sub-pixel); the scale chip
  (§7) keeps it honest.

### 5.3 Precipitation

Rain and hail as **instanced GPU particles driven by the near-surface volume
slices** — the vertex shader samples the bottom voxel layers of `rain` / `graupelhail`
directly from the same 3D texture to gate spawn density and tint (no CPU readback, no
separate surface-texture stack needed for v1; when the Phase 2 pipeline ships proper
qr/qg surface textures, the viewer switches to those — same manifest, per charter).
Rain = elongated streaks with slight wind shear tilt; hail = white pellets, sparser
and faster. Under vertical exaggeration, fall streaks counter-scale per the charter
invariant (particle motion stays plausible).

### 5.4 Lightning

Renders **only** from the pipeline's lightning event list (positions/times/polarity —
Phase 4 pipeline work). Until that exists, no lightning; no viewer-side flash-rate
heuristics (physics through simulation — the viewer never invents events). The design
reserves: point-light flash inside the volume (one-frame boost in the march's ambient
term at the event position) + a procedural stepped-leader streak mesh, timed off the
event list.

## 6. Performance envelope

The march is the cost: at 1440p, ~230 primary steps × ~28 shadow steps only inside
the (small) volume interior — far below the per-pixel adaptive-RK4 geodesic budget
Black Hole Lab already sustains on this machine. **Render scale** is the quality
lever (cost falls with its square; drawn pixels stay exactly as authored), same as
Black Hole Lab; HUD canvas keeps true DPR. Optional cheap win if ever needed: half-res
volume pass + bilateral upsample. Not designed in until measured.

## 7. UI / education layer (thin at first)

- Storm-time clock (frames carry storm-time stamps; playback speed is a pure UI
  multiplier — charter convention).
- Play/pause/speed, frame scrubber.
- **Scale chip**: "diorama scale ≈ 1 : N — this storm is 52 km wide, 18 km tall"
  so the toy framing teaches rather than misleads.
- Vertical-exaggeration slider (1×–3×).
- Later, selectable layers: hydrometeor volume (default) / dBZ radar volume
  (labeled diagnostic) — the same manifest-driven layer idea as the UE app.

## 8. Testing (Black Hole Lab discipline)

Pure CPU modules with vitest coverage; GLSL mirrors tested CPU code where math is
shared:

- quantization: uint8 log-map round-trip error bounds per channel
- manifest parsing + timing (frame index ↔ storm time, crossfade fraction)
- ray–box intersection, camera projection (isometric blend), orbit controls math
- island heightfield generation (deterministic, seeded)
- a `?dbg` NaN/Inf render-target scan, ported from Black Hole Lab

Visual verification is by eye against captures — and *unlike* the UE `-nullrhi`
trap documented in Phase 1, the browser always renders on the real GPU; a screenshot
is always evidence.

## 9. Slice roadmap

1. **Volume on screen** — web exporter (pipeline) + loader/decoder + single-frame
   raymarch with sun shadow march, orbit camera, tone map. *Gate: frame 150 (the
   hero Cb) reads as a sunlit cumulonimbus over a flat ground plane.*
2. **Playback** — ring-buffer streaming, worker decode, time controls, temporal
   crossfade. *Gate: 0–60 min plays smoothly at 60 fps with no upload hitches.*
3. **Diorama staging** — low-poly island + water, pastel palette, tilt-shift DOF,
   background, storm ground-shadow. *Gate: a static screenshot reads as "toy
   diorama with a real storm," side-by-side with the reference image.*
4. **Precipitation** — rain/hail instanced particles off near-surface slices,
   exaggeration counter-scaling.
5. **Layers + education** — dBZ mode, scale chip, clock/scrubber polish.
6. **Lightning** — event-list playback (blocked on Phase 4 pipeline exporter).

Slices 1–3 are the "is this beautiful?" gate; stop/reassess after 3.

## 10. Open decisions (owner)

- **Go/no-go on slice 1**, and whether it may start before the UE track resumes.
- **Repo placement confirmed?** `diorama/` top-level (this doc's assumption) vs a
  separate repo. Top-level is recommended: it shares the scenario-package contract
  and the docs/ provenance trail.
- Whether the web export ships inside the scenario package (`web/` subfolder — the
  package remains the one durable artifact, recommended) or as a separate derived
  folder. Interacts with the still-open LFS vs out-of-repo decision.
