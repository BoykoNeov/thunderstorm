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

### C.2 Supercell streaming throughput — **DONE 2026-09-06: coarser export, no tiers; 6.53x fewer bytes, 682 -> 7 stalls**

**Owner ruling (2026-09-06):** *"i think a lower resolution will be ok anyway - for
the diorama we dont need that superhigh export resolution - also - it would be nice
to be able to run on lower machines."* That retires this section's `tiers[]` design
before it was built, and it retires **diagnose-first as a precondition**: the coarse
export is wanted for its own sake, not as a fix conditional on where the
milliseconds went. The decode instrumentation is not cancelled, only demoted — it is
no longer load-bearing for the decision, because 8x fewer bytes helps decode, upload
and fetch alike.

**Symptom (unchanged — this is the before-number).** `supercell_333m`: 601 frames,
540x540x54 @ 333 m, **2.59 MB/frame gzipped, 1.56 GB total, ~95 MB/frame
decompressed**. Stalls at 60x even with the decoder pool (`stalls=16` per 4 s) while
the GPU sits idle at 4.5 ms. At 60x the viewer needs 5 frames/s, i.e. **~470 MB/s of
gunzip + upload** — which is the whole story.

**What shipped instead of tiers** (commit `0de3494`): `export-web --web-voxel-m`.
No `tiers[]`, no `?tier=`, **no `web_format_version` bump and no viewer change**.
Phase 2 T7 already serves every `scenarios/<name>/web`, lists them at
`/scenarios.json`, and made the viewer grid-agnostic per load — so a coarse export
is simply another package and **the picker is the tier selector**. The other
tempting shape, a second scenario JSON with a bigger `voxel_m`, is refused for the
reason `scenario.py`'s own docstring gives: that file exists so "a scenario cannot
be simulated with one geometry and exported with another", and a duplicated `sim`
block is a second file claiming that guarantee while free to drift from it.

**Pre-registered acceptance — written and committed BEFORE the export finished**
(launched 2026-09-06 12:04 via `M:\claud_projects\temp\run_exportweb_supercell_coarse.sh`;
no CM1 re-run — the 218 GB source run is still on ext4):

1. **Grid.** The new `web_manifest.json` reads **270x270x27 @ 666 m**, `origin_m`
   x = **-89577.0** (it MUST move; -89743.5 is the 333 m grid's centres), and carries
   `source_voxel_m: 333` + `decimation_factor: 2`. Gated offline already
   (`pipeline/tests/test_web_decimation.py`, 10/10); this is the on-data confirmation.
2. **`qmax` must come back IDENTICAL to the 333 m export's** — cloud 0.009069, ice
   0.009691, rain 0.0105, graupelhail 0.01731, dbz 75.44, `w` -53.20 .. +66.33,
   `cref` 0.00 .. 75.44 (docs/phase3-t2-run-health.md §3, 2026-07-22). Those maxima
   are measured on the CM1 **source** grid, so they are independent of the export
   voxel **by construction**; a difference would mean something other than the grid
   moved. It costs nothing and it is **this run's one genuinely falsifiable gate**.
3. **Bytes are MEASURED, never predicted.** Voxel count falls exactly 8x (gated).
   Compressed bytes need not: coarsening averages, which moves the entropy of the
   byte field in a direction this plan does not get to assume in advance. The
   per-frame figure is reported after the fact.
4. **Stall probe.** Re-run the same 9 s `statprobe.mjs` at 60x against the coarse
   package. **Accept:** `stalls=0`, or a written finding that the remainder is
   fetch/disk-bound. Note the A/B against the 333 m package is **visual or on
   decoded values, never on bytes** — `qmax` is deliberately not rescaled, so the
   coarse export uses less of its byte range and the two packages' bytes do not mean
   the same thing.

**What this does NOT fix, stated in advance.** Streaming only — decode, upload,
fetch. It does **not** reduce march cost: `?step=auto` floors the step at
(box extent / 280), so a smaller texture buys **no fewer steps**. "Runs on lower
machines" is therefore **half-delivered** by this change; the render-cost half is
`?rs=auto` (already the shipped default) and C.3.

**RESULT — 2026-09-06, read against the four criteria above, in their order.**
Export `EXIT 0` in 3902 s (65 min, two 601-frame passes over the existing run).
Package copied to `M:\claud_projects\thunderstorm\scenarios\supercell_333m_coarse\web\`
(2405 files; the concatenated-file sha256 matches the ext4 original **byte for
byte**, so the 9P crossing is not a source of doubt). `/scenarios.json` lists it as
the 4th package with the right grid, and **no viewer change was needed** — the
picker is the tier selector, as designed.

1. **Grid — PASS.** 270x270x27 @ 666 m, `origin_m` = [-89577.0, -89577.0, 333.0],
   `source_voxel_m: 333.0`, `decimation_factor: 2.0`. Coarse grid spans 179.82 km,
   i.e. **the same measured box** as the native one.
2. **`qmax` — PASS, to the last digit, on all seven.** cloud 0.009068764746189117,
   ice 0.009691072627902031, rain 0.010498762130737305, graupelhail
   0.017307115718722343, dbz vmax 75.44092559814453, cref vmax 75.44092559814453,
   `w` observed -53.19807052612305 .. 66.33143615722656 — each **`==` the 333 m
   package's**, not merely close. This was the run's only falsifiable gate and it is
   the one that says the *fields* are untouched and only the *grid* moved.
   **Strengthened beyond the pre-registration:** every top-level manifest key outside
   `grid` and `frames` is identical, `extra_fields`/`volume`/`plan_fields`/`dbz`/
   `source_run` included, and both carry 601 frames at `web_format_version` 1.2.
   **13/13 on-data gates pass.**
3. **Bytes — MEASURED: 6.53x, NOT 8x.** Total 1.557 GB -> **0.239 GB**; mean/frame
   2.590 MB -> **0.397 MB**; median 1.883 -> **0.283 MB**; peak frame (f0600 in both)
   7.268 -> **1.124 MB** (6.47x). Voxel count fell exactly 8x, as gated — the shortfall
   is the pre-registered effect: coarsening averages, which raises the per-voxel
   entropy and costs gzip some of its ratio. Reported after the fact for exactly this
   reason. Decompressed: 94.5 -> **11.8 MB/frame**, i.e. the 60x demand falls
   **472 -> 59 MB/s**.
4. **Stall probe — PASS, with the finding written rather than a bare zero.** Both
   packages probed **in one invocation**, same 9 s window, 60x (the select's default),
   so the before-number is re-measured now rather than quoted from memory:

   | | native 333 m | coarse 666 m |
   |---|---|---|
   | stalls / 9 s | **682** | **7** |
   | uploads / 9 s | 22 | 56 |
   | GPU total | 3.88 ms | **2.37 ms** |
   | ...of which upload | 1.40 ms | **0.28 ms** |
   | ...of which march | 2.28 ms | **1.82 ms** |
   | rAF max | 13.9 ms | **7.1 ms** |

   **The upload counts are the real result, not the stall counts.** 9 s at 60x is 540
   storm-seconds = **45 frames** at `tapfrq=12`. The coarse package uploaded 56 (ahead,
   with prefetch); the native uploaded **22 — less than half of what it owed**, which
   is why it stalled 682 times. This is a keeping-up/not-keeping-up difference, not a
   graded one.

   **The residual 7 is a fixed transient, and that is measured, not assumed.** Doubling
   the window to 18 s returned **6** stalls, not ~14 — the count does not scale with
   time, so there is no sustained deficit to be fetch- or disk-bound about. (18 s needs
   90 frames; it uploaded **101**.) 6 events out of 2591 rendered frames is 0.23 %, and
   consistent with the measurement window opening mid-prefetch. The acceptance clause
   asked for `stalls=0` **or** a written finding; this is the finding, and it is
   stronger than the clause anticipated because it comes with a falsification test the
   clause did not require.

**One thing the plan got wrong, in the harmless direction.** "A smaller texture buys
**no fewer steps**" is still true — `?step=auto` floors the step at (box extent / 280)
and the box did not move — but march time nonetheless fell **2.28 -> 1.82 ms (-20 %)**.
The steps are the same steps; they are cheaper because an 8x smaller volume is far
kinder to the texture cache. So the render half is not *zero* help, just ~20 % rather
than the ~6.5x the streaming half got. **"Runs on lower machines" remains
half-delivered**, and C.3 remains the honest answer to the other half.

**VISUAL + DECODED A/B — added 2026-09-06 after the advisor pass, and it caught a real gap.**
The 13 gates above are **all metadata**: every one of them reads `web_manifest.json` and
**not one reads a voxel**. A transposed axis, a half-voxel origin error or a z-column
off-by-one would have passed all 13 and shipped. Worse, this section wrote the rule —
*"the A/B against the 333 m package is visual or on decoded values, never on bytes"* — and
then ran bytes and stall counters only. Owner-call 5 was about to ask *"is the 666 m image
acceptable?"* while handing over **no image**. Both gaps are closed here.

**Captures** (`tools/shot.mjs`, `acc=1&anim=0&precip=0`, in
`M:\claud_projects\temp\`): `sc_native_f150.png` / `sc_coarse_f150.png` (hero Cb),
`sc_native_f600.png` / `sc_coarse_f600.png` (late stage), and on the coarse package
`sc_coarse_dbz.png`, `sc_coarse_cref.png`, `sc_coarse_w.png` with `sc_native_dbz.png`
as the pair. **All four data layers render correctly at the new grid** — which mattered
more than it looks: `nz` is now **27**, odd and shallow, and "grid-agnostic per load" had
only ever been exercised at 208³ and 126×126×54. `cref` (a 270×270 2D plane), the separate
`dbz` R8 ring and signed `w` all came back right, and **no viewer change was needed**.
Visually the storm is in the same place at the same size with the same cloud-top
silhouette; the coarse anvil edge is softer and the native's two magenta >60 dBZ hail-core
spots collapse to one smaller spot.

**Decoded-value check** (`M:\claud_projects\temp\decode_ab.py`, frame 150, everything
decoded to physical units first — never bytes, per the rule):

- **Mass is conserved:** volume-integrated condensate `coarse/native` = **1.0020** cloud,
  **0.9954** ice, **0.9998** rain, **1.0009** graupel/hail. Under 0.5 % on all four.
- **Centroids agree to 5–15 m**, i.e. **0.01–0.02 of a coarse voxel**, in shared world
  metres across all four species. This is the gate that actually rules out a transposed
  axis, a wrong origin or a z off-by-one — and no metadata gate could have.
- **What coarsening costs, quantified:** peak values keep **98.2 %** (cloud, ice) but only
  **92.9 %** (rain) and **92.2 %** (graupel/hail); peak dBZ falls **63.52 → 62.13**, a loss
  of **1.39 dBZ**. The loss is where physics says it should be — averaging hurts the
  sharp-gradient precipitation cores, not the broad cloud field.
- **And it smears rather than only shrinking:** echo volume ≥ 60 dBZ keeps 86.5 %, but
  volume ≥ 50 dBZ comes back at **103.9 %** — averaging spreads a core outward while
  clipping its tip. Worth stating plainly because a "lower resolution just loses detail"
  intuition predicts only the first half.

**Bearing on owner-call 5.** The teaching content — storm position, size, structure,
timing, total water, the hook echo in plan view — survives intact. What degrades is the
**peak intensity of the hail core**, by ~1.4 dBZ and ~8 % of graupel/hail peak mixing
ratio. If the supercell is ever used to teach *hail severity specifically*, that is the
number to weigh; for everything else the 666 m package is a faithful rendering of the
same storm.

**Not touched.** The single-cell packages (0.14 MB/frame — coarsening costs visible
quality and gains nothing), and the 333 m supercell payload, which **stays on disk**
so the resolution drop can be judged as an A/B by one picker click. Deleting it is a
separate owner call, and cheap to defer because the source run is still there.

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

1. ~~Accept/revert the three defaults (C.1).~~ **ANSWERED 2026-09-05** — kept.
2. ~~`?rs=auto` as the shipped default (C.1).~~ **ANSWERED 2026-09-05** — yes,
   it is the default. Still the main weak-GPU lever, since C.2 does not touch
   render cost.
3. ~~Coarser supercell web tier — a pipeline task with its own go (C.2).~~
   **ANSWERED 2026-09-06: go, and lower resolution accepted outright** — which
   turned the "tier" into a plain second package and retired the `tiers[]`
   design unbuilt (C.2).
4. Half-res volume pass default anywhere (C.3) — only after a zoomed-anvil crop.
5. ~~**NEW 2026-09-06, opened by C.2 shipping.** (a) is the 666 m image acceptable
   as the *only* supercell? (b) should the picker default to the coarse one?~~
   **ANSWERED 2026-09-06 (owner): KEEP BOTH — "the coarse is good, but the original
   is better". The picker defaults to the coarse one, and choosing the original must
   be "evident and easy".** So the answer to (a) is *no, do not make it the only
   one*: the 1.56 GB 333 m payload stays, as the quality reference, **and is not to
   be deleted**. (b) is yes.

   **Shipped 2026-09-06** (commit below). Three changes, deliberately small:
   - `DEFAULT_SCENARIO` = `supercell_333m_coarse` in `diorama/src/scenario.ts`. This
     changes which STORM the app opens on as well as which detail level — before
     today it opened on `single_cell_500m`. That is the plain reading of the ruling
     and it was taken on purpose: a default that only applied "within the supercell
     pair" would have left startup behaviour byte-identical to before, which is not
     what "the picker should default on the coarser" asks for. **A bookmark is not
     broken by this**: `resolveScenario` honours a served `?scenario=` over the
     default, and there is a gate asserting exactly that.
   - **The label now says which is which in words**, because
     `supercell_333m_coarse · 270×270×27 @ 666 m` is evident only to someone who
     already knows. The dropdown reads `… · lighter (2× coarser)` and
     `… · full detail`. The tag is **derived, never a hardcoded name list**: two
     packages are the same storm at two detail levels iff they share `source_run`
     (which a coarsened export copies verbatim from its parent), and
     `decimation_factor` says which of the pair is the light one. Consequences worth
     stating: a future coarse export named anything at all still pairs correctly,
     two unrelated packages sharing a name prefix do not, and the tag **only prints
     when a sibling is actually served** — "full detail" is a boast with nothing to
     contrast against on a package that has no lighter twin, so the single-cell
     packages stay untagged.
   - The `<select>` was an unlabelled 12 px dropdown with a `title` tooltip. It now
     carries a visible **`Storm`** label (hidden along with the picker itself when
     only one package is served, so the word never sits beside a hidden control).

   `vite.config.ts` had to start emitting `source_run` / `source_voxel_m` /
   `decimation_factor` in `/scenarios.json`. That discovery list is **one shape
   living in two files with nothing enforcing agreement**, so the server now
   *imports* `ScenarioSummary` from `src/scenario.ts` and types its return with it:
   adding a picker field breaks `tsc --noEmit` until the server emits it, instead of
   silently shipping `undefined`.

   **Verification — and this is the part the unit tests could not do.** 157/157
   vitest (18 in `scenario.test.ts`, up from 11) pass, but every one of them is a
   pure-helper test: they would all stay green if the dropdown rendered nothing, if
   the page opened on the wrong package, or if the reload dropped the view params.
   Same shape as the "13 gates, none read a voxel" catch above. So
   `diorama/tools/picker-check.mjs` (new) drives a real Chrome over CDP against the
   real dev server: **12/12**, covering what opens with no `?scenario=` at all, the
   exact option strings, the visible label, a dropdown switch to the original with
   `az`/`el`/`layer` surviving the reload, and an old `?scenario=` bookmark still
   winning. Two of its gates initially passed **vacuously** — `!/buffering/` is true
   of an empty HUD — and were tightened to require the storm clock to read a real
   time before "it rendered" is claimed.

   **AMENDED SAME DAY 2026-09-06 — the default is the FULL-DETAIL package after all.**
   Owner: *"leave the lower machine half then, park what is done, but make the finer
   detailed default."* `DEFAULT_SCENARIO` is now `supercell_333m`. This is **not** a
   reversal of the keep-both ruling and not a verdict on the coarse export, which stays
   served, stays labelled, and is one click away — the same click the full one needed for
   the few hours in between. It follows from **C.3 (the half-resolution DRAWING pass)
   being parked**: the coarse export halves streaming cost but not render cost, so on its
   own it does not deliver "runs on lower machines", and with that goal shelved there is
   nothing left for a default to trade image quality against. The argument is written into
   the `DEFAULT_SCENARIO` comment in `diorama/src/scenario.ts`, so that if C.3 is ever
   picked up the flip back does not have to be re-derived.

   **The amendment broke the live check, which is the point of having one.**
   `picker-check.mjs` hard-codes the expected package by name (deliberately — importing
   `DEFAULT_SCENARIO` would make the gate agree with any value the constant is ever
   changed to, which is exactly the failure it exists to catch), so flipping the default
   without touching it would have shipped an 11/12 tool on `main`. `tsc` and 157/157
   vitest both stayed green through that. Gate updated, and section 2 now switches to the
   *coarse* member — the invariant is "the pair is one click apart", whichever is default.
   **Re-run: 12/12.**

   **And it caught a THIRD vacuous gate in itself, same shape as the first two.** The
   renderer prints `buffering…` into the **clock** element, not the HUD, so
   `!/buffering/.test(hud)` was true of a page that had rendered nothing — and the
   readiness wait returned as soon as the *picker* populated, which happens long before
   the first brick is fetched. Both render gates were reading `frame 0/600 · buffering…`
   and passing. Fixed at both ends (wait on the clock, assert on the clock). Lesson, third
   instance: **a gate satisfied by an absence must be shown to fail on the absent case**,
   or it is measuring nothing.
