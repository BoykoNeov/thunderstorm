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

Drag = orbit · wheel = zoom · `[` / `]` = step frame

## Status

Slice 1 (volume on screen: one frame, sun self-shadowing, flat ground). Next:
playback streaming (2), island + tilt-shift staging (3), precipitation (4),
layers/cross-sections (5), lightning event list (6).
