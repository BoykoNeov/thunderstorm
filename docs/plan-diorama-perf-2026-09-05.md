# Plan: Diorama performance + visuals — record of the 2026-09-05 pass and the remaining work (2026-09-05)

Written so a lesser model can execute the remaining items without re-deriving
anything. Part A is what was measured and changed (with the numbers, so a later
regression is recognizable). Part B is the verification recipe every remaining
item must use. Part C is the ranked remaining work, each item with exact files,
steps, acceptance criteria, and what is owner-gated.

Everything here is presentation/performance. Nothing touches physics, the
pipeline's science, or the package contract (`web_manifest.json`) — charter
principle 3 ("UE is a dumb player") applies to the diorama too.

---

## Part A — what the pass found and changed

All numbers: `single_cell_500m`, default view (`az=45 el=11 d=145 fov=34 sx=2`),
RTX 5090, Chrome headless (real GPU), per-pass GPU timers, `?acc=0&fps=240`.
"march" = the composite raymarch pass (pass 2), the cost that matters.

### A.1 The instrument came first (commit 6191717)

`?stats` now reports per-pass GPU milliseconds via `EXT_disjoint_timer_query_webgl2`
(`diorama/src/gputimer.ts`; EMA per pass; `window.__stats.gpu`; a top-centre HUD
line). `diorama/tools/statprobe.mjs` prints them per URL. rAF spacing alone was
misleading — vsync-quantized and noisy (a 48 ms median with a 7–111 ms spread).

### A.2 Finding 1 — a flattened branch ran the sun march everywhere (2.5×)

| probe (`rs=2`, 3200×1800) | march ms |
|---|---|
| frame 150 (hero), all defaults | 36 |
| frame 0 — a **completely empty** volume — haze off (`rays=0`) | 36 |
| same, `sun=2` / `sun=8` / `sun=28` / `sun=64` | 6.5 / 13 / 36 / 81 |
| `?debug=cost` heat map on that empty frame | **black: zero sun marches executed** |

Cost linear in the sun-step count while no sun march executed ⇒ the branch that
guards the sun march was *flattened* (predicated) by the shader compiler. Cause:
`texture()` (implicit LOD, needs derivatives) inside a per-pixel `if`. ANGLE's
D3D11 backend cannot sample with derivatives in divergent control flow, so it
executes both sides. Fix: every fragment-shader fetch became `textureLod(…, 0.0)`
(all these textures have exactly one mip level → identical filtering).
**36 → 14.5 ms; bit-identical on 2 of 3 verification views, 71 px within 2/255 on
the third.** The `?lc=1` light cache, measured "slower" in July, was a victim of
the same flattening; it now gives 5 ms.

**Rule (in `shaders.ts` above `VOL_COMMON`):** never write `texture(` in a fragment
shader of this viewer. There is no lint for it; grep before committing:
`grep -n "texture(u" diorama/src/shaders.ts` must list only the two vertex-shader
lines (830/831-ish, `PRECIP_VERT`).

### A.3 Finding 2 — the haze deck was the remaining cost (2.3×)

With real branches: `rays=0` dropped the hero frame 14.5 → 5.5 ms. The sunlit
haze (beauty step 3) is dense in the bottom ~30 % of the box, every one of those
samples ran the 28-step sun march, and the cloud itself was cheap (dense cores
hit the `tau > 9` early-out). Open air is exactly where the half-res 8-bit cache
is faithful, so haze-only samples (`s2.x + s2.y ≤ 1e-4`) now read `sunTransCache`
(one fetch); cloud/rain samples and the ground keep the live march. The cache is
therefore **always baked at upload** (~0.5 ms GPU per brick; it was `?lc=1`-only).
**14.5 → 6.2 ms; A/B `?hazelc=0`: 0.12 % of pixels differ, mean 1/255, confined to
the shadowed haze under the storm.**

### A.4 Finding 3 — short rays wasted samples (1.6×)

`dt = span / 280` gave a ray clipping a box corner 280 samples over a few km.
`?step=auto` (default) floors the step at (box horizontal extent / 280) — the
step the longest in-box ray already had, so no ray samples coarser than the
shipped worst case; short rays get fewer equal steps. **6.2 → 3.4 ms; A/B
`?step=0`: 1.4 % (frame 150) / 2.3 % (255) / 7.7 % (zoomed) of pixels differ,
mean 1/255, max 20; jitter-level, diffuse at cloud edges** (captures:
`M:\claud_projects\temp\diorama-perf\shots\step_*.png`).

### A.5 Streaming and pacing (commit ff0f64f)

- **GPU byte budget** (`diorama/src/budget.ts` `planRing`): slots + read-ahead
  from 300 MB (`?vram=MB`) instead of a fixed 24. The 63 MB supercell brick
  (540×540×54) gets the 10-slot floor (~630 MB) instead of 1.5 GB.
- **z-slab uploads** (`uploadSlabs`, `gl.ts uploadVolumeSlab`): bricks over 16 MB
  upload over consecutive rAFs; a slot is assigned but not `resident()` until
  the last slab + planes + cache bake land. Supercell worst rAF gap 222 → 28 ms.
  The 12.5 MB Phase-1 brick stays single-call (unchanged path).
- **Decoder pool** (`decoder.ts`): half the cores, max 4 gunzip workers,
  round-robin. One worker inflated 63 MB bricks serially.
- **fps-cap bug**: "16.7 ms since the last render" on a 144 Hz display rendered
  every third tick (20.8 ms = 48 fps, measured). The cap now keeps an ideal
  schedule and renders on the closest heartbeat: 60 → 16.65 ms mean.
- `?rs=auto` (`diorama/src/autoscale.ts`): dynamic render scale 0.5–1 from the
  GPU frame time (rAF-spacing fallback: down-only + backing-off probes). Under
  an artificial 4× load it settled at 0.5 (frame gap 33.7 → 17.8 ms); normal
  content stays at 1.0. **Off by default — owner call (C.1).**
- `?dither=ign` (default): interleaved gradient noise for the march start
  offset; 7 % less low-frequency residue than the hash white noise vs the
  converged still (3×3-blurred RMS 0.095 vs 0.102); same converged image.
- `?anim=0` (frozen animation clock) — the A/B recipe needs it; `?debug=cost`;
  `?steps=`, `?sun=`.

### A.6 End state

| | before | after |
|---|---|---|
| hero frame, `rs=2` march | 36 ms | 3.4 ms |
| hero frame, 1600×900 whole GPU frame | ~10 ms | ~2.5 ms |
| zoomed-in (`d=60`), `rs=2` march | 65 ms | 6.7 ms |
| overhead (`el=70`), `rs=2` march | 59 ms | 3.4 ms |
| supercell worst rAF gap during playback | 222 ms | 28 ms |

150/150 unit tests (`budget`, `decoder`, `autoscale` added). Captures for every
A/B under `M:\claud_projects\temp\diorama-perf\shots\`.

---

## Part B — verification recipe (use for EVERY item in Part C)

1. **Dev server.** `node M:\claud_projects\thunderstorm\diorama\tools\find-server.mjs`
   prints a live server's URL if there is one; otherwise
   `npx --prefix M:\claud_projects\thunderstorm\diorama vite M:\claud_projects\thunderstorm\diorama --port 5205`
   (do not `cd`; vite takes the root as a positional arg). Port 5173 usually
   belongs to another project on this machine.
2. **Cost probe** (real GPU, headless Chrome, per-pass GPU ms):
   ```
   node M:\claud_projects\thunderstorm\diorama\tools\statprobe.mjs "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
     "label=http://localhost:5205/?frame=150&rs=2&acc=0&fps=240&stats&<your params>"
   ```
   Always `acc=0` (a converged still skips the march and reads as free) and
   `fps=240` (lift the cap). Use `rs=2` so the march is off the vsync floor
   (~7 ms rAF here). `STAT_WINDOW_MS=9000` for a longer window. Compare the
   `march` number, not the rAF median.
3. **A/B captures** (bit-comparable):
   ```
   node M:\claud_projects\thunderstorm\diorama\tools\shot.mjs "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
     out_a.png "http://localhost:5205/?frame=150&acc=0&anim=0&precip=0&<A>" out_b.png "…&<B>"
   ```
   `anim=0` freezes ripples/veil/precip; `precip=0` removes the wall-time
   particles; `acc=0` gives the single-jitter live image (use `acc=1` for the
   converged still as a ground truth). Diff with numpy: report the count of
   differing pixels, max |Δ| and mean |Δ| over differing pixels, and SAVE the
   diff image. "Jitter-level" = mean ≈ 1/255 with no structure in the diff image.
   Views to cover: `frame=150` default, `frame=255`, `frame=150&az=100&el=25`
   (sun-side), `frame=150&d=60&el=20` (zoomed).
4. **Tests + types**: `npx --prefix <diorama> vitest run --root <diorama>` and
   `npx --prefix <diorama> tsc -p <diorama>\tsconfig.json --noEmit`. Pure logic
   goes in its own module with a test (Black Hole Lab discipline).
5. **One commit per item**, message stating the measured before/after and the
   A/B result. Never lower a default from a single probe.
6. **Owner-gated defaults**: anything with a taste component ships behind a
   param, default unchanged, with the A/B pair saved under
   `M:\claud_projects\temp\diorama-perf\<item>\` and listed in the commit message.

---

## Part C — remaining work, ranked

### C.1 Owner review of this pass's defaults — **DONE 2026-09-05**

**Ruling:** *"they seem almost if not completely identical, so go with the better
performance."* The three defaults stay as shipped; **`?rs=auto` becomes the default**
(`main.ts`, README). Measured no-op on this GPU: default and `?rs=1` both sit at
`rs=1` with identical pacing (raf median 6.90 ms). `?rs=1` is now what a
bit-comparable capture pins. The rest of this section is the record of what was
shown.


Three defaults changed with measured near-identity: `?hazelc=1`, `?step=auto`,
`?dither=ign`. Show the owner the A/B pairs in
`M:\claud_projects\temp\diorama-perf\shots\` (`haze_on/off_*`, `step_off/auto_*`,
`dith_crop_*`). Revert params exist for each. **DONE 2026-09-05: published as a
decision page —** https://claude.ai/code/artifact/96f08cea-0e5e-450f-b0b1-e640fef9b4f0
(crops at the measured diff centroids, the numbers beside each, and — per the
advisor — the dither pair shown as each variant's *error against the converged
still* rather than A-vs-B, since A-vs-B only shows that the noise moved). Also ask: should `?rs=auto` be the
default for the shipped viewer (recommended for outreach machines; it never
changes anything on a GPU that holds the cap)? If yes: flip `rsParam`'s default
in `main.ts`, update README's param table, and note it in `STATUS.md`.

### C.2 Supercell streaming throughput (decode-bound)

**Symptom:** `supercell_333m` (63 MB bricks, 601 frames) stalls at 60× even with
the decoder pool (probe `stalls=16` per 4 s). The GPU is idle (4.5 ms).
**Diagnose first** (do not guess): add to `decode.worker.ts` a `performance.now()`
around `loadBrick` and post `{id, buffer, ms}`; record `stats.decodeMs` in
`main.ts` (like `uploadMs`); print it from `statprobe.mjs`. Then:
- If decode ms × frames-per-second-needed > 1000 / poolSize: raise the pool cap
  (`decoderPoolSize(…, max)`) toward `hardwareConcurrency − 2` and make
  `MAX_INFLIGHT` = pool size (it is a hardcoded 4).
- If the fetch dominates (check `read_network_requests` timing or `performance`
  resource entries in the worker): the vite middleware streams from disk with
  no caching headers — fine on localhost; nothing to do here.
- If neither is enough: the real fix is a **coarser web tier** in the pipeline
  (`pipeline/cm1post/webvol.py` export at 2× decimation → 270×270×27, 8 MB
  bricks) selected per package by the picker. That is a pipeline task with its
  own go (the web manifest would carry `tiers[]`; the viewer picks by `?tier=`
  or by measured throughput). Scope it; do not start without the owner.
**Accept:** `stalls=0` over a 9 s probe at 60× on the supercell, or a written
finding that it is fetch/disk-bound.

### C.3 Half-resolution volume pass + depth-aware upsample (the next 3–4× lever)

Only needed if a target GPU cannot hold 60 fps at `rs=auto` = 0.5 with an
acceptable look. Design (§6 of the design doc calls it "the optional cheap win"):
1. Render pass 2 (composite) into a half-size `sceneT_half` — but the SURFACE
   shading (land/water) and background must stay full-res, so split pass 2:
   (a) full-res surface+background pass writing `bg` (no march), (b) half-res
   march pass writing premultiplied `(acc.rgb, T)` into an RGBA16F target,
   (c) full-res combine: `col = accUp.rgb + accUp.a * bg`, where `accUp` is a
   depth-aware bilinear upsample (weight the 4 half-res taps by
   `exp(-|d_full − d_half| · k)` using the g-buffer depth downsampled with MIN,
   so cloud edges against the landscape do not bleed).
2. The tone map moves to (c). The LDR overlays (dbz/w/cref/cut face) stay in (c)
   at full res reading the volume directly (they are cheap MIPs).
3. Param `?vol=0.5` (fraction); default 1 = today's path bit-identical.
**Accept:** march cost ≈ ¼ at `vol=0.5`; A/B at default view shows edge
differences only at cloud/land silhouettes, mean |Δ| < 2/255 elsewhere; owner
looks at a zoomed crop of the anvil edge against the sky before it can be a
default anywhere.

### C.4 Transmittance-weighted sun steps (cheap, ~10–20 % of what is left)

A sample whose accumulated transmittance `T` is already small contributes
little; its sun march can be coarser. In the hydro loop, before `sunTrans(p)`:
`int M = T > 0.25 ? uSunSteps : (T > 0.06 ? uSunSteps / 2 : uSunSteps / 4)` —
requires `sunTau` to take `M` as an argument (add an overload; `sunTrans` keeps
the uniform). Param `?sunadapt=0` to disable. **Accept:** measurable march
reduction on `frame=255` (the diffuse late frame with many low-T samples) and
A/B mean |Δ| ≤ 1/255. Owner-gated default? No — it is a numerical
approximation with a measured error bound; default on if the A/B holds.

### C.5 Coarse occupancy skip (only after C.3 and C.4, if still needed)

Bake per ring slot an R8 3D "max weighted extinction" at 1/8 grid (worker-side
reduction in `decode.worker.ts`, pure function + test; or a GPU reduction like
`bakeShadow`). In the march, when the block at `p` is empty AND the haze at
that height is below 1e-4, advance `t` to the block's exit. **Caveat:** the
domain warp moves lookups by ~1.5 voxels — dilate the occupancy by one block
(max-filter) or the warp will sample into skipped blocks and edges will
flicker. Accept only if the primary loop (measure with `sun=2`) drops ≥ 30 %
with A/B mean |Δ| ≤ 1/255.

### C.6 Precip pass on weak GPUs

60 000 rain instances × 6 vertices each run a 12-step view march + a sun
transmittance in the vertex shader. Cost here is < 1 ms, but it does not scale
with render scale. If a target GPU shows `precip` > 2 ms in `?stats`: scale
`RAIN.count` by `renderScale²` at draw time (`drawArraysInstanced(…, count *
rs*rs)`) and compensate `alpha` by `1/(rs*rs)` so the curtain keeps its density.
Param `?rainscale=`. Accept: precip ms ∝ rs² with the same curtain read in an
A/B crop.

### C.7 Browser matrix for the perf features

Chrome/ANGLE-D3D11 is measured. Check, on this machine, Firefox and Chrome with
`--use-angle=gl` and `--use-angle=vulkan`: (a) the `textureLod` build compiles
(it must — it is core GLSL ES 3.00), (b) `EXT_disjoint_timer_query_webgl2`
presence (Firefox: absent → `?rs=auto` must show `(raf)` mode in `?stats` and
still retreat under `steps=512&sun=64&d=60`), (c) the fps cap holds 60 on a
60 Hz monitor (drag the window to one if available). Record results in
README's Performance section.

### C.8 Visual items still open (owner-gated, from the design doc backlog)

Unchanged by this pass, listed so they are not lost: warmer sun/ambient split
in the cloud shading; shore-shallows water gradient; softer sky horizon band;
blue-noise texture dither (a 64×64 blue-noise tile beats IGN on gradients —
bake it in `noise3d.ts` style, `?dither=blue`, measure with the C.1 metric);
temporal reprojection during orbit (reuse the previous frame's converged pixels
by reprojecting through the two view-projection matrices — a large item; only
if the owner wants grain-free motion at low render scales). Slice 6 lightning
stays blocked on the Phase 4 event-list exporter.

### C.9 Housekeeping

- **Supercell package vs the staging slab (pre-existing, seen in this pass):**
  `supercell_333m` is 180 km wide, so at the default `sx=2` its box is 360 km on
  a 110 km slab — the anvil hangs far past the diorama and the sea (capture:
  `M:\claud_projects\temp\diorama-perf\shots\final_sc.png`). Options for the
  owner: per-package default display scale in the picker (`sx=1` when the box
  exceeds the slab), or a slab sized from the manifest grid (`land.ts`
  `GROUND_HALF` becomes a parameter; forests/towns/massifs scale with it).
  Presentation only; needs an owner pick before it is built.
- README "Status" paragraph still quotes "78 fps @ 1600×1000" from slice 3;
  replace with the A.6 table once C.1 has settled the defaults.
- `docs/plan-diorama-beauty-2026-07-17.md` step 0 ("light cache: no fps win")
  is superseded — add a one-line pointer to this file at its top.
- The `?lc=1` core-cache artifacts (8-bit quantization of `exp(-tau)`): if a
  weak GPU ever needs the cache for cloud too, store `tau` in R16F instead of
  `T` in R8 (`createShadowCacheTexture` format + `BAKE_FRAG` output +
  `sunTransCache` decode), which removes the stair-steps at the same cost.

---

## Owner calls collected here

1. Accept/revert the three defaults (C.1).
2. `?rs=auto` as the shipped default (C.1).
3. Coarser supercell web tier — a pipeline task with its own go (C.2).
4. Half-res volume pass default anywhere (C.3) — only after a zoomed-anvil crop.
