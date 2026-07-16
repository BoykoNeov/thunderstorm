// Storm Diorama — slice 2: full-sequence playback. A decode worker inflates
// gzipped bricks off the main thread; a ring of 3D textures streams ahead of
// the play head (≤1 texture upload per rAF so uploads never hitch a frame);
// the shader crossfades between the two frames bracketing fractional storm
// time. Design: docs/design-diorama-web-viewer-2026-07-16.md §2, §4, slice 2.

import { basis, clampOrbit, direction, type OrbitState } from "./camera";
import { BrickDecoder } from "./decoder";
import { compileProgram, createVolumeTexture, drawFullscreen, getGL, uploadVolume } from "./gl";
import { advance, locate, wantedFrames } from "./playback";
import { SlotPool } from "./ring";
import { volumeBox } from "./scene";
import { decodeConstants, loadManifest, type WebManifest } from "./volume";
import { FRAG, VERT } from "./shaders";

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

let orbit: OrbitState = {
  target: { x: 0, y: 0, z: 5.5 },
  azimuth: (45 * Math.PI) / 180,
  elevation: (24 * Math.PI) / 180,
  distance: 55,
  fovY: (25 * Math.PI) / 180,
};

function fmt(t: number): string {
  return `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
}

async function start() {
  const gl = getGL(canvas);
  const prog = compileProgram(gl, VERT, FRAG);
  gl.useProgram(prog);
  const U = (n: string) => gl.getUniformLocation(prog, n);

  const man: WebManifest = await loadManifest("/data/web_manifest.json");
  const { nx, ny, nz } = man.grid;
  const frameBytes = nx * ny * nz * 4;
  const times = man.frames.map((f) => f.time_s);
  const nFrames = man.frames.length;
  const tEnd = times[nFrames - 1];
  const box = volumeBox(man);
  const dec = decodeConstants(man.volume.channels);

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

  hud.textContent = `drag orbit · wheel zoom · space play/pause · [ ] frame step\nthis storm is 52 km wide, 18 km tall`;

  function resize() {
    const dpr = window.devicePixelRatio * renderScale;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener("resize", resize);
  resize();

  // ---- static uniforms ------------------------------------------------------
  const thr = new Float32Array(4);
  const k = new Float32Array(4);
  for (const c of man.volume.channels) {
    thr[c.plane] = dec.thr[c.plane];
    k[c.plane] = dec.k[c.plane];
  }
  const w = man.volume.channels.map((c) => WEIGHTS[c.name as keyof typeof WEIGHTS] ?? 0);
  gl.uniform3f(U("uSunDir"), SUN.x, SUN.y, SUN.z);
  gl.uniform3f(U("uBoxMin"), box.min.x, box.min.y, box.min.z);
  gl.uniform3f(U("uBoxMax"), box.max.x, box.max.y, box.max.z);
  gl.uniform1i(U("uVolA"), 0);
  gl.uniform1i(U("uVolB"), 1);
  gl.uniform4fv(U("uThr"), thr);
  gl.uniform4fv(U("uK"), k);
  gl.uniform4f(U("uWeights"), w[0], w[1], w[2], w[3]);
  gl.uniform1f(U("uExtScale"), EXT_SCALE);
  gl.uniform1f(U("uSteps"), 280);
  gl.uniform1f(U("uExposure"), 0.75);

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

    if (bind) {
      pool.touch(bind.fa);
      pool.touch(bind.fb);
      const cam = basis(orbit);
      gl.uniform2f(U("uRes"), canvas.width, canvas.height);
      gl.uniform3f(U("uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
      gl.uniform3f(U("uCamRight"), cam.right.x, cam.right.y, cam.right.z);
      gl.uniform3f(U("uCamUp"), cam.up.x, cam.up.y, cam.up.z);
      gl.uniform3f(U("uCamFwd"), cam.forward.x, cam.forward.y, cam.forward.z);
      gl.uniform1f(U("uFovTan"), Math.tan(orbit.fovY / 2));
      gl.uniform1f(U("uMix"), bind.mix);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fa)!]);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_3D, textures[pool.slotOf(bind.fb)!]);
      drawFullscreen(gl);
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
