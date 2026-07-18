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
npm run dev     # http://localhost:5173  (?frame=NNN, ?rs=0.5 render scale)
npm test        # CPU mirrors: quantization decode, camera math, placement
npm run build   # typecheck + production build
```

Data is served from `../scenarios/single_cell_500m/web/` (see `vite.config.ts`),
produced by:

```
python3 pipeline/export_scenario.py export-web --run <cm1 run> --out <...>/web
```

then copied out of WSL. The bricks are gzipped uint8 log-quantized volumes;
`web_manifest.json` is the whole format contract (`pipeline/cm1post/webvol.py`).

## Controls

Drag = orbit · wheel = zoom · space = play/pause · `[` / `]` = step frame ·
bottom bar: play/pause, speed (15×–300×, a pure UI multiplier over storm
time), scrubber, storm-time clock.

URL params: `?frame=NNN` (start paused on a frame), `?rs=0.8` (render scale,
the quality/fps lever), `?stats` (expose `window.__stats` rAF/upload pacing
for the verification driver), `?az=45&el=11&d=145&fov=34` (starting view,
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
field is prognostic, not a diagnostic). The dBZ radar layer is a later step (5b).

### Beauty knobs (2026-07-18 beauty pass, steps 0–6)

Every visual-beauty effect is presentation-only (never physics) and each is
disableable from the URL for A/B comparison. Defaults are what ship.

| Param     | Default | Effect |
|-----------|---------|--------|
| `?lc=`    | `0`     | Baked sun-transmittance light cache (28-step sun march → 1 fetch). Correct but no measured fps win on this GPU; **off by default** because half-res trilinear softened the shadow terminator (`lc=1` re-enables the cache). |
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
Next in slice 5: dBZ diagnostic layer (5b, streams the shipped .dbz.gz channel),
then scale chip + clock/scrubber polish (5c). Slice 6 = lightning event list.
