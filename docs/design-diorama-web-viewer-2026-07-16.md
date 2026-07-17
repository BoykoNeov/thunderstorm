# Design: "Storm Diorama" — isometric toy-scale web viewer (2026-07-16)

**Status: SLICE 1 GO (owner, 2026-07-16).** Owner picked the venue (standalone web
viewer), the data source (real CM1 scenario), reviewed this doc and clarified:
the **storm itself is never low-poly** — always the raymarched volume (only the
staging is stylized); the palette (incl. teal water) is a placeholder, not a
requirement; camera must eventually be movable (orbit ships early since it is
nearly free); **cross-section views** (horizontal/vertical slices through the
storm) are a wanted later feature (§7); no view-export/recording feature is
needed; home is the `diorama/` subfolder of this repo, code committed.

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
  CPU, vitest-able). Palette is a **placeholder to be tuned by eye with the owner**
  (the reference image's green plateau / sand rim / teal water is a starting point,
  not a requirement); water gets a simple animated normal ripple.
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
- **Cross-sections (owner-requested, later):** horizontal and vertical slice planes
  through the storm — a movable clip plane in the raymarch plus a flat slab view of
  the sliced field (hydrometeors or dBZ). The 3D texture makes this nearly free to
  render; the work is UI.

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
   **DONE 2026-07-16** — gate met (tower + anvil + outflow ring + ground shadow;
   verified by headless-Chrome captures on frames 150 and 255). Real numbers:
   the full 301-frame web export is **89 MB total, peak 0.53 MB/frame** (gzip
   eats the sparse uint8 bricks), 630 s export. Lighting constants are a first
   by-eye pass over a slow screenshot loop — owner tunes live in the browser.
   Bonus already visible in captures: rain-shaft haze under the core (the rain
   channel at work) and the cold-pool outflow cloud ring.
2. **Playback** — ring-buffer streaming, worker decode, time controls, temporal
   crossfade. *Gate: 0–60 min plays smoothly at 60 fps with no upload hitches.*
   **DONE 2026-07-16** — gate met, measured headful on the real display (RTX
   5090, ANGLE D3D11): **80 fps at render scale 0.8 at both 60× and 300×
   playback, zero buffering stalls over full-sequence loop sweeps, upload cost
   p50 ≈ 0.7–1.9 ms / p95 ≤ 3.4 ms**. Full-res on a 150 %-DPI display
   (~3.2 Mpx) is ~51 fps — GPU-bound in the march, not in streaming; `?rs=` is
   the sanctioned quality lever (§6). Design as built: a module worker does
   fetch + native gunzip and transfers decoded 12.5 MB bricks zero-copy; a
   **24-slot** RGBA8 3D-texture ring (~300 MB) streams ≤ 1 `texSubImage3D` per
   rAF; the storm-time clock **holds rather than skips** when the ring
   underruns (observed only during initial page load); crossfade decodes each
   frame then mixes in q space (mixing ratios are linear). Two lessons worth
   keeping: (a) the ring capacity must comfortably exceed the protected window
   — with only ~2 rotating slots the first cut showed 50–77 ms upload spikes
   and cascading buffering stalls (GPU-saturation backpressure); (b) the
   **sun-shadow march samples the nearest frame instead of crossfading** —
   imperceptible at 12 s frame spacing, and it took full-res from 29 → 51 fps
   since the ~28 secondary samples dominate fetch cost. First concrete
   evidence for the §2 interpolation answer: 12 s output × shader crossfade
   reads as continuous motion at every speed (15×–300×); distinct intermediate
   states verified by capture at uMix = 0.5.
3. **Diorama staging** — low-poly island + water, pastel palette, tilt-shift DOF,
   background, storm ground-shadow. *Gate: a static screenshot reads as "toy
   diorama with a real storm," side-by-side with the reference image.*
   **DONE 2026-07-16** — gate met (headless captures at frames 150 and 255 plus
   alternate orbit angles): the storm stands on a 74-km circular water platter
   with a low-poly terraced island and a layered "resin base" side wall against
   a plain pastel backdrop — the frame-255 outflow engulfing the island is the
   money shot. As built: a G-buffer mesh pass (albedo + flat normal + real
   depth; projection unit-tested against the raymarch's ray generation,
   including the depth→ray-distance reconstruction) feeds the existing
   composite pass, which shades land/water per pixel with the *same* sunTau
   shadow march the cloud uses — the storm's shadow sweeps the island (§5.2's
   highest-value effect came free). Island generation is pure CPU,
   seeded/deterministic, vitest-covered; it is decorative staging and the HUD
   says so ("island & water are decorative staging, not simulation data").
   Water is one flat disk with analytic ripple normals (amplitude fades with
   camera distance — full-strength ripples moiré at 100+ km), fresnel backdrop
   reflection, soft sun glint. Tilt-shift is a two-pass variable-radius
   separable blur keyed to a horizontal focus band pinned to the projected
   platter centre, plus +13 % saturation and a gentle vignette; ?ts=0 disables
   it, ?az/?el/?d/?seed override view/island for by-eye tuning. Perf: 78 fps at
   1600×1000 during 300× playback with staging + DOF, zero stalls, upload p95
   2.8 ms — no regression vs slice 2. **Owner feedback round (2026-07-17):**
   finer mesh (0.27 km cells, less jitter — "less blocky"), island grown to
   ~30 km with named features (snowcapped summit cone, carved lagoon bay with
   sand rim, offshore islet), and the backdrop brightened from grey to a
   pastel blue-white studio gradient (vignette halved). Tuning lessons:
   surface lighting needed
   ~half the sun weight the cloud gets or the whole scene reads milk-white
   through ACES; slope-threshold rock colouring on a jittered mesh speckles
   (threshold 0.72, not 0.82); the platter must cover the volume box's
   half-diagonal (37 km ≥ 36.8 km) or ground-level outflow floats past the rim.
   **Owner feedback round 2 (2026-07-17):** (a) the studio gradient replaced by
   a **real horizon** — pastel sky over an infinite sea plane at z = −6 km (below
   the slab bottom, so the platter still floats); the sea's distance fog is
   deliberately capped at 0.78 because fully honest fog converges to exactly the
   haze colour at grazing angles and *erases* the horizon line — the residual sea
   colour is what draws it. Seeing a horizon at all constrains the camera:
   elevation must be under ~fov/2, so the default view moved from el 33°/fov 22°
   to el 11°/fov 34°/d 145 (?fov now a URL param). (b) **2× vertical
   exaggeration by default** (?zx, clamped 1–3, render-time only per charter):
   implemented by stretching the volume box in `volumeBox(man, zx)` — sampling,
   ambient height grading, surface shadowing and the ground shadow all follow
   automatically; the sun-march occluder cap scales with it (uShadowKm = 15·zx);
   staging stays 1× and the HUD states the exaggeration honestly. The DOF band
   widened 0.20 → 0.26 — at 2× the anvil sits far above the focus line and the
   tight band smeared it entirely.
4. **Precipitation** — rain/hail instanced particles off near-surface slices,
   exaggeration counter-scaling.
5. **Layers + education** — dBZ mode, cross-section slice planes, scale chip,
   clock/scrubber polish.
6. **Lightning** — event-list playback (blocked on Phase 4 pipeline exporter).

Slices 1–3 are the "is this beautiful?" gate; stop/reassess after 3.
**Slices 1–3 complete (2026-07-16) — the beauty gate review is now with the
owner** (run `npm run dev` in diorama/ and orbit around frames 150 and 255;
palette constants live in src/island.ts and the shader palette block in
src/shaders.ts, all placeholder-by-design).

## 10. Decisions resolved / still open

- **Slice 1: GO** (owner, 2026-07-16) — proceed before the UE track resumes.
- **Placement: `diorama/` subfolder of this repo** (owner-confirmed). Code is
  committed; scenario data stays out of plain git per the data policy.
- **No view export/recording feature** — screenshots are the owner's own business.
- Still open: whether the web export ships inside the scenario package (`web/`
  subfolder — recommended) or as a separate derived folder. Interacts with the
  still-open LFS vs out-of-repo decision.
