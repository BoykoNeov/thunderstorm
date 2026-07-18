// Leak-safe headless-Chrome screenshot driver for the diorama.
//
// WHY THIS EXISTS
//   1. `--virtual-time-budget` fires the screenshot before the async brick
//      fetch/decode/upload settles, so it always caught the "buffering…"
//      screen. This drives Chrome over CDP and polls the HUD until a frame is
//      streamed and not buffering.
//   2. Chrome re-execs itself into a NEW pid on launch; child.kill() / closing
//      the launcher leaves an orphan that KEEPS RENDERING the WebGL raymarch at
//      full tilt (it has pegged this machine's GPU before). So every capture
//      run launches its OWN Chrome under a UNIQUE --user-data-dir tag and, on
//      EVERY exit path, sweep-kills every chrome.exe whose command line carries
//      that tag — the only reliable kill across the re-parenting.
//
// USAGE
//   node tools/shot.mjs <chrome.exe> <out1.png> <url1> [<out2.png> <url2> ...]
//   Batches all pairs through one Chrome launch. Env: SHOT_SETTLE_MS (default
//   1500) extra wait after buffering clears; SHOT_TIMEOUT_MS (default 45000).

import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const [chrome, ...rest] = process.argv.slice(2);
if (!chrome || rest.length < 2 || rest.length % 2 !== 0) {
  console.error("usage: node tools/shot.mjs <chrome.exe> <out.png> <url> [<out.png> <url> ...]");
  process.exit(2);
}
const pairs = [];
for (let i = 0; i < rest.length; i += 2) pairs.push({ out: rest[i], url: rest[i + 1] });

const settle = Number(process.env.SHOT_SETTLE_MS ?? 1500);
const timeout = Number(process.env.SHOT_TIMEOUT_MS ?? 45000);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Unique, greppable tag for the sweep — profile dir carries it in the cmdline.
const tag = `diorama-shot-${process.pid}-${Math.floor(Math.random() * 1e9)}`;
const profileDir = path.join(os.tmpdir(), tag);

let swept = false;
function sweep() {
  if (swept) return;
  swept = true;
  try { child?.kill("SIGKILL"); } catch {}
  // Kill by tag regardless of Chrome's re-exec/re-parenting (Windows).
  try {
    execFileSync(
      "powershell.exe",
      ["-NoProfile", "-Command",
        `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ` +
        `Where-Object { $_.CommandLine -match '${tag}' } | ` +
        `ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`],
      { stdio: "ignore", timeout: 15000 },
    );
  } catch {}
}
for (const sig of ["exit", "SIGINT", "SIGTERM", "uncaughtException"]) {
  process.on(sig, (e) => { sweep(); if (sig === "uncaughtException") { console.error(e); process.exit(1); } });
}

const child = spawn(chrome, [
  "--headless=new",
  "--remote-debugging-port=0", // pick a free port; read it back from the profile
  `--user-data-dir=${profileDir}`,
  "--window-size=1600,900",
  "--no-first-run",
  "--no-default-browser-check",
  "about:blank",
], { stdio: "ignore" });

// Chrome writes the chosen port to DevToolsActivePort in the profile dir.
async function readPort() {
  const f = path.join(profileDir, "DevToolsActivePort");
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      const txt = fs.readFileSync(f, "utf8").trim().split("\n");
      if (txt[0]) return Number(txt[0]);
    } catch {}
    await sleep(150);
  }
  throw new Error("Chrome did not report a DevTools port");
}

function conn(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
  });
  const ready = new Promise((res, rej) => {
    ws.addEventListener("open", res);
    ws.addEventListener("error", rej);
  });
  const send = (method, params = {}, sessionId) =>
    new Promise((res) => {
      const myId = ++id;
      pending.set(myId, res);
      ws.send(JSON.stringify({ id: myId, method, params, sessionId }));
    });
  return { ready, send, close: () => ws.close() };
}

async function main() {
  const port = await readPort();
  const ver = await (await fetch(`http://localhost:${port}/json/version`)).json();
  const b = conn(ver.webSocketDebuggerUrl);
  await b.ready;

  for (const { out, url } of pairs) {
    // Fresh tab per capture so nothing accumulates; close it right after.
    const { targetId } = await b.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await b.send("Target.attachToTarget", { targetId, flatten: true });
    const S = (m, p) => b.send(m, p, sessionId);
    await S("Page.enable");
    await S("Runtime.enable");
    await S("Page.navigate", { url });

    const deadline = Date.now() + timeout;
    let buffering = true;
    while (Date.now() < deadline) {
      await sleep(300);
      const r = await S("Runtime.evaluate", {
        // Ready = HUD clock populated ("frame N/…") AND not buffering. An empty
        // DOM (still booting) lacks "buffering" too, so absence alone fires early.
        expression: "(t=>t.includes('frame')&&!t.includes('buffering'))(document.body.innerText)",
        returnByValue: true,
      });
      buffering = r?.result?.value !== true;
      if (!buffering) break;
    }
    await sleep(settle); // let the shadow bake + a few clean rAFs land

    const shot = await S("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(out, Buffer.from(shot.data, "base64"));
    console.log(`${buffering ? "TIMED-OUT-buffering" : "ok"} ${out}`);
    await b.send("Target.closeTarget", { targetId });
  }
  b.close();
}

try {
  await main();
} finally {
  sweep();
}
process.exit(0);
