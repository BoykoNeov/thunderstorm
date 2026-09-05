// One-off perf probe: load each URL in headless Chrome, wait for streaming,
// let it render ~4 s, then read window.__stats.deltas and print median/mean.
// Reuses shot.mjs's self-launch + tag-sweep so no Chrome orphan survives.
//   node tools/statprobe.mjs <chrome.exe> <label>=<url> [<label>=<url> ...]
import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const [chrome, ...rest] = process.argv.slice(2);
const jobs = rest.map((a) => { const i = a.indexOf("="); return { label: a.slice(0, i), url: a.slice(i + 1) }; });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tag = `diorama-stat-${process.pid}-${Math.floor(Math.random() * 1e9)}`;
const profileDir = path.join(os.tmpdir(), tag);
let swept = false;
function sweep() {
  if (swept) return; swept = true;
  try { child?.kill("SIGKILL"); } catch {}
  try {
    execFileSync("powershell.exe", ["-NoProfile", "-Command",
      `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -match '${tag}' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`],
      { stdio: "ignore", timeout: 15000 });
  } catch {}
}
for (const sig of ["exit", "SIGINT", "SIGTERM", "uncaughtException"]) process.on(sig, () => sweep());

const child = spawn(chrome, ["--headless=new", "--remote-debugging-port=0",
  `--user-data-dir=${profileDir}`, "--window-size=1600,900", "--no-first-run",
  "--no-default-browser-check", "--use-angle=default", "about:blank"], { stdio: "ignore" });

async function readPort() {
  const f = path.join(profileDir, "DevToolsActivePort");
  const dl = Date.now() + 15000;
  while (Date.now() < dl) {
    try { const t = fs.readFileSync(f, "utf8").trim().split("\n"); if (t[0]) return Number(t[0]); } catch {}
    await sleep(150);
  }
  throw new Error("no DevTools port");
}
function conn(wsUrl) {
  const ws = new WebSocket(wsUrl); let id = 0; const pending = new Map();
  ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); } });
  const ready = new Promise((res, rej) => { ws.addEventListener("open", res); ws.addEventListener("error", rej); });
  const send = (method, params = {}, sessionId) => new Promise((res) => { const myId = ++id; pending.set(myId, res); ws.send(JSON.stringify({ id: myId, method, params, sessionId })); });
  return { ready, send, close: () => ws.close() };
}
const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;

async function main() {
  const port = await readPort();
  const ver = await (await fetch(`http://localhost:${port}/json/version`)).json();
  const b = conn(ver.webSocketDebuggerUrl); await b.ready;
  for (const { label, url } of jobs) {
    const { targetId } = await b.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await b.send("Target.attachToTarget", { targetId, flatten: true });
    const S = (m, p) => b.send(m, p, sessionId);
    await S("Page.enable"); await S("Runtime.enable"); await S("Page.navigate", { url });
    const dl = Date.now() + 45000; let buffering = true;
    while (Date.now() < dl) {
      await sleep(300);
      const r = await S("Runtime.evaluate", { expression: "(t=>t.includes('frame')&&!t.includes('buffering'))(document.body.innerText)", returnByValue: true });
      if (r?.result?.value === true) { buffering = false; break; }
    }
    // reset the deltas buffer, then let it run to collect a clean window
    await S("Runtime.evaluate", { expression: "window.__stats && (window.__stats.deltas.length=0)" });
    await sleep(4000);
    const r = await S("Runtime.evaluate", { expression: "JSON.stringify(window.__stats ? {deltas: window.__stats.deltas, gpu: window.__stats.gpu, gpuSamples: window.__stats.gpuSamples, fps: window.__stats.fps, stalls: window.__stats.stalls, uploads: window.__stats.uploads, uploadMs: window.__stats.uploadMs} : null)", returnByValue: true });
    const st = JSON.parse(r.result.value);
    const d = st?.deltas;
    if (!d || d.length === 0) { console.log(`${label}: NO STATS (buffering=${buffering})`); }
    else {
      const w = d.slice(2);
      // per-pass GPU ms (EMA, EXT_disjoint_timer_query_webgl2) is the honest
      // cost signal; rAF spacing is kept for pacing/stall context only.
      const g = st.gpu ?? {};
      const total = Object.values(g).reduce((a, b) => a + b, 0);
      const gpuTxt = st.gpuSamples > 0
        ? `gpu=${total.toFixed(2)}ms [${Object.entries(g).map(([k, v]) => `${k} ${v.toFixed(2)}`).join(", ")}]`
        : "gpu=n/a";
      const p95 = [...w].sort((x, y) => x - y)[Math.floor(w.length * 0.95)];
      const um = st.uploadMs ?? [];
      console.log(`${label}: ${gpuTxt} | raf median=${median(w).toFixed(2)}ms mean=${mean(w).toFixed(2)}ms p95=${p95.toFixed(1)} max=${Math.max(...w).toFixed(1)} n=${w.length} | stalls=${st.stalls} uploads=${st.uploads} uploadMs median=${um.length ? median(um).toFixed(2) : "-"} max=${um.length ? Math.max(...um).toFixed(1) : "-"}`);
    }
    await b.send("Target.closeTarget", { targetId });
  }
  b.close();
}
try { await main(); } finally { sweep(); }
process.exit(0);
