# Phase 1 lighting/exposure pass — day scene achieved; MI-edit and frame-timeline discoveries (2026-07-16, session 4)

**One-line:** the scene now reads as full daylight with the storm legible at 35 km from both
standard views (`final_day_south.png` / `final_day_sw.png` in
`M:\claud_projects\temp\task5_visuals\`); getting there exposed that **material-instance
parameter edits never apply live over MCP** (only at the next PIE start), that yesterday's
density sweep was therefore blind, and that **frame 255 is a late-stage diffuse cloud, not
the mature storm** — the classic Cb shape lives around frame 150.

## Scene changes (all IN MEMORY — owner must Save All to persist)

| Knob | Was | Now | Why |
|---|---|---|---|
| PPV `AutoExposureBias` | −14.5 | **−13.0** | +1.5 EV; the single biggest "dusk" cause |
| Fog `FogDensity` | 3e-4 | **5e-5** | 35-km wash |
| Fog `FogHeightFalloff` | 1e-4 | **0.01** | fog was filling the whole troposphere; now hugs the surface |
| VolumetricCloud (template) | visible | **hidden** (`bVisible=false`) | camouflage — see findings |
| MI `Albedo Scale` | 0.18 | **0.9** | 0.18 = charcoal cloud; physical single-scatter albedo |
| MI `Density Scale` | 0.05 | **5.0** | 0.05 optically invisible in daylight |
| StormVolume `Frame` | 255 | **150** | see frame-timeline finding |
| Sun | 75000 lux, pitch −32, yaw 55 | unchanged | already physical |

The MI (`/Game/SVT_REAL/MI_SvtPlayback`) is also dirty. Editor showed "3 Unsaved" before
this session's edits; nothing here is on disk until the owner saves.

## Findings

### 1. The "dusk" look had three stacked causes
EV bias 1.5 stops too dark; fog with effectively no height falloff washing everything ≥20 km
into white; and the **template VolumetricCloud layer camouflaging the storm** — an ambient
cumulus field that looks exactly like the SVT storm's own material, plus a dense horizon
band. With it hidden, the storm is the only cloud in the sky and reads instantly. Keep it
hidden until the storm material is final; re-enabling later for ambience is a separate
judgment.

### 2. MI scalar edits do NOT apply live — they apply at world construction (next PIE start)
`set_scalar_parameter` updates the MI asset (readback confirms) but the running render never
picks it up: not in the editor world (proxy goes permanently stale after the session's first
PIE bounce; a `bVisible` off/on re-registration does NOT refresh it), and **not inside a
running PIE session either** — a 0.05-vs-0.9 albedo A/B inside live Simulate produced diffs
equal to pure capture drift (0.43 vs 0.46 mean). A fresh `StartPIE` rebuilds the material
state and applies whatever the asset then holds.

- **Correct sweep pattern: one Simulate cycle per parameter value** (set param → StartPIE →
  wait ~25 s for streaming → capture → StopPIE). `sweep5_cycle.py` implements it.
- The 2026-07-15 "MI edits apply LIVE into a running PIE session" claim is **retracted**;
  that session's sweep appeared live because it was punctuated by PIE restarts.
- **Yesterday's sweep2 (0.003→0.05) was blind** — all four density values rendered the same
  stale material; the visible differences between its captures were template-cloud animation
  (the cumulus field morphs on minute timescales, mean pixel drift ~16 — same magnitude as a
  real material change; a no-op control pair 45 s apart gives 0.46). Any A/B judgment made
  with the template cloud visible is suspect.
- Component/actor property edits (Frame, bVisible, fog, PPV settings) DO apply live,
  including into a running PIE world (path prefix `/Game/Maps/UEDPIE_0_SvtPlayback.`).

### 3. Frame timeline: 255 is NOT the mature storm
With mip-0 residency verified per frame (green bars), the sequence reads: **f83** small warm
boundary-layer puff (initiation); **f120** narrow tower + first rain shaft; **f150** classic
cumulonimbus — tower, spreading anvil, rain core (**recommended judging/hero frame**);
**f180** wide mature mass; **f210–270** progressively larger, smoother, dimmer late-stage
cloud. Prior docs' "frame 255 (mature storm)" label is misleading for visuals — 255 is a
physically-genuine dissipating-stage giant whose smoothness is in the data, not a streaming
defect. (Frame scan captures: `scan_f120…f270.png`.)

### 4. Streaming re-verified end to end (no regression)
`Requested Mip: 0.00`, ~7 MiB/s allocated, residency bars green within ~20 s for every frame
whose bar position fits the capture (83, 100, 120, 150 at 150 % DPI; bar x ≈ (8+idx·9)·1.5 —
indices ≳125 are off-capture, so verify with a frame <120, never by squinting at 255).

### 5. `Density Scale` saturates visually above ~1 with the engine default material
The MI's parent is **`/Engine/EngineMaterials/SparseVolumeMaterial`** (engine preview
material), not a project material. Response: 0.05→0.5 large change; 0.5→5→20 nearly none —
the storm stays a translucent milky mass and never develops a solid core or crisp cauliflower
edges (source data is also 325-m voxels — soft by construction). **"Anvil translucent, core
solid" is not reachable with this knob.** That is task #5's job: a custom volume material
with a physical extinction mapping from the cloud/ice channels (and per-hydrometeor optics),
plus self-shadow tuning. Current 5.0/0.9 is a placeholder that reads plausibly in daylight.

### 6. Method: numeric pixel diffs with a drift control
Eyeballing captures misled this project twice (sweep2; today's "density inert" confusion).
The cheap fix: PIL/numpy mean-abs-diff per A/B pair plus a no-change control pair to measure
drift (0.46 here). A real change is ≥10× drift; anything at drift level did not happen.

## Editor state left behind

- Overlay/log cvars verified 0; BP_ConsoleExec BeginPlay = the two idempotent debug-off
  resets (unchanged contract from teardown).
- Component: Frame=150, bVisible=true, bIssueBlockingRequests=false, StreamingMipBias=0.
- No PIE running. All debug scripts and captures in `M:\claud_projects\temp\task5_visuals\`
  (this session: `bl_*`, `step1…5_*`, `probe_*`, `ab*`, `sweep3/4/5_*`, `scan_f*`,
  `f83_*`, `final_day_*`).

## Still open (unchanged)

Rain/hail Niagara, lightning+thunder, landscape material (handoff tasks #5–#9); Y-flip;
package hosting (LFS vs out-of-repo); Python env lockfile hardening.
