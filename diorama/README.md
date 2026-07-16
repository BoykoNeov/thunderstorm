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
for the verification driver).

## Status

Slice 2 (playback): a decode worker inflates bricks off the main thread; a
24-slot ring of 3D textures streams ≤1 upload per rAF; the shader crossfades
the two frames bracketing fractional storm time (the clock holds, never
skips, if the ring underruns). Measured: 80 fps @ rs=0.8 at 60×–300×, zero
stalls, uploads p95 ≤3.4 ms. Next: island + tilt-shift staging (3),
precipitation (4), layers/cross-sections (5), lightning event list (6).
