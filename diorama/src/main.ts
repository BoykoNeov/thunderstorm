// Storm Diorama — slice 3: diorama staging. Three passes per frame: the
// low-poly island/water platter rasterizes into a G-buffer; the fullscreen
// composite raymarches the storm volume over it (the storm's shadow march
// darkens the toy landscape) against a pastel backdrop; a tilt-shift pass
// finishes the miniature read. Streaming playback is slice 2, unchanged: a
// decode worker inflates gzipped bricks off the main thread; a ring of 3D
// textures streams ahead of the play head (≤1 upload per rAF); the shader
// crossfades the two frames bracketing fractional storm time.
// Design: docs/design-diorama-web-viewer-2026-07-16.md §2, §4, §5.2, slice 3.

import { basis, clampOrbit, direction, type OrbitState } from "./camera";
import { BrickDecoder } from "./decoder";
import {
  compileProgram,
  createColorTarget,
  createGBuffer,
  createInstancedVAO,
  createMeshVAO,
  createVolumeTexture,
  drawFullscreen,
  getGL,
  uploadVolume,
  type ColorTarget,
  type GBuffer,
} from "./gl";
import { buildStaging, PLATTER_RADIUS } from "./island";
import { multiply, perspective, project, view } from "./mat";
import { advance, locate, wantedFrames } from "./playback";
import { buildPrecipInstances, HAIL, RAIN, type PrecipSpec } from "./precip";
import { SlotPool } from "./ring";
import { volumeBox } from "./scene";
import { decodeConstants, loadManifest, type WebManifest } from "./volume";
import { FRAG, GEO_FRAG, GEO_VERT, POST_FRAG, PRECIP_FRAG, PRECIP_VERT, VERT } from "./shaders";

// Extinction weights per species — the numbers proven in the UE material
// (docs/phase1-svt-custom-material-2026-07-16.md), so both axes read alike.
const WEIGHTS = { cloud: 1.0, ice: 0.1, rain: 0.02, graupelhail: 0.005 };
// km^-1 per weighted (kg/kg): 2000 → σ ≈ 10/km in a 5 g/kg core (opaque within
// ~0.5 km) while the ~0.1 g/kg anvil edge stays translucent. Tuned by eye.
const EXT_SCALE = 2000.0;

// Side-lit relative to the default camera (az 45°): one flank in sun, one in
// shade — that ratio is what makes the cauliflower read as 3D.
const SUN = direction((100 * Math.PI) / 180, (40 * Math.PI) / 180);

// Streaming envelope. 24 slots × 12.5 MB (208·208·72·4) ≈ 300 MB GPU — the
// ring, not full residency, is the design (must work on lesser GPUs too).
// Capacity must comfortably exceed the protected window (READ_AHEAD + 2 wanted
// + 2 last-bound): texSubImage3D into a texture the GPU drew from moments ago
// forces a driver sync-wait (measured 50–77 ms spikes with only 2 rotating
// slots); ~10 rotating slots keep every upload ~1–2 ms.
const RING_CAPACITY = 24;
const READ_AHEAD = 10; // frames beyond the current pair kept warm
const MAX_INFLIGHT = 4; // concurrent fetch+gunzip requests in the worker

// Mesh-pass projection planes (rays are generated analytically; these only
// bound the depth buffer — see mat.ts round-trip test).
const NEAR = 0.2; // km
const FAR = 700; // km

const canvas = document.getElementById("view") as HTMLCanvasElement;
const hud = document.getElementById("hud") as HTMLDivElement;
const errBox = document.getElementById("err") as HTMLDivElement;
const bar = document.getElementById("bar") as HTMLDivElement;
const playBtn = document.getElementById("play") as HTMLButtonElement;
const speedSel = document.getElementById("speed") as HTMLSelectElement;
const scrub = document.getElementById("scrub") as HTMLInputElement;
const clockEl = document.getElementById("clock") as HTMLSpanElement;

const params = new URLSearchParams(location.search);
const renderScale = Number(params.get("rs") ?? "1") || 1;
const collectStats = params.has("stats");
const islandSeed = Number(params.get("seed") ?? "1337") || 1337;
const tiltShift = params.get("ts") !== "0"; // ?ts=0 disables the DOF pass
// storm display scale — UNIFORM magnification (proportions stay true),
// render-time only, never baked into data (charter); staging stays 1×, so the
// island reads smaller under the bigger storm — that contrast is the point
const stormScale = Math.min(3, Math.max(1, Number(params.get("sx") ?? "2") || 2));
const precipOn = params.get("precip") !== "0"; // ?precip=0 disables the particles

// starting view, overridable for tuning/captures: ?az=45&el=11&d=145&fov=34
// (deg, km). The default elevation is low enough that the sea horizon sits in
// frame above the platter — elevation must stay below ~fov/2 to see it at all.
let orbit: OrbitState = {
  target: { x: 0, y: 0, z: 3.5 },
  azimuth: ((Number(params.get("az") ?? "45") || 45) * Math.PI) / 180,
  elevation: ((Number(params.get("el") ?? "11") || 11) * Math.PI) / 180,
  distance: Number(params.get("d") ?? "145") || 145,
  fovY: ((Number(params.get("fov") ?? "34") || 34) * Math.PI) / 180,
};

function fmt(t: number): string {
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}

async function start() {
  const gl = getGL(canvas);
  const progGeo = compileProgram(gl, GEO_VERT, GEO_FRAG);
  const progVol = compileProgram(gl, VERT, FRAG);
  const progPost = compileProgram(gl, VERT, POST_FRAG);
  const progPrecip = compileProgram(gl, PRECIP_VERT, PRECIP_FRAG);
  const loc = (p: WebGLProgram, n: string) => gl.getUniformLocation(p, n);

  const man: WebManifest = await loadManifest("/data/web_manifest.json");
  const { nx, ny, nz } = man.grid;
  const frameBytes = nx * ny * nz * 4;
  const times = man.frames.map((f) => f.time_s);
  const nFrames = man.frames.length;
  const tEnd = times[nFrames - 1];
  const box = volumeBox(man, stormScale);
  const dec = decodeConstants(man.volume.channels);

  // ---- staging (decorative, never sim terrain — design doc §5.2) ------------
  const staging = createMeshVAO(gl, buildStaging(islandSeed).data);

  // ---- precipitation instances (slice 4; presentation, never physics) -------
  const rainVAO = createInstancedVAO(gl, buildPrecipInstances(RAIN.count, islandSeed + 11, RAIN.spawnFrac));
  const hailVAO = createInstancedVAO(gl, buildPrecipInstances(HAIL.count, islandSeed + 23, HAIL.spawnFrac));
  const planeOf = (name: string) => man.volume.channels.find((c) => c.name === name)?.plane;

  // ---- playback state -------------------------------------------------------
  // storm time is the single source of truth; speed is a pure UI multiplier
  const startFrame = params.get("frame");
  const startIdx = Math.min(nFrames - 1, Math.max(0, Number(startFrame ?? "0") || 0));
  let tStorm = startFrame !== null ? times[startIdx] : 0;
  let playing = startFrame === null; // autoplay unless inspecting one frame
  let speed = Number(speedSel.value); // storm seconds per wall second
  let buffering = true;

  // ---- streaming state ------------------------------------------------------
  const pool = new SlotPool(RING_CAPACITY);
  const textures: WebGLTexture[] = [];
  for (let i = 0; i < RING_CAPACITY; i++) textures.push(createVolumeTexture(gl, nx, ny, nz));
  const decoder = new BrickDecoder();
  const inflight = new Set<number>();
  const ready = new Map<number, Uint8Array>(); // decoded, awaiting upload
  let lastGood: { fa: number; fb: number; mix: number } | null = null;

  function requestFrame(f: number) {
    inflight.add(f);
    decoder
      .request(`/data/${man.frames[f].rgba}`, frameBytes)
      .then((data) => ready.set(f, data))
      .catch((e: unknown) => console.error(`frame ${f}:`, e))
      .finally(() => inflight.delete(f));
  }

  // ---- controls -------------------------------------------------------------
  bar.style.display = "flex";
  scrub.max = String(tEnd);
  scrub.value = String(tStorm);

  function setPlaying(p: boolean) {
    playing = p;
    playBtn.textContent = p ? "⏸" : "▶";
  }
  setPlaying(playing);

  playBtn.addEventListener("click", () => setPlaying(!playing));
  speedSel.addEventListener("change", () => (speed = Number(speedSel.value)));
  let scrubbing = false;
  scrub.addEventListener("input", () => {
    scrubbing = true;
    tStorm = Number(scrub.value);
  });
  scrub.addEventListener("change", () => (scrubbing = false));

  function stepFrame(dir: number) {
    setPlaying(false);
    const i = locate(times, tStorm).i0;
    tStorm = times[Math.min(nFrames - 1, Math.max(0, i + dir))];
  }
  window.addEventListener("keydown", (e) => {
    if (e.key === " ") {
      e.preventDefault();
      setPlaying(!playing);
    }
    if (e.key === "[") stepFrame(-1);
    if (e.key === "]") stepFrame(+1);
  });

  // orbit: drag + wheel
  let dragging = false;
  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointerup", () => (dragging = false));
  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    orbit = clampOrbit({
      ...orbit,
      azimuth: orbit.azimuth - e.movementX * 0.005,
      elevation: orbit.elevation + e.movementY * 0.005,
    });
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    orbit = clampOrbit({ ...orbit, distance: orbit.distance * Math.exp(e.deltaY * 0.001) });
  }, { passive: false });

  hud.textContent =
    `drag orbit · wheel zoom · space play/pause · [ ] frame step\n` +
    `this storm is 52 km wide, 18 km tall` +
    (stormScale !== 1 ? ` — shown at ${stormScale}× scale` : "") + `\n` +
    `island & water are decorative staging, not simulation data` +
    (precipOn ? `\nrain & hail are stylized particles gated by the simulated near-surface fields` : "");

  // ---- render targets (recreated on resize) ----------------------------------
  let gbuf: GBuffer | null = null;
  let sceneT: ColorTarget | null = null;
  let blurT: ColorTarget | null = null;

  function resize() {
    const dpr = window.devicePixelRatio * renderScale;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    gbuf?.dispose();
    gbuf = createGBuffer(gl, canvas.width, canvas.height);
    if (tiltShift) {
      sceneT?.dispose();
      blurT?.dispose();
      sceneT = createColorTarget(gl, canvas.width, canvas.height);
      blurT = createColorTarget(gl, canvas.width, canvas.height);
    }
  }
  window.addEventListener("resize", resize);
  resize();

  // ---- static uniforms (volume program) --------------------------------------
  const thr = new Float32Array(4);
  const k = new Float32Array(4);
  for (const c of man.volume.channels) {
    thr[c.plane] = dec.thr[c.plane];
    k[c.plane] = dec.k[c.plane];
  }
  const w = man.volume.channels.map((c) => WEIGHTS[c.name as keyof typeof WEIGHTS] ?? 0);
  gl.useProgram(progVol);
  gl.uniform3f(loc(progVol, "uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(loc(progVol, "uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(loc(progVol, "uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(loc(progVol, "uVolA"), 0);
  gl.uniform1i(loc(progVol, "uVolB"), 1);
  gl.uniform1i(loc(progVol, "uAlbedo"), 2);
  gl.uniform1i(loc(progVol, "uNormalTex"), 3);
  gl.uniform1i(loc(progVol, "uDepthTex"), 4);
  gl.uniform1f(loc(progVol, "uNear"), NEAR);
  gl.uniform1f(loc(progVol, "uFar"), FAR);
  gl.uniform4fv(loc(progVol, "uThr"), thr);
  gl.uniform4fv(loc(progVol, "uK"), k);
  gl.uniform4f(loc(progVol, "uWeights"), w[0], w[1], w[2], w[3]);
  // Uniform magnification must keep optical depth invariant: paths through the
  // storm are stormScale× longer in km, so per-km extinction divides by the
  // scale (and the sun-march cap grows with it). The 2× storm then looks like
  // the same cloud shown bigger — not a denser one.
  gl.uniform1f(loc(progVol, "uExtScale"), EXT_SCALE / stormScale);
  gl.uniform1f(loc(progVol, "uSteps"), 280);
  gl.uniform1f(loc(progVol, "uExposure"), 0.75);
  gl.uniform1f(loc(progVol, "uShadowKm"), 15 * stormScale);

  // ---- static uniforms (precip program) --------------------------------------
  // The shared VOL_COMMON chunk gives this program the same names/values as
  // the volume pass; particle speeds/lengths pre-scale by the display scale so
  // the bigger storm sheds bigger rain (same transit time, same proportions).
  gl.useProgram(progPrecip);
  gl.uniform3f(loc(progPrecip, "uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(loc(progPrecip, "uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(loc(progPrecip, "uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(loc(progPrecip, "uVolA"), 0);
  gl.uniform1i(loc(progPrecip, "uVolB"), 1);
  gl.uniform1i(loc(progPrecip, "uDepthTex"), 4);
  gl.uniform4fv(loc(progPrecip, "uThr"), thr);
  gl.uniform4fv(loc(progPrecip, "uK"), k);
  gl.uniform4f(loc(progPrecip, "uWeights"), w[0], w[1], w[2], w[3]);
  gl.uniform1f(loc(progPrecip, "uExtScale"), EXT_SCALE / stormScale);
  gl.uniform1f(loc(progPrecip, "uShadowKm"), 15 * stormScale);
  gl.uniform2f(loc(progPrecip, "uTilt"), 0.1, 0.04); // slight wind-shear lean
  gl.uniform1f(loc(progPrecip, "uGateZ"), 2.5 / nz); // ~625 m: the near-surface layers
  gl.uniform1f(loc(progPrecip, "uMaxR"), PLATTER_RADIUS - 0.8); // rain stays on the diorama

  function drawPrecip(spec: PrecipSpec, vao: WebGLVertexArrayObject, count: number) {
    const plane = planeOf(spec.gateChannel);
    if (plane === undefined) return; // package without that channel: no particles
    const mask = [0, 0, 0, 0];
    mask[plane] = 1;
    gl.uniform4f(loc(progPrecip, "uGateMask"), mask[0], mask[1], mask[2], mask[3]);
    gl.uniform1f(loc(progPrecip, "uQFloor"), spec.qFloor);
    gl.uniform1f(loc(progPrecip, "uQFull"), spec.qFull);
    gl.uniform1f(loc(progPrecip, "uFallSpeed"), spec.fallSpeed * stormScale);
    gl.uniform1f(loc(progPrecip, "uLen"), spec.length * stormScale);
    gl.uniform1f(loc(progPrecip, "uHalfWidth"), spec.halfWidth);
    gl.uniform1f(loc(progPrecip, "uZTop"), spec.zTop * stormScale);
    gl.uniform3f(loc(progPrecip, "uColor"), spec.color[0], spec.color[1], spec.color[2]);
    gl.uniform1f(loc(progPrecip, "uAlphaMax"), spec.alpha);
    gl.bindVertexArray(vao);
    gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, count);
    gl.bindVertexArray(null);
  }

  // ---- pacing stats (?stats — read by the headless verification driver) -----
  const stats = {
    deltas: [] as number[],
    stalls: 0,
    uploads: 0,
    drawn: 0,
    uploadMs: [] as number[], // texSubImage3D wall cost per upload
    stallInfo: [] as { ready: number; inflight: number; resident: number }[],
  };
  if (collectStats) (window as unknown as { __stats: typeof stats }).__stats = stats;

  // ---- frame loop -----------------------------------------------------------
  let lastNow = performance.now();
  function frame(now: number) {
    const rawDtMs = now - lastNow;
    const dtWall = Math.min(rawDtMs / 1000, 0.1); // clamp tab-away gaps
    lastNow = now;

    // 1. what does the play head need?
    let pos = locate(times, tStorm);
    const wanted = wantedFrames(pos.i0, READ_AHEAD, nFrames);
    const wantedSet = new Set(wanted);

    // 2. schedule decodes for missing frames, in priority order
    for (const f of wanted) {
      if (inflight.size >= MAX_INFLIGHT) break;
      if (pool.slotOf(f) === null && !inflight.has(f) && !ready.has(f)) requestFrame(f);
    }

    // 3. upload at most ONE decoded brick per rAF (12.5 MB — keeps the GPU
    //    copy off the critical path; 60 uploads/s ≫ 25 frames/s at 300×)
    for (const f of ready.keys()) if (!wantedSet.has(f)) ready.delete(f); // stale scrub leftovers
    const keep = new Set(wantedSet);
    if (lastGood) {
      keep.add(lastGood.fa);
      keep.add(lastGood.fb);
    }
    for (const f of wanted) {
      const data = ready.get(f);
      if (!data) continue;
      const slot = pool.assign(f, keep);
      if (slot !== null) {
        const u0 = performance.now();
        uploadVolume(gl, textures[slot], nx, ny, nz, data);
        if (collectStats && stats.uploadMs.length < 2000) stats.uploadMs.push(performance.now() - u0);
        ready.delete(f);
        stats.uploads++;
      }
      break;
    }

    // 4. advance the clock — but never past frames that aren't resident yet
    //    (playback holds, storm time never skips)
    if (playing && !scrubbing) {
      const tNext = advance(tStorm, dtWall * speed, 0, tEnd);
      const posNext = locate(times, tNext);
      const ok = pool.slotOf(posNext.i0) !== null && pool.slotOf(posNext.i1) !== null;
      if (ok) tStorm = tNext;
      else {
        stats.stalls++;
        if (collectStats && stats.stallInfo.length < 500) {
          stats.stallInfo.push({ ready: ready.size, inflight: inflight.size, resident: pool.resident().length });
        }
      }
      pos = locate(times, tStorm);
    }

    // 5. bind the pair (falling back to the last complete pair while buffering)
    const sa = pool.slotOf(pos.i0);
    const sb = pool.slotOf(pos.i1);
    let bind: { fa: number; fb: number; mix: number } | null = null;
    if (sa !== null && sb !== null) {
      bind = { fa: pos.i0, fb: pos.i1, mix: pos.f };
      lastGood = bind;
      buffering = false;
    } else {
      bind = lastGood;
      buffering = true;
    }

    if (bind && gbuf) {
      pool.touch(bind.fa);
      pool.touch(bind.fb);
      const cam = basis(orbit);
      const aspect = canvas.width / canvas.height;
      const viewProj = multiply(perspective(orbit.fovY, aspect, NEAR, FAR), view(cam));

      // -- pass 1: staging mesh into the g-buffer ------------------------------
      gl.bindFramebuffer(gl.FRAMEBUFFER, gbuf.fbo);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.enable(gl.DEPTH_TEST);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.useProgram(progGeo);
      gl.uniformMatrix4fv(loc(progGeo, "uViewProj"), false, viewProj);
      gl.bindVertexArray(staging.vao);
      gl.drawArrays(gl.TRIANGLES, 0, staging.count);
      gl.bindVertexArray(null);
      gl.disable(gl.DEPTH_TEST);

      // -- pass 2: volume raymarch + surface shading + backdrop ----------------
      gl.bindFramebuffer(gl.FRAMEBUFFER, tiltShift && sceneT ? sceneT.fbo : null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(progVol);
      gl.uniform2f(loc(progVol, "uRes"), canvas.width, canvas.height);
      gl.uniform3f(loc(progVol, "uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
      gl.uniform3f(loc(progVol, "uCamRight"), cam.right.x, cam.right.y, cam.right.z);
      gl.uniform3f(loc(progVol, "uCamUp"), cam.up.x, cam.up.y, cam.up.z);
      gl.uniform3f(loc(progVol, "uCamFwd"), cam.forward.x, cam.forward.y, cam.forward.z);
      gl.uniform1f(loc(progVol, "uFovTan"), Math.tan(orbit.fovY / 2));
      gl.uniform1f(loc(progVol, "uMix"), bind.mix);
      gl.uniform1f(loc(progVol, "uTime"), now / 1000);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fa)!]);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fb)!]);
      gl.activeTexture(gl.TEXTURE2);
      gl.bindTexture(gl.TEXTURE_2D, gbuf.albedo);
      gl.activeTexture(gl.TEXTURE3);
      gl.bindTexture(gl.TEXTURE_2D, gbuf.normal);
      gl.activeTexture(gl.TEXTURE4);
      gl.bindTexture(gl.TEXTURE_2D, gbuf.depth);
      drawFullscreen(gl);

      // -- pass 2.5: precipitation particles (same target, before tilt-shift so
      //    the DOF treats rain like everything else; volume + depth textures are
      //    still bound on units 0/1/4) -----------------------------------------
      if (precipOn) {
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(progPrecip);
        gl.uniformMatrix4fv(loc(progPrecip, "uViewProj"), false, viewProj);
        gl.uniform3f(loc(progPrecip, "uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
        gl.uniform1f(loc(progPrecip, "uMix"), bind.mix);
        gl.uniform1f(loc(progPrecip, "uTimeWall"), now / 1000);
        gl.uniform2f(loc(progPrecip, "uRes"), canvas.width, canvas.height);
        drawPrecip(RAIN, rainVAO.vao, RAIN.count);
        drawPrecip(HAIL, hailVAO.vao, HAIL.count);
        gl.disable(gl.BLEND);
      }

      // -- pass 3: tilt-shift (H then V + grade) --------------------------------
      if (tiltShift && sceneT && blurT) {
        // keep the sharp band pinned to the platter: project the diorama
        // centre at ground level and focus there
        const c = project(viewProj, { x: orbit.target.x, y: orbit.target.y, z: 0 });
        const focusY = Math.min(0.85, Math.max(0.15, c.y * 0.5 + 0.5));
        const maxRadius = Math.min(12, canvas.height * 0.009);
        gl.useProgram(progPost);
        gl.uniform1i(loc(progPost, "uTex"), 0);
        gl.uniform2f(loc(progPost, "uRes"), canvas.width, canvas.height);
        gl.uniform1f(loc(progPost, "uFocusY"), focusY);
        // wider than slice 3's 0.20: at 2× vertical exaggeration the anvil
        // sits far above the focus line and a tight band smears it entirely
        gl.uniform1f(loc(progPost, "uBand"), 0.26);
        gl.uniform1f(loc(progPost, "uMaxRadius"), maxRadius);

        gl.bindFramebuffer(gl.FRAMEBUFFER, blurT.fbo);
        gl.uniform2f(loc(progPost, "uDir"), 1, 0);
        gl.uniform1f(loc(progPost, "uGrade"), 0);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, sceneT.tex);
        drawFullscreen(gl);

        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.uniform2f(loc(progPost, "uDir"), 0, 1);
        gl.uniform1f(loc(progPost, "uGrade"), 1);
        gl.bindTexture(gl.TEXTURE_2D, blurT.tex);
        drawFullscreen(gl);
      }
      stats.drawn++;
    }

    // 6. UI readout
    if (!scrubbing) scrub.value = String(tStorm);
    clockEl.textContent =
      `${fmt(tStorm)} / ${fmt(tEnd)} · frame ${pos.i0}/${nFrames - 1}` +
      (buffering ? " · buffering…" : "");

    if (collectStats) {
      stats.deltas.push(rawDtMs); // raw rAF spacing, ms
      if (stats.deltas.length > 4000) stats.deltas.shift();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

start().catch((e: unknown) => {
  errBox.style.display = "block";
  errBox.textContent =
    `Storm Diorama failed to start:\n${e instanceof Error ? e.message : String(e)}\n\n` +
    `Is the scenario web export present at scenarios/single_cell_500m/web/?\n` +
    `(pipeline: export_scenario.py export-web — see docs/design-diorama-web-viewer-2026-07-16.md)`;
});
