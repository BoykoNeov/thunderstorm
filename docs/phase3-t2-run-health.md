# Phase 3 T2 — supercell run health + bbox gate

**Status: T2 COMPLETE** (2026-07-22). All four analysis pieces PASS (deck gate, bbox,
peak-|w|, run-health), the web export finished clean at 15:34 (1.557 GB, 601 frames), and
the package ships as the project's **first web-only package** — owner decision on the
tracked contract taken and applied. Committed and pushed (`c898eb8`, `7200970`).
Carried items in §7. **Next: T3** (cref orientation discharge) — needs the diorama on a
real GPU; use frame 525 or 600, never 450 (§4.4).
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
crashed on an f-string; the per-frame data is decisive.)

**AUTHORITATIVE (export-web pass 1, all 601 frames, 2026-07-22):**
**`w: observed −53.20 .. +66.33 m/s`** → **|w| = 66.33, margin 13.67 m/s under the
±80 scale.** The pre-scan's 62.64 was a *sampled* peak and undershot the true maximum
by 3.7 m/s — which is exactly why the gate is the exporter's own full sweep and not a
scratch script: a sampled scan can only ever be a lower bound on a maximum.

Two other pass-1 numbers worth keeping:
- `qmax: cloud=0.009069  ice=0.009691  rain=0.0105  graupelhail=0.01731  dbz=75.44`
- `cref: observed +0.00 .. +75.44 dBZ` — **identical to the `dbz` qmax (75.44)**, so
  T5's standing per-scenario re-check of the `cref ≡ colmax(dbz)` identity passes on a
  *supercell* (it was originally measured on the Phase 1 pulse cell). That identity is
  what licenses the plan view borrowing the dbz channel's vmax and palette.

This is same-family-consistent: Phase 0 (Morrison, 1 km) peaked 60.6 m/s; 333 m + NSSL
sits in the same band (cf. single_cell 53→67.5 at 333 m).

## 4. Run-health / same-FAMILY check — PASS ✅ (2026-07-22)

**Qualitative verdict, NOT a numeric match** (NSSL/333 m legitimately exceeds Phase 0,
so a numeric gate would false-fail). Signature to confirm: single core → two
**separated** cores → **counter-rotating** pair. **All three confirmed.**

Reference (Phase 0, docs/phase0-validation.md): split underway ~40 min; two separated
cores 17.9 km apart at 75 min; counter-rotating |ζ| ≈ 0.022–0.029 s⁻¹.

### 4.1 Separation — PASS (`scratch_health.py`, log in `runs/supercell333/`)

Column-max `winterp` ≥ 10 m/s connected components. Two strong cores, separation
**monotonically increasing**, both movers staying vigorous for the full 2 h:

| t (min) | 45 | 60 | 75 | 90 | 105 | 120 |
|---|---|---|---|---|---|---|
| separation (km) | 10.0 | 12.0 | 19.4 | 26.1 | 35.5 | 46.2 |
| core 1 peak w | 54.4 | 60.4 | 58.9 | 57.0 | 60.5 | 57.1 |
| core 2 peak w | 25.0 | 34.4 | 56.2 | 51.3 | 49.4 | 54.6 |

19.4 km at 75 min vs Phase 0's 17.9 km — the same split at the same time.

### 4.2 Rotation — the instrument had to be replaced (this is the finding)

**`scratch_health.py`'s per-core sign flag is NOT trustworthy and its verdict line
should be ignored.** It scores a core by the **mean** `zvort` over the whole component;
a 2000-cell component contains both signs of the vorticity couplet, so the mean is a
near-cancellation — it reports |ζ| ~0.002 s⁻¹ where the component **extrema** are
±0.05–0.07 s⁻¹, a ~20× washout. It printed `counter-rotating: False` at t=60 and t=105.
That flag is an artifact. Three statistics on the same components (mean,
extremum-dominance, value at the peak-w column) **disagree with each other frame to
frame** — which is itself the proof that no single statistic on a large blob settles
the question.

**CM1's own `uh` cannot settle it either:** measured `min(uh) = +0.0` over the entire
domain in all 7 sampled frames — CM1's updraft helicity is **clipped at zero**, so it
marks "rotating updraft present" but is blind to anticyclonic rotation. (Clipped, not
magnitude: if it were |·| its t=45 max would be 2050.8, the |negative| peak; it is
1552.1, the positive one.)

**Instrument used instead — signed updraft helicity**, computed in
`M:\claud_projects\temp\probe_uh_signed.py`:
`SUH = ∫(2–5 km) w·ζ dz, w>0 only`. Weighting ζ by `w` is exactly what defeats the
washout: surrounding air of opposite sign has no updraft, so it cannot cancel the core.
**Self-validating:** its positive extremum reproduces CM1's `uh` maximum *to the printed
digit* in 6 of 7 frames (1567.8 / 1552.1 / 1119.6 / 1215.1 / 1226.2 / 1882.1), which
both confirms the implementation against CM1's own code and is what proves the clipping.

**Result — a persistent ANTICYCLONIC centre, monotonically NW-drifting:**

| t (min) | 30 | 45 | 60 | 75 | 90 | 105 | 120 |
|---|---|---|---|---|---|---|---|
| SUH min (m²/s²) | −1632 | −2051 | −1750 | −1134 | −1302 | −1288 | −1674 |
| location (km) | (−8.5,+8.2) | (−10.2,+12.5) | (−14.2,+17.8) | (−16.8,+22.1) | (−22.5,+26.8) | (−26.5,+30.5) | (−26.1,+36.5) |

Counter-rotation **confirmed**: a strong, coherent, continuously-tracked anticyclonic
left mover alongside the cyclonic right mover. It also explains the t=60/75 confusion —
the domain-wide *positive* SUH max sits at (−9.8,+14.5)/(−13.2,+18.2), i.e. on the left
mover's **cyclonic flank**, the other half of its couplet, rather than at the right mover.

### 4.3 Mover locations — the asset T3 consumes

Left mover **NW-drifting** (−x, +y), right mover held near origin **because the domain
moves with it** (`imove=1` at the Bunkers right-mover velocity — so "stays near centre"
is the moving frame working, not the storm sitting still):

| t (min) | left mover (km) | right mover (km) |
|---|---|---|
| 45 | (+4.2, +9.8) | (−5.7, +8.3) |
| 75 | (−10.2, +21.2) | (−5.6, +2.4) |
| 90 | (−12.6, +24.6) | (−5.4, −0.6) |
| 105 | (−17.5, +28.5) | (−2.5, −3.6) |
| 120 | (−14.4, +36.2) | (−0.7, −7.9) |

Note the two instruments' centroids agree closely in **y** but differ by up to ~12 km in
**x** at t=120 (winterp −14.4 vs SUH −26.1): an updraft centroid and a rotation centre
are not the same point. The N–S separation is instrument-robust; the E–W one is soft.
Which is why the asset below is measured in **neither** of these fields.

### 4.4 T3 orientation asset — measured in `cref`, the field T3 renders

The T3 test detects an **x↔y transpose** in the `cref` plan view. `cref` is unsigned
reflectivity and a transpose is purely **spatial**, so rotation sign — however well
established above — is *not* what T3 checks, and neither `w` nor `ζ` is the right place
to characterise the asset (advisor). Measured directly in the shipped bricks
(`M:\claud_projects\temp\probe_cref_asset.py`, gunzip → decode → `reshape(ny, nx)`, i.e.
exactly the consumer path), cores ≥ 45 dBZ:

| frame | t | cores ≥45 dBZ | Δx (km) | Δy (km) | Δy/Δx |
|---|---|---|---|---|---|
| 450 | 90 min | **1** (still merged) | — | — | — |
| 525 | 105 min | 2 | 4.03 | 26.30 | **6.5** |
| 600 | 120 min | 4 (2 dominant) | 7.54 | 34.24 | **4.5** |

Frame 600 cores: **(+0.58, −1.17) km @ 74.3 dBZ** and **(−6.96, +33.07) km @ 69.1 dBZ**.

**Usable for T3, with one constraint: use a LATE frame.** At t=90 the two cells are still
one connected ≥45 dBZ mass — the split is visible in `w` long before it separates in
reflectivity, so an orientation test run on frame 450 would have nothing to orient.
Frames 525 and 600 both give a clean 4.5–6.5:1 N–S-dominant pair, which is what makes a
transpose detectable by eye and by pixel test — the failure mode T9 could not test on a
radially symmetric pulse cell. (Supersedes both the T1 note's L→(−11.3,+21.9),
R→(+7.2,+13.4) and the §4.3 w-derived figures; those measure other fields.)

Whole-field ≥45 dBZ spread is also y-dominant but only ~1.5:1 (std x 34.2 vs y 52.8
cells at frame 600) — so T3 should test the **two-core separation**, not a bulk moment.

## 5. Web export — DONE ✅ (2026-07-22 15:34 EEST, rc=0, 8004 s)

**Result:** `/home/boiko/thunderstorm/export/supercell333/web` — **1.557 GB**, 601 frames
× 4 files (`rgba`/`dbz`/`w`/`cref`, all 601 present) + `web_manifest.json` (151 641 B).
**PEAK rgba = 4.24 MB @ frame 600.** (The SVT 30–50 MB/frame budget does not bind here —
this is the web brick path, and the owner's web-only decision means no VDB ships this
phase. The peak is recorded because it is the decimation-budget figure the manifest
carries, and because frame 600 being the peak is consistent with the bbox gate's
peak-active frame 600.)

### Relaunch history (2026-07-22)

- **Two earlier attempts were killed by the vjoy BSOD** (see `[[vjoy-driver-bsod-2026-07-22]]`;
  unrelated to the export — a `find /` in another project). Both left an empty `web/`
  and a log containing only the bash start line, with **no partial output to corrupt**,
  so the relaunch is a clean slate.
- **`python3 -u` added to the driver.** Without it python block-buffers stdout when
  redirected to a file, so pass 1's every-60-frames progress line does not reach the log
  for many minutes — a *healthy* run then looks byte-identical to one that died at
  startup (start line + empty `web/`), which is exactly what made the killed attempts'
  state unreadable. This is the difference between "verify existence" and "verify
  progress"; only the latter distinguishes a live run from a dead one.
- Driver: `M:\claud_projects\temp\run_exportweb_supercell.sh` (LF-clean), launched via
  `Start-Process` so it survives the session. Pass 1 confirmed progressing at
  **0.77 s/frame** (~8 min for the 601-frame maxima scan).
- Output → WSL ext4 `/home/boiko/thunderstorm/export/supercell333/web`; log
  `.../exportweb.log`. Two full 601-frame passes (maxima scan, then encode).
- **When done:** copy the package to `scenarios/supercell_333m/web/`, then the
  `web_manifest.json` / `manifest.json` per the data policy (payload out of git history,
  `manifest.json` tracked). Estimate ~1.5–2 GB web (540×540×54, 601 frames).

## 6. Remaining checklist to close T2

- [x] export-web finishes; record authoritative `observed w:` range + peak rgba MB/frame — §5
- [x] run-health same-family verdict + mover locations — §4 **PASS** (note: `scratch_health.py`'s
      own sign flag is unusable; the verdict rests on signed UH, §4.2)
- [x] T3 orientation asset characterised in `cref` — §4.4 (use frame 525 or 600, not 450)
- [x] copy web package → `scenarios/supercell_333m/web/`; diorama picker lists it.
      **Copy verified, not assumed:** 2405 files (601 × `.rgba/.dbz/.w/.cref` + the
      manifest), 1.45 GiB, and **5/5 sampled MD5s identical** to the WSL source across all
      four field types. (`robocopy` exits **1** on success — "files were copied"; only
      ≥8 is a failure. A harness that reads nonzero as failure will call a good copy bad,
      which is why the check is hashes and counts rather than the exit code.)
      **Served, not just present:** the dev server enumerated it as
      `supercell_333m 540×540×54 @ 333 m, 601 frames` alongside the two single-cell
      packages, and `/data/supercell_333m/f0600.{cref,rgba,w}.gz` all returned HTTP 200
      with byte counts matching disk — `f0600.rgba.gz` at 4 239 411 B independently
      confirming §5's 4.24 MB peak-rgba frame. (An actual *render* of this package is
      T3's job, on a real GPU per the standing rule.)
- [x] **web-only tracked-contract question — RESOLVED by the owner 2026-07-22:
      track `web/web_manifest.json`.** A web-only package ships **no** top-level
      `manifest.json`. Reason it is not merely "the cheap option": `manifest.build()` is
      SVT-shaped — its `frames` list is per-**VDB**-file `{file, bytes}`, alongside
      `SVT_TEXTURE_MAP` and `ue_placement_rule` — so synthesising one for a package with
      no VDB would advertise an SVT payload that is not in the package. That is the same
      class of error as T2's census-in-prose and T5's run-specific-numbers-in-a-generic-
      builder: a contract file asserting something untrue about what ships. The web
      manifest is already a real versioned contract (`web_format_version` 1.2) and the
      diorama already refuses a newer major (`volume.ts SUPPORTED_MAJOR`), so tracking it
      keeps "the contract is version-controlled" true without inventing anything.
      **Ignore-rule mechanics (the part that bites):** the rule had to change from
      `scenarios/**/web/` to `scenarios/**/web/*`. Git does **not descend into an excluded
      directory**, so with the directory form a `!…/web/web_manifest.json` negation is
      unreachable and the file is silently untrackable — it would have looked like the
      policy was applied while nothing was actually tracked. Verified with
      `git check-ignore`: manifests TRACKABLE, `f0000.rgba.gz` IGNORED.
      Side-effect, kept deliberately: the two `single_cell_*` packages' web manifests
      become tracked too, so all three packages get a versioned web contract.
- [x] commit + push (package manifest tracked, payload ignored) — `c898eb8`, `7200970`

## 7. Carried items out of T2

**(a) The tracking-scope call, made deliberately.** The owner's decision was scoped to
the *web-only* package, but git cannot express "track `web_manifest.json` only where
`manifest.json` is absent" — a glob has no such predicate. The choice was a global rule
or an explicit per-scenario negation (`!scenarios/supercell_333m/web/web_manifest.json`)
that would need editing for every future scenario and would rot silently when someone
forgot. **Kept global**, so all three packages get a versioned web contract and the rule
has no per-scenario exceptions to maintain.

**(b) `web_manifest.json` is tracked WITHOUT a reproduction gate — the real cost of (a).**
`manifest.json` earned its tracking *because* `test_manifest.py` rebuilds it byte-for-byte
from committed files alone; that is this project's stated principle — a tracked contract
has a gate. The web manifest now rides in tracked with no equivalent, so a future
`webvol.write_manifest` edit could silently stale all three tracked copies and no suite
would fail. **This is a genuine asymmetry, not a nit.** It looks fixable by T2's own
trick: feed `webvol.write_manifest` the shipped manifest's own `frames` list (the same
way `test_manifest.py` feeds `manifest.build`) and demand byte-identity. **Carry to T7
close-out** — not done here, and deliberately not started, because the ask was to restart
the run and T2 is complete.

**(c) Fresh-clone picker lists data-less scenarios.** The dev server enumerates any
subdir carrying `web/web_manifest.json`; that file is now in git for all three while the
bricks are not, so a fresh clone advertises three scenarios whose data 404s until
re-export. **Mild, and partly pre-existing:** a fresh clone has no bricks for *any*
package, so the viewer was already broken there without a re-export — the change turns
"silently absent" into "listed, then 404". Arguably the better diagnostic; a friendly
"package not exported yet" state in the picker is a viewer nicety for later, not a T2 fix.

**(d) Manifest provenance gap (pre-existing, owner-pending).** This package, like both
single-cell ones, omits inline CM1 sha256 / rank count / domain decomposition. The
recovery path is nonetheless intact: `sim/scenarios/supercell_333m.json` and the deck
generator *are* in git, and the deck is the sole scenario input at `isnd=5`.
