// Live picker check -- the part unit tests structurally cannot cover.
//
// The pure helpers can be 18/18 green while the dropdown renders nothing, the
// page opens on the wrong package, or the reload drops the view params. This
// drives a real Chrome over CDP against the real dev server and asserts on the
// rendered DOM and the post-reload URL.
//
// Launch/kill discipline copied from tools/shot.mjs: own --user-data-dir under a
// unique tag, killed by the PIDs carrying that tag (never by image name).
import { spawn, execFileSync } from "node:child_process";
import path from "node:path";
import os from "node:os";

// usage: node tools/picker-check.mjs <chrome.exe> [base-url]
const CHROME = process.argv[2];
const BASE = process.argv[3] ?? "http://localhost:5173";
if (!CHROME) {
  console.error("usage: node tools/picker-check.mjs <chrome.exe> [http://localhost:PORT]");
  process.exit(2);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const DBG = 9300 + (process.pid % 200); // avoid colliding with a concurrent run
const tag = `diorama-pick-${process.pid}-${Math.floor(Math.random() * 1e9)}`;
const profileDir = path.join(os.tmpdir(), tag);
let child, swept = false;
function sweep() {
  if (swept) return; swept = true;
  try { child?.kill("SIGKILL"); } catch {}
  try {
    execFileSync("powershell.exe", ["-NoProfile", "-Command",
      `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ` +
      `Where-Object { $_.CommandLine -match '${tag}' } | ` +
      `ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`],
      { stdio: "ignore", timeout: 15000 });
  } catch {}
}
for (const sig of ["exit", "SIGINT", "SIGTERM"]) process.on(sig, sweep);

child = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${DBG}`, `--user-data-dir=${profileDir}`,
  "--no-first-run", "--no-default-browser-check", "--disable-gpu-sandbox",
  "--window-size=1200,800", "about:blank",
], { stdio: "ignore" });

async function cdpUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${DBG}/json/list`);
      const t = (await r.json()).find((x) => x.type === "page");
      if (t?.webSocketDebuggerUrl) return t.webSocketDebuggerUrl;
    } catch {}
    await sleep(250);
  }
  throw new Error("no CDP target");
}

const ws = new WebSocket(await cdpUrl()); // node's global WebSocket (>=22)
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
};
function send(method, params = {}) {
  const i = ++id;
  ws.send(JSON.stringify({ id: i, method, params }));
  return new Promise((r) => pending.set(i, r));
}
async function evaluate(expr) {
  const m = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (m.result?.exceptionDetails) throw new Error(JSON.stringify(m.result.exceptionDetails));
  return m.result?.result?.value;
}
async function goto(url) {
  await send("Page.navigate", { url });
  for (let i = 0; i < 120; i++) {
    await sleep(500);
    const ready = await evaluate(
      `(() => { const s = document.getElementById('scenario');
                return !!s && s.options.length > 0 && getComputedStyle(s).display !== 'none'; })()`
    ).catch(() => false);
    if (ready) return;
  }
  throw new Error("picker never populated at " + url);
}

await send("Page.enable");
await send("Runtime.enable");

const results = [];
const check = (name, ok, detail) => { results.push([ok, name, detail]); };

// --- 1. no ?scenario= at all: what does the app OPEN on? -------------------
await goto(`${BASE}/?az=90&el=25&layer=dbz&anim=0`);
const opened = await evaluate(`document.getElementById('scenario').value`);
check("opens on the coarse supercell with no ?scenario=", opened === "supercell_333m_coarse", opened);

const opts = await evaluate(
  `[...document.getElementById('scenario').options].map(o => o.value + ' => ' + o.textContent)`);
check("dropdown lists all four packages", opts.length === 4, `\n      ` + opts.join("\n      "));

const crsLbl = await evaluate(
  `[...document.getElementById('scenario').options].find(o => o.value === 'supercell_333m_coarse').textContent`);
const natLbl = await evaluate(
  `[...document.getElementById('scenario').options].find(o => o.value === 'supercell_333m').textContent`);
check("the light one says so in words", /lighter/.test(crsLbl), crsLbl);
check("the original says so in words", /full detail/.test(natLbl), natLbl);
const scLbl = await evaluate(
  `(() => { const l = document.getElementById('scenarioLbl');
            return getComputedStyle(l).display !== 'none' ? l.textContent : '(hidden)'; })()`);
check("the dropdown carries a visible label", scLbl === "Storm", scLbl);

const grid0 = await evaluate(`document.getElementById('hud').textContent`);
const clk0 = await evaluate(`document.getElementById("clock").textContent`);
// NOT the buffering regex alone: an EMPTY hud passes that vacuously. The clock
// only carries a storm time once a frame is decoded and drawn.
check("coarse package actually rendered a frame",
  !/buffering/i.test(grid0) && /storm time/i.test(clk0) && /\d/.test(clk0), JSON.stringify(clk0));

// --- 2. switching to the original from the dropdown ------------------------
await evaluate(
  `(() => { const s = document.getElementById('scenario');
            s.value = 'supercell_333m';
            s.dispatchEvent(new Event('change')); })()`);
await sleep(1200);
for (let i = 0; i < 120; i++) {
  await sleep(500);
  const ok = await evaluate(
    `(() => { const s = document.getElementById('scenario');
              return !!s && s.value === 'supercell_333m' && !/buffering/i.test(document.getElementById('hud').textContent); })()`
  ).catch(() => false);
  if (ok) break;
}
const href = await evaluate(`location.search`);
check("switch put ?scenario=supercell_333m in the URL", /scenario=supercell_333m(?!_)/.test(href), href);
check("switch PRESERVED the view params", /az=90/.test(href) && /el=25/.test(href) && /layer=dbz/.test(href), href);
const sel2 = await evaluate(`document.getElementById('scenario').value`);
check("picker shows the original after the reload", sel2 === "supercell_333m", sel2);
const hud2 = await evaluate(`document.getElementById('hud').textContent`);
const clk2 = await evaluate(`document.getElementById("clock").textContent`);
check("original package actually rendered a frame",
  !/buffering/i.test(hud2) && /storm time/i.test(clk2) && /\d/.test(clk2), JSON.stringify(clk2));

// --- 3. an old bookmark still wins over the new default --------------------
await goto(`${BASE}/?scenario=single_cell_500m&anim=0`);
const book = await evaluate(`document.getElementById('scenario').value`);
check("an old bookmark keeps its storm", book === "single_cell_500m", book);
const bookLbl = await evaluate(
  `[...document.getElementById('scenario').options].find(o => o.value === 'single_cell_500m').textContent`);
check("a package with no sibling gets no detail tag", !/lighter|full detail/.test(bookLbl), bookLbl);

let pass = 0;
for (const [ok, name, detail] of results) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -- " + detail : ""}`);
  if (ok) pass++;
}
console.log(`\n${pass}/${results.length} gates pass`);
sweep();
process.exit(pass === results.length ? 0 : 1);
