import { defineConfig, type Plugin } from "vite";
import fs from "node:fs";
import path from "node:path";

// Scenario data is NOT in git (data policy: packages live outside plain git).
// The dev server maps /data/* onto the scenario package's web/ folder on disk.
// Frames are served as opaque gzipped bytes (no Content-Encoding header) — the
// viewer decompresses explicitly with DecompressionStream, so nothing here
// depends on transport negotiation.
const DATA_DIR = path.resolve(import.meta.dirname, "../scenarios/single_cell_500m/web");

function serveScenarioData(): Plugin {
  return {
    name: "serve-scenario-data",
    configureServer(server) {
      server.middlewares.use("/data", (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const p = path.normalize(path.join(DATA_DIR, rel));
        if (!p.startsWith(DATA_DIR) || !fs.existsSync(p) || !fs.statSync(p).isFile()) {
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
