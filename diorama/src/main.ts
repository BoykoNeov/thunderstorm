// Storm Diorama — slice 1: one real CM1 frame raymarched over a flat ground
// plane, orbit camera, sun self-shadowing. Design: docs/design-diorama-web-
// viewer-2026-07-16.md. Playback/streaming is slice 2; island staging slice 3.

import { basis, clampOrbit, direction, type OrbitState } from "./camera";
import { compileProgram, createVolumeTexture, drawFullscreen, getGL, uploadVolume } from "./gl";
import { volumeBox } from "./scene";
import { decodeConstants, loadBrick, loadManifest, type WebManifest } from "./volume";
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

const canvas = document.getElementById("view") as HTMLCanvasElement;
const hud = document.getElementById("hud") as HTMLDivElement;
const errBox = document.getElementById("err") as HTMLDivElement;

const params = new URLSearchParams(location.search);
const renderScale = Number(params.get("rs") ?? "1") || 1;

let orbit: OrbitState = {
  target: { x: 0, y: 0, z: 5.5 },
  azimuth: (45 * Math.PI) / 180,
  elevation: (24 * Math.PI) / 180,
  distance: 55,
  fovY: (25 * Math.PI) / 180,
};

async function start() {
  const gl = getGL(canvas);
  const prog = compileProgram(gl, VERT, FRAG);
  gl.useProgram(prog);
  const U = (n: string) => gl.getUniformLocation(prog, n);

  const man: WebManifest = await loadManifest("/data/web_manifest.json");
  const { nx, ny, nz } = man.grid;
  const tex = createVolumeTexture(gl, nx, ny, nz);
  const dec = decodeConstants(man.volume.channels);

  // frame selection: ?frame=NNN, default 150 (the hero Cb), else first present
  const wanted = Number(params.get("frame") ?? "150");
  const indices = man.frames.map((f) => f.index);
  let cursor = indices.includes(wanted) ? indices.indexOf(wanted) : 0;
  const cache = new Map<number, Uint8Array>();

  async function showFrame(c: number) {
    cursor = ((c % man.frames.length) + man.frames.length) % man.frames.length;
    const rec = man.frames[cursor];
    let data = cache.get(rec.index);
    if (!data) {
      data = await loadBrick(`/data/${rec.rgba}`, nx * ny * nz * 4);
      cache.set(rec.index, data);
    }
    uploadVolume(gl, tex, nx, ny, nz, data);
    const t = rec.time_s;
    hud.textContent =
      `frame ${rec.index}  ·  storm time ${Math.floor(t / 60)}:${String(Math.round(t % 60)).padStart(2, "0")}\n` +
      `drag orbit · wheel zoom · [ ] frame step · this storm is 52 km wide, 18 km tall`;
  }
  await showFrame(cursor);

  const box = volumeBox(man);

  function resize() {
    const dpr = window.devicePixelRatio * renderScale;
    canvas.width = Math.round(canvas.clientWidth * dpr);
    canvas.height = Math.round(canvas.clientHeight * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
  }
  window.addEventListener("resize", resize);
  resize();

  // input: orbit drag, wheel zoom, frame stepping
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
  window.addEventListener("keydown", (e) => {
    if (e.key === "[") void showFrame(cursor - 1);
    if (e.key === "]") void showFrame(cursor + 1);
  });

  const thr = new Float32Array(4);
  const k = new Float32Array(4);
  for (const c of man.volume.channels) {
    thr[c.plane] = dec.thr[c.plane];
    k[c.plane] = dec.k[c.plane];
  }
  const w = man.volume.channels.map(
    (c) => WEIGHTS[c.name as keyof typeof WEIGHTS] ?? 0,
  );

  function frame() {
    const cam = basis(orbit);
    gl.uniform2f(U("uRes"), canvas.width, canvas.height);
    gl.uniform3f(U("uCamPos"), cam.pos.x, cam.pos.y, cam.pos.z);
    gl.uniform3f(U("uCamRight"), cam.right.x, cam.right.y, cam.right.z);
    gl.uniform3f(U("uCamUp"), cam.up.x, cam.up.y, cam.up.z);
    gl.uniform3f(U("uCamFwd"), cam.forward.x, cam.forward.y, cam.forward.z);
    gl.uniform1f(U("uFovTan"), Math.tan(orbit.fovY / 2));
    gl.uniform3f(U("uSunDir"), SUN.x, SUN.y, SUN.z);
    gl.uniform3f(U("uBoxMin"), box.min.x, box.min.y, box.min.z);
    gl.uniform3f(U("uBoxMax"), box.max.x, box.max.y, box.max.z);
    gl.uniform1i(U("uVol"), 0);
    gl.uniform4fv(U("uThr"), thr);
    gl.uniform4fv(U("uK"), k);
    gl.uniform4f(U("uWeights"), w[0], w[1], w[2], w[3]);
    gl.uniform1f(U("uExtScale"), EXT_SCALE);
    gl.uniform1f(U("uSteps"), 280);
    gl.uniform1f(U("uExposure"), 0.75);
    gl.activeTexture(gl.TEXTURE0);
    drawFullscreen(gl);
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
