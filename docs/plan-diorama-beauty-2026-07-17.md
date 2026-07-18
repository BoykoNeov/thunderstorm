# Plan: Diorama beauty upgrades — 6 items + prerequisite (2026-07-17)

Implementation plan for the six visual-beauty items agreed on 2026-07-17, written
so a less capable model can execute them mechanically. Step 0 (the sun-transmittance
light cache) is a *prerequisite*: steps 1 and 3 consume it, and it is also the
single biggest frame-rate win (it collapses the 28-step secondary sun march —
the dominant cost of the whole renderer — into one texture fetch).

All work is in `diorama/` (TS + WebGL2, no engine). No pipeline or UE changes.

## Ground rules (read before every step)

1. **Presentation, never physics.** Every effect here modulates how the data
   LOOKS. Nothing writes back into the volume, nothing scripts storm behavior.
   Lightning is explicitly OUT of scope (it is a diagnostic layer; slice 6
   waits for the Phase 4 event-list exporter).
2. **Every new knob is a URL param** parsed with the existing `numParam`
   helper in `main.ts` (it exists because `Number(x) || default` eats a
   legitimate `0`). Every effect must be disableable from the URL for A/B.
3. **After each step:** `npm run typecheck && npm test` must pass (run in
   `diorama/`), capture an A/B screenshot pair (see "Verification recipe"),
   save captures under `M:\claud_projects\temp\diorama-beauty\stepN\`, then
   commit. One commit per step. Do NOT batch steps into one commit.
4. **Do not refactor beyond what a step specifies.** The shaders are template
   strings in `src/shaders.ts`; GLSL errors surface only at startup (red error
   box / console), so keep diffs small and test in the browser after each step.
5. **Execute steps in order 0 → 6.** Step 1 introduces `Tsun` in the march
   loop which step 3 reuses; step 4 restructures the render-target chain which
   step 5 extends.
6. Defaults with a taste component (tonemap choice, split-tone strength) are
   implemented behind params and **presented to the owner as A/B captures** —
   the implementing model does not pick the winner by itself.

### Current architecture (orientation)

- `src/shaders.ts` — all GLSL. `VOL_COMMON` is a shared chunk interpolated into
  both the composite fragment shader (`FRAG`) and the precip vertex shader
  (`PRECIP_VERT`). `FRAG` = fullscreen raymarch + surface shading + background
  + tonemap. `POST_FRAG` = tilt-shift (run twice: H, then V + grade).
- `src/main.ts` — frame loop. Passes per frame: (1) staging mesh → G-buffer;
  (2) composite → `sceneT` (or screen if `?ts=0`); (2.5) precip particles into
  the same target; (3) tilt-shift H → `blurT`, V + grade → screen.
- Texture units in use: 0 = volume frame A, 1 = volume frame B, 2 = g-albedo,
  3 = g-normal, 4 = g-depth, 5 = 3D noise. **Units 6 and 7 are free** (step 0
  claims them).
- Volume bricks are RGBA8 3D textures (208×208×72 for the current package) in
  a 24-slot LRU ring (`SlotPool`); at most one `texSubImage3D` upload per rAF.
- The sun direction `SUN` is a compile-time constant of the scene
  (`main.ts`: `const SUN = direction(100°, 40°)`). It never changes at
  runtime. This is what makes step 0 legal.

### Corrections found while executing (2026-07-18, step 2)

Three errors in this plan surfaced during step 2 — later steps reuse the same
recipe/view, so heed these:

1. **The headless capture recipe below never waits for volume streaming.**
   `--virtual-time-budget` fires the screenshot before the async brick
   fetch/decode/upload settles, so it always caught the "buffering…" screen.
   Use `diorama/tools/shot.mjs` instead: it drives real headless Chrome over
   CDP and polls the HUD until the clock reads a frame and is not buffering.
   `node tools/shot.mjs <chrome.exe> <out.png> <url>` (Chrome must already be
   running with `--remote-debugging-port=9222`).
2. **The "sun-side" view is `az≈280`, not `az=100`.** In this camera
   convention `az=100` places the camera on the *same* bearing as the sun,
   looking *away* from it → `cosSun<0`, effect dead. The backlit view that
   makes silver/rays visible is `az=280&el≈8-12` (looking toward the sun).
3. **Step 2's `ph0 += spike` is ~6× self-suppressed** (× msNorm ≈0.54 × powder
   ≈0.3 on thin edges) and contradicts its own "kept OUT of msNorm" comment.
   Implemented instead as a pure additive rim on `Sc`, after both terms:
   `Sc += CLOUD_ALB*SUN_COL*(hg(cosSun,0.92)*4π*uSilver*Tsun)`. Step 3 (rays)
   should likewise verify its term isn't gutted by powder before judging it.

### Verification recipe (used by every step)

1. Dev server: `node tools/find-server.mjs` prints the URL of a live server if
   one exists (reuse it — do NOT start a second one); otherwise run
   `npm run dev` in `diorama/` and use the URL vite prints.
2. Static captures with headless Chrome (real GPU — screenshots are trustworthy,
   unlike UE `-nullrhi`):

   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" `
     --headless=new --screenshot=M:\claud_projects\temp\diorama-beauty\stepN\a.png `
     --window-size=1600,900 --virtual-time-budget=20000 `
     "http://localhost:PORT/?frame=150&PARAMS"
   ```

   `?frame=150` starts paused on the hero frame (150 is the classic-Cb frame;
   255 is late-stage diffuse — do not judge beauty on 255). If a capture comes
   out black or shows "buffering…", raise `--virtual-time-budget`.
3. A/B = same URL with the step's param on vs off (e.g. `lc=1` vs `lc=0`).
   Also capture one late frame (`frame=255`) and one alternate view
   (`az=100&el=25` — sun-side) when a step says so.
4. Pacing: append `&stats` and read `window.__stats` (deltas = raw rAF ms,
   uploadMs, stalls) from the console, or via the same headless driver used in
   the beauty-gate sessions. On the RTX 5090 everything is vsync-capped;
   to make a perf effect measurable, raise `?rs=` (render-scale supersample,
   e.g. `rs=2` or `rs=3`) until `lc=0` deltas exceed ~16.7 ms, then compare
   `lc=1` at the same `rs`.

---

## Step 0 — Sun-transmittance light cache (prerequisite; perf)

**Goal.** Bake, per resident volume frame, a small R8 3D texture holding
`exp(-sunTau(p))` (sun transmittance) at every point of the box. Replace all
per-sample/per-pixel secondary sun marches with one fetch from this cache.
Since the sun never moves, the bake is valid for the lifetime of the frame in
its ring slot, and it costs one 104×104×36-frag pass at upload time (uploads
are already capped at 1/rAF).

**Files:** `src/gl.ts`, `src/shaders.ts`, `src/main.ts`.

### 0.1 gl.ts — cache texture + parametrized color target

Add (next to `createVolumeTexture`):

```ts
/** R8 3D sun-transmittance cache (linear, clamp). One per ring slot. */
export function createShadowCacheTexture(
  gl: WebGL2RenderingContext,
  sx: number,
  sy: number,
  sz: number,
): WebGLTexture {
  const tex = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.texStorage3D(gl.TEXTURE_3D, 1, gl.R8, sx, sy, sz);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE);
  return tex;
}
```

(R8 is color-renderable in core WebGL2 — no extension needed.)

### 0.2 shaders.ts — bake shader + `sunTrans()` in VOL_COMMON

**(a)** Append to the END of the `VOL_COMMON` string (after `tauDir`):

```glsl
uniform sampler3D uShadowA;   // baked sun transmittance, frame i0 (unit 6)
uniform sampler3D uShadowB;   // frame i1 (unit 7)
uniform float uUseCache;      // ?lc=0 falls back to the live march

// Sun transmittance at p — one fetch from the baked cache, nearest frame
// (exactly the sigmaShadowAt policy: crossfading shadows is imperceptible).
// Points OUTSIDE the box advance to the sun ray's box entry: the cache voxel
// there already integrates the remaining path to the sun. Rays that miss the
// box are unshadowed.
float sunTrans(vec3 p) {
  if (uUseCache < 0.5) return exp(-sunTau(p));
  vec2 tb = rayBox(p, uSunDir, uBoxMin, uBoxMax);
  if (tb.y <= max(tb.x, 0.0)) return 1.0;
  vec3 q = p + uSunDir * max(tb.x, 0.0);
  vec3 uvw = clamp((q - uBoxMin) / (uBoxMax - uBoxMin), 0.0, 1.0);
  return uMix < 0.5 ? texture(uShadowA, uvw).r : texture(uShadowB, uvw).r;
}
```

**(b)** New exported bake shader (it reuses VOL_COMMON; `uMix` defaults to 0 so
`sunTau`'s `sigmaShadowAt` reads only `uVolA` — the brick being baked):

```ts
// -- pass 0 (upload-time): sun-transmittance bake ------------------------------
// One fullscreen draw per z-slice of the cache; framebufferTextureLayer selects
// the slice. Runs once per brick upload — never per rendered frame.
export const BAKE_FRAG = `#version 300 es
precision highp float;
precision highp sampler3D;
out vec4 fragColor;
uniform vec2  uCacheXY;  // cache slice resolution, texels
uniform float uSliceZ;   // normalized z of this slice's texel centers
${VOL_COMMON}
void main() {
  vec3 uvw = vec3(gl_FragCoord.xy / uCacheXY, uSliceZ);
  vec3 p = mix(uBoxMin, uBoxMax, uvw);
  fragColor = vec4(exp(-sunTau(p)), 0.0, 0.0, 1.0);
}
`;
```

**(c)** Replace the two `exp(-sunTau(p))` call sites in `FRAG`:

- in `shadeSurface`: `float shadow = exp(-sunTau(p));` → `float shadow = sunTrans(p);`
- in the march loop: `float shadow = exp(-sunTau(p));` → `float shadow = sunTrans(p);`
  (step 1 renames this to `Tsun`).

**(d)** In `PRECIP_VERT`, replace the sun-direction coarse march:

```glsl
float light = mix(0.35, 1.0, exp(-tauDir(pLow, uSunDir, uShadowKm, 10)));
```
→
```glsl
float light = mix(0.35, 1.0, sunTrans(pLow));
```
(The view-direction `tauDir` stays — direction varies per instance, can't cache.)

### 0.3 main.ts — allocate, bake on upload, bind at draw

**(a)** Params & sizes (near the other param parsing):

```ts
const lightCache = params.get("lc") !== "0"; // ?lc=0: live-march fallback (A/B)
```

After the manifest loads (where `nx, ny, nz` exist):

```ts
const CACHE_DIV = 2;
const cacheX = Math.ceil(nx / CACHE_DIV);
const cacheY = Math.ceil(ny / CACHE_DIV);
const cacheZ = Math.ceil(nz / CACHE_DIV);
```

**(b)** Allocate one cache per ring slot (next to the `textures` loop) + a bake
FBO + program:

```ts
const progBake = compileProgram(gl, VERT, BAKE_FRAG);
const shadowTex: WebGLTexture[] = [];
for (let i = 0; i < RING_CAPACITY; i++) shadowTex.push(createShadowCacheTexture(gl, cacheX, cacheY, cacheZ));
const bakeFBO = gl.createFramebuffer()!;
```

(24 × 104×104×36 × 1 B ≈ 9.3 MB total — negligible next to the 300 MB ring.)

**(c)** Static bake uniforms (put with the other static-uniform blocks; note the
bake must see exactly what the shadow march sees today — `wShadow` weights, the
scaled extinction, the same `uShadowKm` cap):

```ts
gl.useProgram(progBake);
gl.uniform3f(loc(progBake, "uSunDir"), SUN.x, SUN.y, SUN.z);
gl.uniform3f(loc(progBake, "uBoxMin"), box.min.x, box.min.y, box.min.z);
gl.uniform3f(loc(progBake, "uBoxMax"), box.max.x, box.max.y, box.max.z);
gl.uniform1i(loc(progBake, "uVolA"), 0);
gl.uniform1i(loc(progBake, "uVolB"), 0); // unused (uMix=0), pointed somewhere valid
gl.uniform4fv(loc(progBake, "uThr"), thr);
gl.uniform4fv(loc(progBake, "uK"), k);
gl.uniform4f(loc(progBake, "uWeights"), wShadow[0], wShadow[1], wShadow[2], wShadow[3]);
gl.uniform1f(loc(progBake, "uExtScale"), EXT_SCALE / stormScale);
gl.uniform1f(loc(progBake, "uShadowKm"), 15 * stormScale);
gl.uniform2f(loc(progBake, "uCacheXY"), cacheX, cacheY);
```

**(d)** Bake helper (place above the frame loop):

```ts
function bakeShadow(slot: number) {
  gl.bindFramebuffer(gl.FRAMEBUFFER, bakeFBO);
  gl.viewport(0, 0, cacheX, cacheY);
  gl.useProgram(progBake);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_3D, textures[slot]);
  for (let z = 0; z < cacheZ; z++) {
    gl.framebufferTextureLayer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, shadowTex[slot], 0, z);
    gl.uniform1f(loc(progBake, "uSliceZ"), (z + 0.5) / cacheZ);
    drawFullscreen(gl);
  }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
}
```

**(e)** Call it in the upload block (frame-loop step 3), immediately after
`uploadVolume(...)` and inside the same timing bracket so `?stats` sees the
cost:

```ts
uploadVolume(gl, textures[slot], nx, ny, nz, data);
if (lightCache) bakeShadow(slot);
```

Add `bakeMs: [] as number[]` to `stats` and push
`performance.now() - u0` split if you want the bake separated from the upload —
optional; a combined `uploadMs` is acceptable.

**(f)** Static uniforms for the two consumer programs — in the `progVol` block:

```ts
gl.uniform1i(loc(progVol, "uShadowA"), 6);
gl.uniform1i(loc(progVol, "uShadowB"), 7);
gl.uniform1f(loc(progVol, "uUseCache"), lightCache ? 1 : 0);
```

and the same three lines in the `progPrecip` block. **Do not skip the precip
ones** — an unset sampler uniform defaults to unit 0 and would read the volume
brick as a shadow cache.

**(g)** Per-frame binds — in the draw section, after the unit-4 depth bind:

```ts
gl.activeTexture(gl.TEXTURE6);
gl.bindTexture(gl.TEXTURE_3D, shadowTex[pool.slotOf(bind.fa)!]);
gl.activeTexture(gl.TEXTURE7);
gl.bindTexture(gl.TEXTURE_3D, shadowTex[pool.slotOf(bind.fb)!]);
```

(The slot's cache is baked in the same rAF the slot is filled, before the frame
can be bound — the ordering upload→bake→bind guarantees no stale cache. Eviction
reuses the slot only via `pool.assign`, which is immediately followed by
upload+bake.)

### Verify (step 0)

- `npm run typecheck && npm test` (no pure-TS logic changed — must stay green).
- A/B captures `?frame=150&lc=1` vs `?frame=150&lc=0`: visually
  near-identical. Expected difference: cache shadows are slightly SOFTER
  (half-res trilinear). Repeat at `frame=255`. If shadows are grossly wrong
  (storm shadow missing from the landscape, or volume fully unshadowed),
  suspect (f) or (g).
- Perf: at `?rs=3&stats`, playback mean rAF delta with `lc=1` should be
  markedly lower than `lc=0` (the 28-step inner march is gone from both the
  volume march and every landscape pixel).
- Pitfalls: R8 quantizes transmittance to 1/255 — banding is hidden by the
  existing output dither; do not "fix" by storing tau. If the framebuffer is
  reported incomplete on the first `framebufferTextureLayer`, check the texture
  was made with `texStorage3D` (immutable) and level 0 is used.

**Commit:** `Diorama: baked sun-transmittance light cache (28-step sun march → 1 fetch)`

---

## Step 1 — Multiple-scattering octaves (beauty 1)

**Goal.** Real cumulus is bright and creamy because light scatters many times;
single scattering + powder reads dark and flat in the cores. Standard real-time
approximation (Wrenninge; used by Nubis/Frostbite-class sky renderers): sum 2–3
"octaves" of the sun term, each with attenuated optical depth and a flatter
phase. Because step 0 caches transmittance `T = exp(-tau)`, attenuated depth is
just `pow(T, a^i)` — almost free.

**Files:** `src/shaders.ts` (FRAG only), `src/main.ts` (two uniforms + params).

### 1.1 FRAG — before the march loop

Replace:

```glsl
float cosSun = dot(rd, uSunDir);
// moderately-peaked dual lobe: side-lit cloud still receives real phase
// weight (a hard 0.65 forward lobe starves every sun-at-the-side view)
float phase = mix(hg(cosSun, -0.2), hg(cosSun, 0.45), 0.65) * 4.0 * PI;
```

with:

```glsl
float cosSun = dot(rd, uSunDir);
// multi-scatter octaves (Wrenninge-style): octave i sees optical depth
// scaled by uMsA^i (pow of the cached transmittance) and phase eccentricity
// scaled by MS_B^i (higher orders are more isotropic). The dual lobe is the
// slice-3 one: a hard forward lobe starves every sun-at-the-side view.
const float MS_B = 0.6;
float ph0 = mix(hg(cosSun, -0.2), hg(cosSun, 0.45), 0.65) * 4.0 * PI;
float ph1 = mix(hg(cosSun, -0.2 * MS_B), hg(cosSun, 0.45 * MS_B), 0.65) * 4.0 * PI;
float ph2 = mix(hg(cosSun, -0.2 * MS_B * MS_B), hg(cosSun, 0.45 * MS_B * MS_B), 0.65) * 4.0 * PI;
// renormalize so uMsW does not change overall brightness, only shadow lift
float msNorm = 1.0 / (1.0 + uMsW + uMsW * uMsW);
```

### 1.2 FRAG — inside the march loop

Replace the lighting block:

```glsl
float shadow = exp(-sunTau(p));            // (already sunTrans(p) after step 0)
float hfrac = clamp((p.z - uBoxMin.z) / (uBoxMax.z - uBoxMin.z), 0.0, 1.0);
vec3 amb = mix(AMB_LOW, AMB_HIGH, hfrac) * (0.25 + 0.45 * hfrac);
float powder = 1.0 - 0.7 * exp(-s2.x * 1.2);
vec3 Sc = CLOUD_ALB * (SUN_COL * (shadow * phase * powder) + amb);
vec3 Sr = RAIN_ALB * (SUN_COL * (shadow * phase * 0.55) + amb);
```

with:

```glsl
float Tsun = sunTrans(p);
float hfrac = clamp((p.z - uBoxMin.z) / (uBoxMax.z - uBoxMin.z), 0.0, 1.0);
vec3 amb = mix(AMB_LOW, AMB_HIGH, hfrac) * (0.25 + 0.45 * hfrac);
float powder = 1.0 - 0.7 * exp(-s2.x * 1.2);
float ms = (ph0 * Tsun
          + uMsW * ph1 * pow(Tsun, uMsA)
          + uMsW * uMsW * ph2 * pow(Tsun, uMsA * uMsA)) * msNorm;
vec3 Sc = CLOUD_ALB * (SUN_COL * (ms * powder) + amb);
vec3 Sr = RAIN_ALB * (SUN_COL * (ms * 0.55) + amb);
```

### 1.3 main.ts — uniforms + params

```ts
const msW = Math.max(0, numParam("msw", 0.55)); // octave weight (?msw=0 → single scatter)
const msA = Math.min(1, Math.max(0.05, numParam("msa", 0.35))); // depth attenuation per octave
```

In the `progVol` static block:

```ts
gl.uniform1f(loc(progVol, "uMsW"), msW);
gl.uniform1f(loc(progVol, "uMsA"), msA);
```

(FRAG-only uniforms: declare `uniform float uMsW; uniform float uMsA;` in FRAG
near `uErosion`, NOT in VOL_COMMON — the precip shader doesn't use them.)

### Verify (step 1)

- Captures `?frame=150&msw=0` vs `?frame=150` (default 0.55): with octaves on,
  the shadowed flank and under-anvil cores lift from near-black to a luminous
  grey; the sunlit side barely changes (msNorm keeps overall level). No white
  clipping on the sunlit cauliflower.
- Sanity: `pow(T, 0.35)` at a deep-core `T ≈ e⁻⁹` is `e⁻³·¹⁵ ≈ 0.043` — the
  expected visible lift. If cores stay pitch black, `Tsun` is likely 0 exactly
  (R8 floor) — acceptable, or slightly raise `msa`.
- Owner eyeballs the pair before tuning further; `msw`/`msa` are the two knobs.

**Commit:** `Diorama: multi-scatter octaves — shadowed cloud cores read luminous, not black`

---

## Step 2 — Silver lining (beauty 2)

**Goal.** Thin cloud edges between the camera and the sun should bloom into a
bright rim ("silver lining"). This falls out of a narrow forward phase lobe:
high transmittance (thin edge) × strongly forward phase = bright rim; opaque
cores are shadowed, so they cannot blow out.

**Files:** `src/shaders.ts` (FRAG), `src/main.ts` (one uniform + param).

### 2.1 FRAG

Right after the `ph0/ph1/ph2` block from step 1, add:

```glsl
// silver lining: a narrow forward spike on octave 0 only — kept OUT of the
// msNorm renormalization on purpose (it is a rim accent, not energy balance)
ph0 += hg(cosSun, 0.92) * 4.0 * PI * uSilver;
```

Declare `uniform float uSilver;` next to `uMsW`.

### 2.2 main.ts

```ts
const silver = Math.max(0, numParam("silver", 0.15)); // ?silver=0 disables
gl.uniform1f(loc(progVol, "uSilver"), silver);
```

### Verify (step 2)

- The default view looks away from the sun (camera az 45°, sun az 100°), so
  capture the sun-side view: `?frame=150&az=100&el=25&silver=0` vs
  `...&silver=0.15` — cloud edges near the sun direction gain a bright, tight
  rim. The default view should be nearly unchanged.
- `hg(1, 0.92)·4π ≈ 300` — the spike is huge but only within a few degrees of
  the sun and multiplied by `Tsun·SUN_COL`; the tonemap shoulder absorbs it.
  If the rim reads as a hard white blowout, halve `silver`; do not clamp in
  the shader.

**Commit:** `Diorama: silver-lining forward lobe on thin sun-facing edges`

---

## Step 3 — God rays / sunlit haze (beauty 3)

**Goal.** Add a faint constant "clear air" haze inside the volume box, lit by
the cached sun transmittance. Where the anvil shadows the air, the haze goes
dark → true 3D crepuscular rays / under-storm gloom, correctly occluded by the
landscape (the march is already clipped at `tSurf`). Cost: the lighting branch
now runs at every march step (one extra cache fetch) — affordable after step 0.

**Files:** `src/shaders.ts` (FRAG), `src/main.ts` (one uniform + param).

### 3.1 FRAG — before the loop

After the phase block:

```glsl
// haze phase: strongly forward — that's what makes shafts directional
float phHaze = hg(cosSun, 0.6) * 4.0 * PI;
```

### 3.2 FRAG — in the loop

Replace:

```glsl
vec2 s2 = sigma2At(p);
float sig = s2.x + s2.y;
if (sig > 1e-4) {
```

with:

```glsl
vec2 s2 = sigma2At(p);
float sig = s2.x + s2.y + uRays;   // uRays: constant sunlit-haze extinction
if (sig > 1e-4) {
```

and the source blend:

```glsl
vec3 S = (Sc * s2.x + Sr * s2.y) / sig;
```

with:

```glsl
vec3 Sh = SUN_COL * (phHaze * Tsun) + AMB_HIGH * 0.3;
vec3 S = (Sc * s2.x + Sr * s2.y + Sh * uRays) / sig;
```

Declare `uniform float uRays;` next to `uMsW`.

Note: `Tsun` (step 1) must be computed before `S` — it already is, since the
lighting block sits inside the same `if`. With `?rays=0` the gate returns to
skipping empty air exactly as before (uniform is 0, `sig` unchanged).

### 3.3 main.ts

```ts
const rays = Math.max(0, numParam("rays", 0.0035)); // km^-1; ?rays=0 disables
gl.uniform1f(loc(progVol, "uRays"), rays);
```

### Verify (step 3)

- Captures `?frame=150&rays=0` vs default: with rays on, expect (a) visible
  bright shafts where sunlight passes beside/under the anvil into shadowed
  air, (b) a soft gloom under the storm, (c) slight aerial dimming of
  background seen THROUGH the box (τ ≈ 0.2 over 60 km — subtle, intended).
- Also check playback (a few seconds live) — shafts must be stable, no
  flicker beyond the march jitter grain.
- Known limitation (by design): haze exists only inside the volume box, so
  shafts never extend past the box walls. Do not try to extend them — the sea
  fog already handles the far field.
- Perf: this makes formerly-empty pixels pay the lighting branch each step.
  If `?rs=2` playback drops below vsync with rays on but holds with rays=0,
  note it in the commit message — the owner decides the default later.

**Commit:** `Diorama: sunlit haze in the volume — crepuscular shafts + under-storm gloom`

---

## Step 4 — Temporal accumulation when idle (beauty 4)

**Goal.** The march uses per-pixel jitter (`hash12`) → visible grain. When the
view AND the displayed storm frame are static (paused, or holding on a
buffering stall), re-render with a per-frame jitter offset and average into an
accumulation buffer: the image converges to a noise-free "beauty still" in
under a second. Any interaction resets instantly, so motion looks exactly as
today. Bonus: once converged, the volume passes stop re-rendering — idle power
drops.

**Design decision (flag to owner in the commit message):** while accumulating,
the animation clock freezes — water ripples, veil scroll, and precip fall stop
when paused. Pausing now freezes the whole miniature (which also reads
naturally for a diorama). `?acc=0` restores today's behavior.

**Files:** new `src/accum.ts`, new `test/accum.test.ts`, `src/gl.ts`,
`src/shaders.ts` (FRAG: one uniform), `src/main.ts`.

### 4.1 accum.ts (pure, unit-tested)

```ts
// Idle-accumulation bookkeeping — pure (no WebGL), unit-tested.
//
// A "view key" captures everything that must be IDENTICAL between two rAFs
// for their renders to be averageable: camera orbit, the bound frame pair and
// crossfade mix, and the frozen animation clock. Any change resets the count.

export interface ViewKey {
  az: number;
  el: number;
  dist: number;
  fovY: number;
  targetZ: number;
  fa: number;
  fb: number;
  mix: number;
}

export const ACC_CAP = 64; // converged after this many averaged frames

export function sameView(a: ViewKey | null, b: ViewKey): boolean {
  if (a === null) return false;
  return (
    a.az === b.az && a.el === b.el && a.dist === b.dist && a.fovY === b.fovY &&
    a.targetZ === b.targetZ && a.fa === b.fa && a.fb === b.fb && a.mix === b.mix
  );
}

/** Frames accumulated so far: 1 restarts, else count up to the cap. */
export function nextCount(same: boolean, prev: number, cap = ACC_CAP): number {
  return same ? Math.min(prev + 1, cap) : 1;
}

/** Low-discrepancy jitter offset for accumulation pass n (golden ratio). */
export function jitterSeq(n: number): number {
  return (n * 0.61803398875) % 1;
}
```

`test/accum.test.ts`: assert `nextCount(false, 40) === 1`,
`nextCount(true, 1) === 2`, `nextCount(true, 64) === 64`; `jitterSeq(0) === 0`,
`jitterSeq(1) ≈ 0.618`, all outputs in `[0,1)` for n up to 200; `sameView`
null → false, equal → true, one field changed → false.

### 4.2 gl.ts — float color target

Change `createColorTarget` to accept a format (default keeps current behavior):

```ts
export function createColorTarget(
  gl: WebGL2RenderingContext,
  w: number,
  h: number,
  fmt: number = gl.RGBA8,
): ColorTarget {
  const tex = tex2D(gl, w, h, fmt, gl.LINEAR);
  ...
```

### 4.3 shaders.ts — jitter uniform

In FRAG, declare `uniform float uJitter;` (near `uErosion`) and change the ray
start:

```glsl
float t = t0 + dt * hash12(gl_FragCoord.xy);
```
→
```glsl
float t = t0 + dt * fract(hash12(gl_FragCoord.xy) + uJitter);
```

(`uJitter = 0` reproduces today's image bit-for-bit.)

### 4.4 main.ts — restructure targets + accumulate

**(a)** Params & capability:

```ts
const accumOn = params.get("acc") !== "0";
const floatOK = !!gl.getExtension("EXT_color_buffer_float"); // enables RGBA16F render
const accEnabled = accumOn && floatOK;
```

**(b)** Targets. `sceneT` is now ALWAYS allocated (composite never draws
straight to screen when either tilt-shift, accumulation, or — step 5 — FXAA is
on; keep the direct-to-screen path only for the all-off combo). Add `accT`:

```ts
let accT: ColorTarget | null = null;
// in resize(), alongside sceneT/blurT (create sceneT/blurT unconditionally now):
if (accEnabled) {
  accT?.dispose();
  accT = createColorTarget(gl, canvas.width, canvas.height, gl.RGBA16F);
  accN = 0; // resize invalidates history
}
```

(RGBA16F is filterable in core WebGL2; renderable once EXT_color_buffer_float
is enabled. If the extension is missing, `accEnabled` is false and NOTHING else
changes — verify this fallback compiles and runs.)

**(c)** State (above the frame loop):

```ts
let accN = 0;
let prevKey: ViewKey | null = null;
let tFrozen = 0; // frozen animation clock, seconds
```

**(d)** In the frame loop, right after `bind` is resolved (before the passes):

```ts
const key: ViewKey = {
  az: orbit.azimuth, el: orbit.elevation, dist: orbit.distance,
  fovY: orbit.fovY, targetZ: orbit.target.z,
  fa: bind?.fa ?? -1, fb: bind?.fb ?? -1, mix: bind?.mix ?? -1,
};
const same = accEnabled && !dragging && !scrubbing && sameView(prevKey, key);
prevKey = key;
accN = nextCount(same, accN);
if (!same) tFrozen = now / 1000;
const tAnim = same ? tFrozen : now / 1000;
const converged = same && accN >= ACC_CAP;
```

Then use `tAnim` for BOTH `uTime` (progVol) and `uTimeWall` (progPrecip)
instead of `now / 1000`, and set the jitter each frame:

```ts
gl.uniform1f(loc(progVol, "uJitter"), same ? jitterSeq(accN) : 0);
```

**(e)** Pass routing. Wrap passes 1, 2, 2.5 in `if (!converged) { ... }` (the
G-buffer + composite + precip). Composite target: `sceneT.fbo` always (see (b)).
After pass 2.5, accumulate:

```ts
if (accEnabled && sceneT && accT && !converged) {
  gl.bindFramebuffer(gl.FRAMEBUFFER, accT.fbo);
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.useProgram(progPost); // radius 0 + grade 0 ⇒ plain copy (cocAt < 0.5 path)
  gl.uniform2f(loc(progPost, "uRes"), canvas.width, canvas.height);
  gl.uniform1f(loc(progPost, "uMaxRadius"), 0);
  gl.uniform1f(loc(progPost, "uGrade"), 0);
  gl.uniform2f(loc(progPost, "uDir"), 0, 0);
  if (accN > 1) {
    gl.enable(gl.BLEND);
    gl.blendColor(0, 0, 0, 1 / accN);
    gl.blendFunc(gl.CONSTANT_ALPHA, gl.ONE_MINUS_CONSTANT_ALPHA); // running average
  }
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, sceneT.tex);
  drawFullscreen(gl);
  gl.disable(gl.BLEND);
}
const postSrc = accEnabled && accT ? accT.tex : sceneT!.tex;
```

The tilt-shift H pass then reads `postSrc` instead of `sceneT.tex` (its other
uniforms are per-frame already — but note the accumulate blit above changed
`uMaxRadius`/`uGrade`/`uDir`, and the tilt-shift block re-sets all of them, so
order is safe as long as the tilt-shift block keeps setting every uniform it
uses — verify it does; it currently does).

When tilt-shift is off (`?ts=0`), present `postSrc` to screen through the same
progPost-as-blit trick (radius 0, grade 0, framebuffer null). Only when
`?ts=0&acc=0` (and, after step 5, `fxaa=0`) may composite draw directly to
screen as today.

### Verify (step 4)

- `npm test` — new accum tests green.
- Live check (real browser, not headless): load `?frame=150`, do not touch
  anything for ~2 s → grain visibly dissolves to a clean still. Drag the
  orbit → grain returns instantly, NO ghosting/smearing while dragging.
  Press play → playback looks exactly as before (mix changes every rAF ⇒
  `same` is false ⇒ pure passthrough).
- Headless A/B: two captures of the same URL, `--virtual-time-budget` 20000 vs
  40000 — the longer one must be smoother (more accumulation), and both must
  show identical framing (no drift).
- Pitfall: if the converged image slowly darkens or brightens, the blend
  founders on `accN` off-by-one — the first accumulated frame must OVERWRITE
  (`accN === 1`, no blend), the nth must blend with weight `1/accN`.
- Pitfall: any uniform that changes per rAF while paused (e.g. `uTime` left
  unfrozen) makes the average smear water/veil/rain — that is what `tAnim`
  exists for.

**Commit:** `Diorama: idle temporal accumulation — grain-free beauty stills when paused`

---

## Step 5 — FXAA on the final output (beauty 5)

**Goal.** The G-pass has no MSAA (`getGL` requests `antialias: false`, and the
G-buffer is NEAREST-sampled), so staging silhouettes (mountains, towns, forest
cones) alias. Add a standard FXAA pass as the LAST pass, after tilt-shift —
one fullscreen LDR pass, ~10 texture fetches/px.

**Files:** `src/shaders.ts` (new shader), `src/main.ts` (routing + param).

### 5.1 shaders.ts — append

```ts
// -- pass 4: FXAA (Lottes console variant) -------------------------------------
// Luma-directed 4-tap edge blur with a local-contrast gate. Runs on the final
// LDR image so it also smooths precip streak edges; the composite's 1/255
// dither sits below the contrast gate and is untouched.
export const FXAA_FRAG = `#version 300 es
precision highp float;
out vec4 fragColor;
uniform sampler2D uTex;
uniform vec2 uRes;

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

void main() {
  vec2 px = 1.0 / uRes;
  vec2 uv = gl_FragCoord.xy * px;
  vec3 cM = texture(uTex, uv).rgb;
  float lM = luma(cM);
  float lN = luma(texture(uTex, uv + vec2(0.0,  px.y)).rgb);
  float lS = luma(texture(uTex, uv - vec2(0.0,  px.y)).rgb);
  float lE = luma(texture(uTex, uv + vec2(px.x, 0.0)).rgb);
  float lW = luma(texture(uTex, uv - vec2(px.x, 0.0)).rgb);
  float lMin = min(lM, min(min(lN, lS), min(lE, lW)));
  float lMax = max(lM, max(max(lN, lS), max(lE, lW)));
  if (lMax - lMin < max(0.0312, lMax * 0.125)) { fragColor = vec4(cM, 1.0); return; }
  float lNW = luma(texture(uTex, uv + vec2(-px.x,  px.y)).rgb);
  float lNE = luma(texture(uTex, uv + vec2( px.x,  px.y)).rgb);
  float lSW = luma(texture(uTex, uv + vec2(-px.x, -px.y)).rgb);
  float lSE = luma(texture(uTex, uv + vec2( px.x, -px.y)).rgb);
  vec2 dir = vec2(-((lNW + lNE) - (lSW + lSE)), (lNW + lSW) - (lNE + lSE));
  float dirReduce = max((lNW + lNE + lSW + lSE) * 0.03125, 1.0 / 128.0);
  float rcp = 1.0 / (min(abs(dir.x), abs(dir.y)) + dirReduce);
  dir = clamp(dir * rcp, vec2(-8.0), vec2(8.0)) * px;
  vec3 a = 0.5 * (texture(uTex, uv + dir * (1.0 / 3.0 - 0.5)).rgb
                + texture(uTex, uv + dir * (2.0 / 3.0 - 0.5)).rgb);
  vec3 b = a * 0.5 + 0.25 * (texture(uTex, uv + dir * -0.5).rgb
                           + texture(uTex, uv + dir *  0.5).rgb);
  float lB = luma(b);
  fragColor = vec4((lB < lMin || lB > lMax) ? a : b, 1.0);
}
`;
```

### 5.2 main.ts — routing

```ts
const fxaaOn = params.get("fxaa") !== "0";
const progFxaa = compileProgram(gl, VERT, FXAA_FRAG);
gl.useProgram(progFxaa);
gl.uniform1i(loc(progFxaa, "uTex"), 0);
```

Routing table (final pass chain, building on step 4's `postSrc`):

| ts  | fxaa | chain after composite→sceneT (+acc→accT)                              |
|-----|------|-----------------------------------------------------------------------|
| on  | on   | H: postSrc→blurT · V+grade: blurT→sceneT · FXAA: sceneT→screen        |
| on  | off  | H: postSrc→blurT · V+grade: blurT→screen (today's path)               |
| off | on   | FXAA: postSrc→screen                                                  |
| off | off  | blit postSrc→screen (or direct-to-screen composite if acc is off too) |

Notes for the "ts on, fxaa on" row: the V+grade pass writes INTO `sceneT` —
legal, because that pass samples only `blurT` (WebGL feedback rules forbid
sampling a texture bound to the current framebuffer; `sceneT` is not sampled
there). FXAA then reads `sceneT` to screen:

```ts
gl.bindFramebuffer(gl.FRAMEBUFFER, null);
gl.viewport(0, 0, canvas.width, canvas.height);
gl.useProgram(progFxaa);
gl.uniform2f(loc(progFxaa, "uRes"), canvas.width, canvas.height);
gl.activeTexture(gl.TEXTURE0);
gl.bindTexture(gl.TEXTURE_2D, sceneT.tex);
drawFullscreen(gl);
```

### Verify (step 5)

- Captures `?frame=150&fxaa=0` vs default at `rs=1`; crop-zoom the mountain
  ridge and town silhouettes in the sharp focus band — stair-stepping smoothed,
  no visible blur of the cloud (clouds are low-frequency; FXAA's contrast gate
  leaves them alone). The HUD is DOM, not canvas — unaffected by definition.
- Check the dither didn't turn into crawling worms: pause 2 s (accumulation
  makes the image clean), then compare fxaa on/off — differences should be
  confined to geometric edges.

**Commit:** `Diorama: FXAA final pass — staging silhouettes de-jaggied`

---

## Step 6 — Tonemap (AgX option) + warm/cool split-tone (beauty 6)

**Goal.** (a) The ACES fit skews hue on the bright sunlit cauliflower (pushes
toward orange near clipping); AgX holds white and rolls off more gracefully.
Implement AgX behind `?tm=`, capture A/B, owner picks the default. (b) A gentle
warm-highlight / cool-shadow split in the grade pass — the warm/cool tension of
storm-light photography.

**Files:** `src/shaders.ts` (FRAG tonemap block, POST_FRAG grade block),
`src/main.ts` (uniforms + params).

### 6.1 FRAG — tonemap block

Replace:

```glsl
col *= uExposure;
col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
```

with:

```glsl
col *= uExposure;
if (uTonemap > 0.5) {
  // AgX (Sobotka; matrices/polynomial as in the three.js implementation).
  // Pipeline: inset matrix → log2 encode → sigmoid contrast → outset matrix
  // → back to linear; the existing gamma below then encodes for display.
  const mat3 AGX_IN = mat3(
    0.842479062253094,  0.0423282422610123, 0.0423756549057051,
    0.0784335999999992, 0.878468636469772,  0.0784336,
    0.0792237451477643, 0.0791661274605434, 0.879142973793104);
  const mat3 AGX_OUT = mat3(
     1.19687900512017,   -0.0528968517574562, -0.0529716355144438,
    -0.0980208811401368,  1.15190312990417,   -0.0980434501171241,
    -0.0990297440797205, -0.0989611768448433,  1.15107367264116);
  const float EV_MIN = -12.47393;
  const float EV_MAX = 4.026069;
  col = AGX_IN * col;
  col = clamp((log2(max(col, vec3(1e-10))) - EV_MIN) / (EV_MAX - EV_MIN), 0.0, 1.0);
  vec3 x2 = col * col;
  vec3 x4 = x2 * x2;
  col = 15.5 * x4 * x2 - 40.14 * x4 * col + 31.96 * x4
      - 6.868 * x2 * col + 0.4298 * x2 + 0.1191 * col - 0.00232;
  col = AGX_OUT * col;
  col = pow(max(col, vec3(0.0)), vec3(2.2)); // AgX outputs 2.2-encoded; back to linear
} else {
  col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14);
}
col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
```

Declare `uniform float uTonemap;` near `uExposure`.

### 6.2 POST_FRAG — split-tone in the grade branch

Inside `if (uGrade > 0.5)`, after the saturation push and before the vignette:

```glsl
// warm/cool split-tone: highlights toward storm-light warmth, shadows toward
// blue-grey — luma-hinged so mid-grey is untouched
col += (l - 0.55) * vec3(0.045, 0.015, -0.045) * uSplit;
col = clamp(col, 0.0, 1.0);
```

(`l` is already computed in that branch.) Declare `uniform float uSplit;`.

### 6.3 main.ts

```ts
const tonemap = (params.get("tm") ?? "agx") === "agx" ? 1 : 0; // ?tm=aces reverts
const split = Math.max(0, numParam("split", 1)); // ?split=0 disables
gl.uniform1f(loc(progVol, "uTonemap"), tonemap);   // in the progVol block
// uSplit is set with the other per-frame progPost uniforms (it is static, but
// progPost uniforms are set in the tilt-shift block — set it there once per
// frame alongside uGrade, value `split` on the grade pass)
```

Careful: `uSplit` belongs to progPost, which is also used as a blit in step 4/5
with `uGrade = 0` — the split only executes in the grade branch, so blits are
unaffected. Still, set `uSplit` explicitly in the tilt-shift block every frame.

### Verify (step 6)

- Captures: `?frame=150&tm=aces&split=0` (old look), `?frame=150&tm=agx&split=0`
  (tonemap alone), `?frame=150` (both). Sun-side too (`az=100&el=25`) — AgX
  should hold the silver-lining rim white where ACES tints it orange.
  Expect AgX to look slightly lower-contrast/greyer overall — that is
  characteristic, not a bug; the owner picks the default (`tm` param stays
  either way; if the owner prefers ACES, flip the default string).
- `split` sanity: mid-grey staging (roads, rock faces) must not shift hue;
  sunlit cloud warms slightly, shadowed base cools slightly.

**Commit:** `Diorama: AgX tonemap option + warm/cool split-tone grade`

---

## Wrap-up (after step 6)

1. Update `diorama/README.md`'s URL-param table with all new params:
   `lc, msw, msa, silver, rays, acc, fxaa, tm, split` (+ existing).
2. Produce a final before/after pair for the owner: old =
   `?frame=150&lc=1&msw=0&silver=0&rays=0&acc=0&fxaa=0&tm=aces&split=0`,
   new = `?frame=150` (all defaults). Same for `az=100&el=25` and one live-
   playback impression. The owner gates the result by eye, exactly like the
   slice-4 beauty gate.
3. Amend `docs/design-diorama-web-viewer-2026-07-16.md` §5.1 with one short
   paragraph: shadow marches replaced by a baked per-frame sun-transmittance
   cache; lighting model now multi-scatter (3 octaves) + silver lobe + sunlit
   haze; grading = AgX (or ACES if owner reverts) + split-tone; idle temporal
   accumulation.
4. Commit + push everything, including the captures' summary (never the PNGs —
   nothing >10 MB in git, and captures are temp artifacts under
   `M:\claud_projects\temp`).

## Explicit non-goals of this plan

- Lightning of any kind (slice 6; blocked on the Phase 4 event-list exporter).
- The remaining perf items from the 2026-07-17 discussion (coarse-occupancy
  empty-space skipping, RGBA noise packing, half-res volume pass, adaptive
  step count) — worth doing, but separate; step 0 alone removes the dominant
  cost. If frame rate on weak GPUs is still short after step 0, do noise
  packing next (smallest diff), then occupancy skip.
- Any change to the web-package format, the pipeline, or the UE app.
