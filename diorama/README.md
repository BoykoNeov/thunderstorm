# diorama/ — Storm Diorama web viewer

Isometric toy-scale viewer for scenario packages: the real CM1 storm, raymarched
in WebGL2 over stylized staging. TypeScript + Vite, **no engine** — architecture
adopted from the Black Hole Lab project. Design + slice roadmap:
`docs/design-diorama-web-viewer-2026-07-16.md`.

Like the UE app, this is a **dumb player**: it renders what the pipeline
exported and computes no science.

## Run

Easiest: double-click **`Start Storm Diorama.bat`** (repo root). It reuses a
dev server that is already serving *this* project if one is running — found by
fetching ports 5173–5204 and matching `index.html`'s `<title>` via
`tools/find-server.mjs`, never by port alone (vite climbs past busy ports, so
a port number identifies nothing) — and starts one only otherwise. Reuse is
safe at any age (vite transforms from disk per request); only a
`vite.config.ts` change needs a fresh start. The `<title>` string is
load-bearing for this — comments at both ends guard the rename.

```
npm install
npm run dev     # http://localhost:5173  (?frame=NNN, ?rs=0.5 render scale, ?rs=auto)
npm test        # CPU mirrors: quantization decode, camera math, placement
npm run build   # typecheck + production build
```

Data is served from `../scenarios/<name>/web/` (see `vite.config.ts`): every
scenario package that carries a `web/web_manifest.json` is served at
`/data/<name>/` and listed at `/scenarios.json`. A package is produced by:

```
python3 pipeline/export_scenario.py export-web --scenario <name> --out <...>/web
```

then copied out of WSL. The bricks are gzipped uint8 log-quantized volumes;
`web_manifest.json` is the whole format contract (`pipeline/cm1post/webvol.py`).

**Scenario selection (T7).** The viewer plays one package at a time; the picker
(bottom-left of the control bar, shown only when ≥2 packages are served) or
`?scenario=<name>` chooses it, defaulting to `single_cell_500m`. Packages differ
in grid (`single_cell_500m` is 208×208×72 @ 250 m, `single_cell_333m` is
126×126×54 @ 333 m), so a switch **reloads the page** (every GL resource is
sized to the grid) — preserving all other URL params (`az`, `layer`, `sx`, …).

## Controls

Left-drag = orbit · **right-drag = pan across the ground** · **middle-drag =
height** · wheel = zoom · space = play/pause · `[` / `]` = step frame ·
`\` cross-section axis · `,` / `.` slide the cut plane · `d` toggle the dBZ
radar layer · `b` toggle the scale bar · **data-layer panel (top-right)** picks
the field · bottom bar: play/pause, speed (15×–300×, a pure UI multiplier over
storm time), scrubber, storm-time clock.

The two pans are separate axes of one gesture, and neither touches the orbit
angles or zoom:

- **Right-drag** (or shift+left-drag) walks the look-at point **across the
  ground**, z held — sideways along the world-horizontal `right` vector,
  up/down along the ground-projected view direction, so dragging down pulls the
  far countryside toward you. Vertical motion divides by `sin(elevation)`
  because the ground is foreshortened on screen (clamped at 0.15 so a
  near-horizon camera cannot teleport the target).
- **Middle-drag** (or alt+left-drag) is the **elevator** — raises/lowers the
  look-at point for following a tall storm from cloud base to anvil. Same
  grab-the-world sense as the ground pan (drag down ⇒ you rise), so the two
  read as one gesture on different axes rather than opposites.

Both convert pixels at the target's depth, so the scene tracks the cursor at any
zoom. The shift/alt duplicates exist because plenty of trackpads make right- and
middle-drag awkward. The target is clamped to the diorama (ground floor at
z = 0, up to 40 km, ±60 km horizontally) so a stray drag cannot lose the storm.

URL params: `?frame=NNN` (start paused on a frame), `?rs=0.8` (render scale,
the quality/fps lever; **`?rs=auto`** holds the fps cap by moving it between
0.5 and 1 — the lesser-GPU mode), `?stats` (bottom-right readout of fps and
per-pass GPU ms, plus `window.__stats` for the probe driver), `?anim=0` (freeze
the wall-clock animation so two captures of one URL are bit-comparable), `?az=45&el=11&d=145&fov=34` (starting view,
deg/km), `?seed=1337` (staging), `?ts=0` (disable tilt-shift), `?sx=2`
(uniform display scale of the storm volume — proportions stay true; render-time
only, clamped 1–3; default 2 — the HUD states it, staging stays 1×),
`?precip=0` (disable the rain/hail particles), `?er=0.45` (cloud detail
noise strength: domain warp + edge wisps, 0 = raw voxel look), `?veil=0.12`
(rain-veil extinction weight, 0 disables the volumetric rain curtain).
The presentation-only beauty knobs (light cache, multi-scatter, silver lining,
sunlit haze, accumulation, FXAA, tonemap, split-tone) have their own table.

### Cross-section (slice 5a — education layer)

A movable false-color cut plane through the storm's interior. **Off by default**
(an inspection tool, not part of the shipped look). `?xsec=x|y|z` (or `1|2|3`)
picks the cut axis, `?xpos=0..1` the plane position, `?xmax=10` the total-
hydrometeor value (g/kg) mapped to the top of the colormap. At runtime, `\`
cycles the axis (off→x→y→z) and `,` / `.` slide the plane. The camera-side half
is clipped away so you see *into* the storm, and the exposed cut face is painted
with the **raw** decoded field — no erosion/veil beautification — on a
perceptually-uniform viridis map, with a DOM legend (honest g/kg units; the
field is prognostic, not a diagnostic).

### dBZ radar layer (slice 5b — labeled diagnostic)

`?layer=dbz` (or press `d`) swaps the storm to **radar reflectivity** — a
diagnostic (CM1/NSSL microphysics reflectivity, passed through the pipeline) and
shipped as the `.dbz.gz` plane, streamed here alongside each hydrometeor brick
only when the layer is active (the hydrometeor default fetches/uploads nothing
extra). The volume renders as a **max-intensity projection** — the peak dBZ
along each **view ray** (view-dependent; it equals the classic column-max
*composite reflectivity* product only looking straight down) — using a
recognizable NWS-style rainbow palette (green → yellow → red → magenta),
deliberately **not** the perceptually-uniform viridis: matching what a viewer
already reads as "a storm on radar" is the teaching goal. It is labeled
**DIAGNOSTIC** in the HUD and legend (dBZ units, charter rule). With a
cross-section active, the cut face paints dBZ too (same palette), pairing the
plan-view MIP silhouette with the
storm's vertical echo structure. Off by default → the shipped look is unchanged.

### Data-layer panel + updraft w (T8)

The **top-right panel** is the teaching-grade layer selector — one radio row per
shipped field (Hydrometeors / Radar (dBZ) / Updraft (w) / Composite reflectivity),
each carrying a **DIAGNOSTIC** badge iff the manifest flags that field a diagnostic
(the badge is *read* from the contract — `dbz.diagnostic`,
`extra_fields.w.diagnostic`, `plan_fields.cref.diagnostic` — never hardcoded, so it
cannot drift). It replaces keystroke-only discovery; `?layer=` and `d` remain as
accelerators. The updraft and composite-reflectivity rows are **feature-detected**
on `extra_fields.w` / `plan_fields.cref` — a package that predates them simply
doesn't offer them.

`?layer=w` (or the panel) swaps the storm to **updraft `w`** — the simulated
vertical wind (m/s), a *prognostic* field (no DIAGNOSTIC badge), shipped as the
`.w.gz` plane and streamed only when active (hydrometeor default unchanged, like
dbz). It renders as a **signed max-|w| projection** — the strongest vertical
motion along each **view ray**, keeping its sign — on a colorblind-safe
**coolwarm** diverging map (blue sinking ↔ red rising, no green). The colour
domain is **fixed at ±`scale`** (the constant `extra_fields.w.scale` = 80 m/s,
*not* a per-sequence max), so the same red means the same m/s in every package —
which is what makes the 500 m and 333 m cells comparable side by side. `?wclip=60`
sets a tighter *fixed* clip (more colour resolution, saturates above it);
`?wdead=2`/`?wramp=8` (m/s) tune the transparent deadband + alpha ramp so weak
environmental motion stays clear and the storm core reads solid. Cut face paints
`w` too.

### Composite-reflectivity radar plan view (T9 — labeled diagnostic)

`?layer=cref` (or the panel) shows **composite reflectivity** — the standard
top-down radar product from TV weather: the column-max dBZ, **view-independent**.
This is the deliberate counterpart to the dBZ layer above, which is a maximum
along the **view ray** and so changes as you orbit; `cref` is CM1's true column
maximum, computed in the pipeline and shipped as the 2D `.cref.gz` plan plane
(streamed only when active, hydrometeor default unchanged). It is painted **flat
on the toy landscape** as a radar footprint — a genuine map (plan) product, not a
volume — using the **same** NWS palette and dBZ scale as the dBZ layer (exact, not
approximate: CM1's `cref` is bitwise `dbz.max(axis=0)`, so one colour means one
dBZ in both). Because a flat ground map at the default low camera would read
edge-on, **entering the layer frames the camera near-overhead** (azimuth/distance
untouched, orbit stays free afterward; `?el=` pins a capture angle and suppresses
the auto-framing). Labeled **DIAGNOSTIC** in the HUD and legend, stated as
view-independent so it never reads as the same thing as the dBZ MIP.
Feature-detected on `plan_fields.cref`.

### Scale bar + storm-time clock (slice 5c — honest scale chip)

The HUD states the domain's true size (**derived from the manifest grid**, not
written into the text — a scenario with a different crop reports its own size),
and a live cartographic scale bar is drawn bottom-left. **On by default**;
`?scalebar=0` or key `b` hides it for clean captures.

The bar reports **real storm kilometres**: the storm draws at `?sx`× uniform
magnification while the staging land stays 1×, so the bar undoes the
magnification — at the default `sx=2` it reads 5 km where a scene-space bar
would read 10. Because the projection is perspective, the bar is exact on the
plane through the look-at point, which is what its "across the storm, at centre
depth" caption says. Verified on the GPU against the render's own view-projection
matrix (`mat.ts`, a code path independent of the bar's `camera.ts::kmPerPixel`):
0.03 % agreement at `sx=2`, i.e. sub-pixel.

The design doc's §7 originally asked for a "diorama scale ≈ 1 : N" chip. That
was **deliberately not built**: in a freely-orbited 3D scene there is no honest
single N — it changes with every zoom, and deriving one from screen size needs
the viewer's *physical* display dimensions (the CSS pixel's 1/96 in is nominal
and wrong on most monitors). A live bar carries the same teaching payload and
stays true at any zoom, so it supersedes the ratio.

The clock is prefixed **"storm time"** — it counts simulated time in the storm,
never wall time; the speed select is a pure multiplier over it (charter).

### Performance (2026-09-05 perf pass)

Measured with per-pass GPU timers (`?stats`; `tools/statprobe.mjs` prints them —
`EXT_disjoint_timer_query_webgl2`, an EMA per pass). Hero frame 150 of
`single_cell_500m`, default view, RTX 5090:

| Config | 3200×1800 (`rs=2`) composite march | notes |
|---|---|---|
| before the pass | 36 ms | the same on an EMPTY frame — cost did not depend on cloud content |
| explicit-LOD fetches | 14.5 ms | image bit-identical |
| + haze reads the baked sun cache | 6.2 ms | A/B `?hazelc=0`: 0.12 % of pixels, mean 1/255 |
| + step-length floor | 3.4 ms | A/B `?step=0`: 1–8 % of pixels, mean 1/255 |

At 1600×900 the whole frame is now ~2.5 ms of GPU (was ~10), so the viewer is
vsync-bound on this machine and has ~6× more headroom for lesser GPUs.

**The rule that found 2.5× of it:** every fetch in a fragment shader is
`textureLod(…, 0.0)`, never `texture(…)`. Implicit-LOD sampling needs
screen-space derivatives, and ANGLE's D3D11 backend cannot sample with
derivatives inside a per-pixel branch, so it *flattens* the branch — the 28-step
sun march ran for every primary sample of every pixel in the box, cloud or not
(diagnosed with `?debug=cost`, a heat map of sun-march samples per pixel, and the
fact that cost was linear in `?sun=` even where the heat map was black). All
volume/cache/noise/g-buffer textures have one mip level, so LOD 0 is the identical
filter.

Instruments and knobs (all presentation/perf, never physics):

| Param | Default | Effect |
|---|---|---|
| `?stats` | off | bottom-right readout: fps, drawn size, render scale, per-pass GPU ms; `window.__stats.gpu` |
| `?debug=cost` | off | heat map of sun-march samples per pixel (black → blue → green → red → white) |
| `?steps=` | 280 | primary march samples per ray |
| `?sun=` | 28 | sun-march samples per shaded sample (also the cache bake) |
| `?step=` | `auto` | primary step-length floor, display km; `auto` = box horizontal extent / steps (no ray coarser than the shipped worst case); `0` = the fixed-count march |
| `?hazelc=` | 1 | haze-only samples read the baked sun cache (one fetch) instead of marching; `0` = live march everywhere |
| `?dither=` | `ign` | march start-offset pattern: interleaved gradient noise (7 % less low-frequency residue vs the converged still) or `hash` (the original white noise) |
| `?rs=auto` | off | dynamic render scale 0.5–1 from the measured GPU frame time (rAF-spacing fallback where the timer extension is missing) |
| `?vram=` | 300 | GPU byte budget (MB) for the brick ring: slot count + read-ahead follow it (`budget.ts`); the 63 MB supercell bricks get 10 slots instead of 24 |
| `?anim=0` | on | freeze the wall-clock animation (ripples, veil, precip) for bit-comparable captures |
| `?fps=` | 60 | frame-rate cap. Fixed 2026-09-05: it used to render every third rAF tick on a 144 Hz display (48 fps); now it tracks the cap on average |

Streaming: bricks over 16 MB upload as z-slabs over consecutive rAFs (the
supercell's worst frame gap went 222 → 28 ms), and gunzip runs in a pool of
workers (half the cores, max 4). Full record + the remaining plan:
`docs/plan-diorama-perf-2026-09-05.md`.

### Beauty knobs (2026-07-18 beauty pass, steps 0–6)

Every visual-beauty effect is presentation-only (never physics) and each is
disableable from the URL for A/B comparison. Defaults are what ship.

| Param     | Default | Effect |
|-----------|---------|--------|
| `?lc=`    | `0`     | Use the baked sun-transmittance cache for **cloud** samples too (the cache is always baked now and serves the haze — see Performance). Off: the half-res 8-bit cache stair-steps dense cores; the live 28-step march inside cloud is cheap since the 2026-09-05 fix. |
| `?msw=`   | `0.55`  | Multi-scatter octave weight — lifts shadowed cloud cores from black to luminous grey (`msw=0` = single scatter). |
| `?msa=`   | `0.35`  | Per-octave optical-depth attenuation for the multi-scatter octaves. |
| `?silver=`| `0.15`  | Silver-lining forward spike on thin sun-facing edges (`silver=0` off). |
| `?rays=`  | `0.004` | Sunlit-haze **surface** extinction (km⁻¹) inside the box → crepuscular gloom under/beside the anvil + backlit atmosphere. Height-graded `exp(-alt/rayh)` (`rays=0` off). |
| `?rayh=`  | `1.5`   | Haze scale height (storm-km) — how deep the low haze deck feels. |
| `?acc=`   | `1`     | Idle temporal accumulation: averages successive jittered renders into a grain-free still whenever the view and storm frame hold still (freezes the animation clock while doing so — pausing freezes the whole miniature). `acc=0` keeps the always-live look. |
| `?fxaa=`  | `1`     | FXAA final pass — de-jaggies the staging silhouettes (mountains, towns, forest cones). `fxaa=0` off. |
| `?tm=`    | `agx`   | Tonemap: `agx` (holds white on the bright cauliflower, softer rolloff) or `aces` (the older ACES fit that skews orange near clipping). |
| `?split=` | `1`     | Warm/cool split-tone in the grade pass (warm highlights, cool shadows; mid-grey stays neutral). `split=0` off. Only active with tilt-shift on. |

## Status

Slices 1–4 done; beauty gate PASSED (owner GO, 2026-07-17). Slice 3 (staging,
reworked 2026-07-17 per owner request): the storm stands on a 110×110 km
square slab of seeded low-poly continuous countryside (decorative staging,
never sim terrain) — terraced rolling hills, three craggy mountain massifs on
a ring 20–38 km off the storm axis (rock/snow ramps; kept clear of the cloud
base), carved lakes with a z=0 water sheet, ~3.5k cone-tree forests and up to
8 toy towns of pitched-roof houses (`land.ts`, placement unit-tested) — with
a layered sediment side wall. A G-buffer mesh pass feeds the composite
raymarch, which shades land/water with the same sun shadow march as the cloud
— the storm's shadow sweeps the countryside; tilt-shift DOF finishes the
miniature read. The backdrop is a real horizon — dark storm sky over an
infinite sea, the slab floating above it — and the storm renders at 2×
uniform scale by default (owner request; `?sx=1` for true size — extinction
is divided by the scale so the bigger storm keeps the same look). 78 fps @
1600×1000 during 300× playback, zero stalls (pre-rework platter; slab mesh is
~2.4× the triangles, cost is G-pass raster only).
Slice 4 (precipitation): rain streaks and hail pellets as instanced quads,
gated in the vertex shader by the near-surface rain/graupelhail voxels of the
same streamed 3D textures (no CPU readback), shadow-tinted and view-attenuated
by coarse marches through the cloud, occluded by the terrain via the G-buffer
depth, wall-time animated, counter-scaled under `?sx`. Near-surface rain first
reaches the ground ~frame 200 of this run — the frame-150 hero is honestly
rain-free at the surface. Cost is <1 % (paused-frame A/B on the real GPU).
De-blocking + distant-rain pass (owner feedback): a small tileable 3D value
noise (noise3d.ts, baked once) drives (a) a ~1.5-voxel domain warp of the
volume lookup plus zero-mean edge wisps — the 250 m trilinear voxel facets,
collar striping and terraced rings dissolve into organic cauliflower while
cores and the (optically thin) anvil keep their opacity; and (b) a volumetric
rain veil: the rain channel splits out of the cloud extinction and renders as
a darker gray curtain modulated by vertically-stretched sheets scrolling down
on wall time. Rain streaks became many/fine/faint (60k × α 0.35) so they fuse
into that curtain at distance but stay individual lines up close. Costs ~16 %
on the worst frame (85→71 fps full-res; `?er=0&veil=0` reclaims it).
Slice 5a (cross-section) done (2026-07-18): a movable clip plane + false-color
cut-face sheet of the raw hydrometeor field, with a DOM legend (see the
Cross-section section above). Off by default, so the shipped look is unchanged.
Slice 5b (dBZ radar diagnostic) done (2026-07-18): streams the shipped `.dbz.gz`
plane (R8 ring parallel to the rgba bricks, allocated + fetched only when the
layer is active) and renders a max-intensity-projection (peak dBZ along the view
ray) + rainbow palette, labeled diagnostic; the cut face reads dBZ too (see the dBZ radar section
above). One `?layer=`/`d` toggle drives both. Off by default → shipped look
unchanged.
Slice 5c (scale chip + clock polish) done (2026-07-20): the HUD's domain extents
are derived from the manifest instead of hard-coded text; a live cartographic
scale bar (`b` / `?scalebar=0`) reports real storm km, GPU-verified to 0.03 %
against the render matrix; the clock is labelled "storm time"; and right-drag
pans across the ground while middle-drag changes height (`camera.ts::panGround`
/ `panAltitude`, clamped to the diorama) — which required `targetX`/`targetY`
in the accumulation `ViewKey`, the same trap slice 5a hit with the cut plane.
**Slice 5 is complete.**
Slice 6 = lightning event list (blocked on the Phase 4 pipeline exporter).
Perf pass (2026-09-05): composite march 36 → 3.4 ms at 3200×1800 on the hero
frame (explicit-LOD fetches un-flattened the sun-march branch; haze reads the
baked cache; step-length floor), per-pass GPU timers, `?rs=auto`, GPU byte
budget + slab uploads for big bricks, decoder pool, fps-cap fix — see
"Performance" above and `docs/plan-diorama-perf-2026-09-05.md`.
