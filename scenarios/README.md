# scenarios/

Finished scenario packages. A package is a **versioned contract**:

- VDB volume sequence (cloud/ice/rain/graupel-hail/dBZ channels, matched transforms,
  fixed padded bounding box across all frames)
- `web/` — the Storm Diorama web export of the same volumes (gzipped quantized
  uint8 bricks + `web_manifest.json`), served by `diorama/`
- surface-layer textures (qr/qg near-surface stack driving Niagara particles)
- skew-T / hodograph plot images (rendered in the pipeline with MetPy/matplotlib)
- lightning event list (positions / times / polarity)
- `manifest.json` carrying `format_version` (UE refuses newer major versions) and a
  `web` block **pointing at** the rendition above — the package is self-describing.
  The pointer deliberately copies no grid/frame/byte figures: `web/` is gitignored and
  regenerable, so a copy would be false on a fresh clone, while `web_manifest.json`
  stays authoritative. Nothing duplicated, nothing to drift.

The last three ship from Phase 2/4; the first three exist today.

## Storage — RESOLVED 2026-07-20 (owner): in-tree, out of git history

The charter's open "LFS vs out-of-repo" item is closed. **Neither, strictly:**

- Packages live **here**, in `scenarios/<name>/`, inside the project folder — so the
  repo, the diorama dev server and the UE project all see one path with no env
  wiring, and `diorama/vite.config.ts` needs no change.
- The **payload is out of git history**, not out of the folder. `.gitignore` drops
  `*.vdb`, `scenarios/**/web/` and the image/frame globs; nothing >10 MB enters
  plain git. **Git LFS is not used anywhere in this repo.**
- `manifest.json` **is tracked** (via the `!scenarios/**/manifest.json` negation).
  This is deliberate and load-bearing: the manifest is the versioned contract UE
  checks `format_version` against, and a contract that isn't version-controlled
  isn't a contract. It is ~48 KB for a 301-frame package and diffs meaningfully.
  Second dividend, since T2: `pipeline/tests/test_manifest.py` can rebuild the shipped
  manifest and compare it byte-for-byte from **committed files alone** — no CM1, no
  WSL, no netCDF — because `manifest.build()` is a pure function of (Scenario, frames,
  provenance). An edit that silently perturbs the contract fails there, not in UE.

**Consequence — packages are NOT backed up by git.** They are regenerable from
`sim/` + `pipeline/` (this one: 7.5 min from CM1 netCDF), which is the intended
recovery path; the raw netCDF behind it is itself disposable by design. If a package
ever becomes expensive to regenerate, that assumption needs revisiting.

## What ships today

`single_cell_500m/` — Phase 1 spike package, 525 MB: `manifest.json` (tracked) +
`vdb/` 301 frames, 437 MB (ignored) + `web/` 603 files, 86 MB (ignored). Source run
`/home/boiko/thunderstorm/runs/singlecell` in WSL. Provenance, channel contract and
the UE placement rule are all inside `manifest.json`; see
`docs/phase1-task5-pipeline.md` for how it was built.

_Do not start a phase without explicit go from the owner._
