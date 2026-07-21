# Phase 3 T2 — supercell run health + bbox gate

**Status: IN PROGRESS** (paused mid-session 2026-07-22; export-web running detached).
Scenario `supercell_333m`, run `/home/boiko/thunderstorm/runs/supercell333` (601
output frames + 10 hourly restarts).

T2 has four pieces (advisor decomposition): **deck differential gate**, **run-health /
same-family check**, **bbox gate**, and **the web export** (T3's diorama consumes the
web package). Owner decision this task: **web-only, no VDB** (§4.2 confirmed
2026-07-22 — the anvil fills the 180 km domain, so a VDB would blow the 30–50 MB/frame
SVT budget for no consumer this phase; regenerable when UE returns).

## 1. Deck differential gate — DONE ✅

`pipeline/tests/test_supercell_t2.py` — **10/10 pass**. Full suite green
(test_deck/manifest/regrid_dbz/w/cref/scenario_t6/supercell_t2).

Differential vs `single_cell_333m` (same resolution isolates the change). Exactly **10
of 344 keys** differ, each classified into a declared category; the gate fails on any
unclassified key, and asserts the same-family invariants do NOT move:

| Category | Keys | Change |
|---|---|---|
| shear | `iwnd` | 0 → 2 (WK unidirectional shear — the supercell maker) |
| motion | `imove`, `umove`, `vmove` | 0→1, 0→12.5, 0→3.0 (Bunkers moving frame; **first positive `imove=1` exercise** in the project) |
| domain | `nx`, `ny`, `tot_x_len`, `tot_y_len` | 240→540 (+derived) — bigger domain to hold the split |
| timing | `timax` | 3600 → 7200 (2 h; the split fully develops) |
| restart | `rstfrq` | −3600 → 3600 (hourly restarts, Category-5 optional) |

**Same-family invariants asserted identical (14 keys):** `ptype`, `isnd`, `iinit`,
`irandp`, `icor`, `iorigin`, `dx`, `dy`, `dtl`, `tapfrq`, `nz`, `dz`, `ztop`,
`stretch_z`. This is what makes "differs from the pulse cell by shear + motion +
domain only, not microphysics/thermo/resolution" a *verified* statement.

## 2. bbox gate — PASS ✅ (from T1, `runs/supercell333/bbox_final.log`)

Box `540×540×54 @ 333 m` contains every frame: horizontal half-width 89.744 km vs box
89.910 km (margin +0.166 km); top 17.750 km vs 17.982 km (+0.232 km); peak-active
frame 600 (1.95M CM1 voxels).

**Honesty note (advisor):** the box is the **full centred domain** (89910 = full
half-width), so `bbox_center=(0,0)` is *trivially* static — the anvil fills the domain,
the box is symmetric because it's the whole domain, NOT because the storm is. The plan
anticipated a genuinely **off-origin** static-centre box (left-mover drift); that hard
case did **not** occur here. The real off-origin static-centre discipline still awaits
a scenario whose active union is off-origin (candidate: multicell T6) — **carry it**,
same shape as the T9→T3 orientation-test carry.

## 3. Peak-|w| gate — PASS ✅ (gates the ±80 m/s web encode scale)

The exported `w` field (`winterp`) must fit the fixed cross-scenario ±80 m/s scale
(T4 `contract.W_ENCODE_SCALE_M_S`) or `export-web` errors in pass 1. Full 601-frame
scan (`scratch_peakw.py`): mature-phase maxima ~57–63 m/s, minima ~−40 to −53 m/s;
sampled peak **wmax ≈ 62.64 @ frame 540 (t=108 min)**, **wmin ≈ −52.81 @ frame 390
(t=78 min)** → **|w| ≈ 63 m/s, a 17 m/s margin under 80.** (The scan's summary line
crashed on an f-string; the per-frame data is decisive. The **authoritative** exact
range is `export-web` pass-1's `observed w:` line — record it here when the export
finishes.)

This is same-family-consistent: Phase 0 (Morrison, 1 km) peaked 60.6 m/s; 333 m + NSSL
sits in the same band (cf. single_cell 53→67.5 at 333 m).

## 4. Run-health / same-FAMILY check — PENDING ⏳

**Qualitative verdict, NOT a numeric match** (NSSL/333 m legitimately exceeds Phase 0,
so a numeric gate would false-fail). Signature to confirm: single core → two
**separated** cores → **counter-rotating** pair.

- Analysis script **ready**: `/home/boiko/thunderstorm/scratch_health.py` (column-max
  `winterp` connected components at t=45/60/75/90/105/120 min; per-core mid-level
  `zvort` sign for cyclonic/anticyclonic; w-weighted centroids). Run **after** the
  export finishes to avoid HDD thrash; writes `runs/supercell333/scratch_health.log`.
- **Reference (Phase 0, docs/phase0-validation.md):** split underway ~40 min; two
  separated cores (17.9 km apart) at 75 min; counter-rotating |ζ| ≈ 0.022–0.029 s⁻¹.
- **T1 already observed** (config note): left mover NW-drifting, right mover near-centre,
  Bunkers umove/vmove verified; cores +55 / −50 m/s.
- **Capture the mover (x,y) LOCATIONS** — that asymmetric E-W/N-S placement is the asset
  **T3** consumes to detect an x↔y transpose in the cref plan view. (T1 note had
  L→(−11.3,+21.9), R→(+7.2,+13.4) km — confirm/record here.)

## 5. Web export — RUNNING ⏳ (detached, pid 501 at pause)

- Driver: `M:\claud_projects\temp\run_exportweb_supercell.sh` (LF-clean), launched via
  `Start-Process` so it survives the session.
- Output → WSL ext4 `/home/boiko/thunderstorm/export/supercell333/web`; log
  `.../exportweb.log`. Two full 601-frame passes (maxima scan, then encode).
- **When done:** copy the package to `scenarios/supercell_333m/web/`, then the
  `web_manifest.json` / `manifest.json` per the data policy (payload out of git history,
  `manifest.json` tracked). Estimate ~1.5–2 GB web (540×540×54, 601 frames).

## 6. Remaining checklist to close T2

- [ ] export-web finishes; record authoritative `observed w:` range + peak rgba MB/frame
- [ ] run `scratch_health.py`; write the same-family verdict + mover locations above
- [ ] copy web package → `scenarios/supercell_333m/web/`; verify diorama picker lists it
- [ ] run a full `export` (VDB) manifest? **NO** — web-only; but the package still needs
      a top-level `manifest.json`. Decide: does web-only ship `manifest.json` (tracked
      contract) or only `web_manifest.json`? (Check single_cell_333m — it has both; the
      VDB `export` writes `manifest.json`. For web-only, confirm the tracked-contract
      story.) **Owner-adjacent — resolve before committing the package.**
- [ ] commit + push (package manifest tracked, payload ignored)
