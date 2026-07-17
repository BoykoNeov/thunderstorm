# diorama/ — Storm Diorama web viewer

Isometric toy-scale viewer for scenario packages: the real CM1 storm, raymarched
in WebGL2 over stylized staging. TypeScript + Vite, **no engine** — architecture
adopted from the Black Hole Lab project. Design + slice roadmap:
`docs/design-diorama-web-viewer-2026-07-16.md`.

Like the UE app, this is a **dumb player**: it renders what the pipeline
exported and computes no science.

## Run

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
deg/km), `?seed=1337` (island), `?ts=0` (disable tilt-shift), `?sx=2`
(uniform display scale of the storm volume — proportions stay true; render-time
only, clamped 1–3; default 2 — the HUD states it, staging stays 1×).

## Status

Slices 1–3 done. Slice 3 (staging): the storm stands on a 74-km water platter
with a seeded low-poly terraced island (decorative staging, never sim
terrain) and a layered side wall. A G-buffer mesh pass feeds the composite
raymarch, which shades land/water with the same sun shadow march as the cloud
— the storm's shadow sweeps the island; tilt-shift DOF finishes the miniature
read. The backdrop is a real horizon — pastel sky over an infinite sea, the
platter floating above it — and the storm renders at 2× uniform scale by
default (owner request; `?sx=1` for true size — extinction is divided by the
scale so the bigger storm keeps the same look). 78 fps @ 1600×1000
during 300× playback, zero stalls. Beauty-gate review is with the owner.
Next: precipitation (4), layers/cross-sections (5), lightning event list (6).
