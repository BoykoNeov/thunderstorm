// Headless-Chrome screenshot driver that WAITS for the volume to finish
// streaming before capturing. `--virtual-time-budget` fires before the async
// brick fetch/decode/upload settles, so it always caught the "buffering…"
// screen; this instead polls the live page until buffering clears.
//
// Usage: node tools/shot.mjs <chrome.exe> <outPng> <url> [extraSettleMs]
// Requires a Chrome already launched with --remote-debugging-port=9222.

const [, , , outPng, url, settleArg] = process.argv;
const extraSettle = Number(settleArg ?? 1500);
const DBG = "http://localhost:9222";

async function cdpTarget() {
  const r = await fetch(`${DBG}/json/new?about:blank`, { method: "PUT" });
  return r.json();
}

function conn(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      pending.get(m.id)(m.result);
      pending.delete(m.id);
    }
  });
  const ready = new Promise((res) => ws.addEventListener("open", res));
  const send = (method, params = {}) =>
    new Promise((res) => {
      const myId = ++id;
      pending.set(myId, res);
      ws.send(JSON.stringify({ id: myId, method, params }));
    });
  return { ready, send, close: () => ws.close() };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const t = await cdpTarget();
const c = conn(t.webSocketDebuggerUrl);
await c.ready;
await c.send("Page.enable");
await c.send("Runtime.enable");
await c.send("Page.navigate", { url });

// Poll until the HUD no longer says "buffering…" (or timeout), then settle.
const deadline = Date.now() + 45000;
let buffering = true;
while (Date.now() < deadline) {
  await sleep(300);
  // Ready = the HUD clock is populated ("frame N/…") AND not buffering.
  // An empty DOM (app still booting) lacks "buffering" too, so checking only
  // for its absence fires too early — require the clock text to be present.
  const r = await c.send("Runtime.evaluate", {
    expression:
      "(t=>t.includes('frame')&&!t.includes('buffering'))(document.body.innerText)",
    returnByValue: true,
  });
  buffering = r?.result?.value !== true;
  if (!buffering) break;
}
await sleep(extraSettle); // let the shadow bake + a few clean rAFs land

const shot = await c.send("Page.captureScreenshot", { format: "png" });
const fs = await import("node:fs");
fs.writeFileSync(outPng, Buffer.from(shot.data, "base64"));
console.log(`${buffering ? "TIMED-OUT-buffering" : "ok"} ${outPng}`);
c.close();
process.exit(0);
