import { defineConfig, type Plugin } from "vite";
import fs from "node:fs";
import path from "node:path";
// The discovery list's wire format is ONE shape living in two files. Importing
// the viewer's interface here (rather than restating it) makes `tsc --noEmit`
// the thing that keeps them in agreement: if the picker starts needing a field,
// this server stops compiling until it emits it.
import type { ScenarioSummary } from "./src/scenario";

// Scenario data is NOT in git (data policy: package payloads live outside plain
// git). The dev server maps /data/<name>/* onto ../scenarios/<name>/web/* and
// exposes /scenarios.json so the viewer can populate its scenario picker (T7).
// Frames are served as opaque gzipped bytes (no Content-Encoding header) — the
// viewer decompresses explicitly with DecompressionStream, so nothing here
// depends on transport negotiation.
const SCENARIOS_ROOT = path.resolve(import.meta.dirname, "../scenarios");

// Scenario dir names in the URL: letters/digits/_-. only, and never a lone
// `.`/`..`. This is the ONLY sanitizer on the /data path — with slashes and
// traversal thus excluded, `<root>/<name>/web` is guaranteed under the root, so
// only per-file traversal in the remainder still needs the startsWith guard.
const SAFE_NAME = /^[A-Za-z0-9_.-]+$/;
const isSafeName = (s: string) => SAFE_NAME.test(s) && s !== "." && s !== "..";

// A scenario is any subdir carrying web/web_manifest.json. Enumerated per
// request (a readdir + a couple of small JSON reads) so a freshly exported
// package appears in the picker without restarting the server.
function listScenarios() {
  let names: string[] = [];
  try {
    names = fs.readdirSync(SCENARIOS_ROOT);
  } catch {
    return [];
  }
  const out: ScenarioSummary[] = [];
  for (const name of names.sort()) {
    if (!isSafeName(name)) continue;
    const mf = path.join(SCENARIOS_ROOT, name, "web", "web_manifest.json");
    try {
      if (!fs.statSync(mf).isFile()) continue;
      const m = JSON.parse(fs.readFileSync(mf, "utf8"));
      // source_run pairs a coarsened export with its parent (same CM1 run =
      // same storm, two detail levels); decimation_factor says which is which.
      // Both are forwarded raw and left undefined when absent, so "no coarse
      // sibling" stays distinguishable from "coarsened by a factor of 1".
      out.push({
        name,
        voxel_m: m.grid?.voxel_m ?? 0,
        nx: m.grid?.nx ?? 0,
        ny: m.grid?.ny ?? 0,
        nz: m.grid?.nz ?? 0,
        frames: Array.isArray(m.frames) ? m.frames.length : 0,
        source_run: typeof m.source_run === "string" ? m.source_run : undefined,
        source_voxel_m: m.grid?.source_voxel_m,
        decimation_factor: m.grid?.decimation_factor,
      });
    } catch {
      // not a readable scenario package — skip it silently
    }
  }
  return out;
}

function serveScenarioData(): Plugin {
  return {
    name: "serve-scenario-data",
    configureServer(server) {
      // discovery: the viewer fetches this once at startup to build its picker
      server.middlewares.use("/scenarios.json", (req, res, next) => {
        if ((req.url ?? "/").split("?")[0] !== "/") {
          next();
          return;
        }
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(listScenarios()));
      });
      // data: /data/<scenario>/<file...> -> scenarios/<scenario>/web/<file...>
      server.middlewares.use("/data", (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const [scenario, ...file] = rel.split("/").filter(Boolean);
        if (!scenario || file.length === 0 || !isSafeName(scenario)) {
          next();
          return;
        }
        const base = path.join(SCENARIOS_ROOT, scenario, "web");
        const p = path.normalize(path.join(base, ...file));
        // scenario is slash/traversal-free, so `base` is safely under the root;
        // this guard only has to stop traversal inside the file remainder.
        if (!p.startsWith(base + path.sep) || !fs.existsSync(p) || !fs.statSync(p).isFile()) {
          next();
          return;
        }
        res.setHeader(
          "Content-Type",
          p.endsWith(".json") ? "application/json" : "application/octet-stream",
        );
        fs.createReadStream(p).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [serveScenarioData()],
  server: { open: false },
});
