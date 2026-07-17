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
Next: layers/cross-sections (5), lightning event list (6).
