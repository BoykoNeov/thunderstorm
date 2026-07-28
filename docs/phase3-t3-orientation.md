# Phase 3 T3 — the cref orientation test, discharged

**Status: T3 COMPLETE** (2026-07-28). The composite-reflectivity plan view is
verified un-transposed **end to end** — CM1's own netCDF → shipped brick → rendered
pixels — on the split supercell, with the transposed hypothesis rejected by
**42.9–59.1 km** (pipeline link) and **284–331 px** (render link). This discharges
the carried note Phase 2 T9 recorded at `docs/phase2-plan-2026-07-20.md` §19.6, and
leaves behind a **committed** gate (`pipeline/tests/test_orientation_t3.py`, 8/8) for
the half of the claim that can be re-run without a 218 GB run directory.

Scenario `supercell_333m`, frames **525** (t=105 min) and **600** (t=120 min) — never
450, per the T2 asset note (§4.4 of `docs/phase3-t2-run-health.md`: at t=90 the two
cells are still one connected ≥45 dBZ mass and there is nothing to orient).

## 1. What was owed, and why the obvious test could not pay it

T9 shipped `cref` and said so plainly: **orientation was earned from the write
convention, not from the capture.** The Phase 1 pulse cell was centred and
near-axisymmetric, so an x↔y transpose was *pixel-identical*; the independent test
was deferred to "the Phase 3 asymmetric asset".

The trap to avoid when finally paying it (advisor, before any code was written): the
cref shader's footprint mapping

```glsl
vec2 fuv = (pG.xy - uBoxMin.xy) / (uBoxMax.xy - uBoxMin.xy);
```

is the volume's **own** `uvw.xy` expression. So cref is transpose-consistent with the
hydrometeor and dbz layers *by construction*, and any check of the form "the echo sits
under the storm core" or "it agrees with the dbz MIP" **cannot fail** — that is the
corroboration T9 already ran and already labelled non-discriminating. A real test has
to compare the render against an **external absolute reference**, never against
another layer of the same viewer.

Three external references exist. All three were used.

| # | Reference | Closes |
|---|---|---|
| A | CM1's netCDF with its **own** `xh`/`yh` coordinate variables | pipeline link (CM1 → brick) |
| B | The viewer's own projection math applied to A's coordinates, vs measured pixels | render link (brick → screen) |
| C | The physics: a westerly-sheared splitter in a Bunkers right-mover frame | corroboration that survives without either |

## 2. Link A — CM1 netCDF vs the shipped brick

`M:\claud_projects\temp\t3_probe_nc_vs_brick.py`, run in WSL against
`/home/boiko/thunderstorm/runs/supercell333` (602 `.nc` files, 218 GB, intact) and
`scenarios/supercell_333m/web`.

Ground truth is read as CM1 writes it: variable `cref`, dims `('time', 'yh', 'xh')`,
positions from `xh`/`yh` (units km) — **not** from any pipeline constant. The brick is
read through the exact consumer path (gunzip → `reshape(ny, nx)` → linear-uint8
decode). Cores are ≥45 dBZ connected components ≥20 cells, reflectivity-weighted
centroids.

**The axis check is on dimension NAMES, not axis lengths.** This domain is 540×540:
a shape check cannot tell `(yh, xh)` from `(xh, yh)` and would pass a transposed file
silently. Same class of blindness as the symmetric storm — one level up.

| frame | core | CM1 netCDF (km) | shipped brick (km) | offset |
|---|---|---|---|---|
| 525 | 69.6 dBZ | (−5.02, +27.51) | (−5.03, +27.52) | 15 m |
| 525 | 73.8 dBZ | (−0.96, +1.25) | (−1.00, +1.22) | 47 m |
| 600 | 69.1 dBZ | (−6.95, +33.07) | (−6.96, +33.07) | 13 m |
| 600 | 74.4 dBZ | (+0.61, −1.15) | (+0.58, −1.17) | 43 m |

**Discriminator = the core-to-core separation VECTOR**, not per-core distance:

| frame | truth separation | brick separation | error | error if transposed |
|---|---|---|---|---|
| 525 | (−4.06, +26.27) km | (−4.03, +26.30) km | **0.043 km** | **42.889 km** |
| 600 | (−7.57, +34.22) km | (−7.54, +34.24) km | **0.032 km** | **59.086 km** |

**A core near the origin cannot discriminate** — it sits on the mirror line, so a
transpose barely moves it (the 600 right mover shifts only 2.5 km, the 525 one 3.1 km,
while the off-axis left movers shift 33.0 and 29.2 km). The first draft of this probe
demanded that *both* cores move and reported FAIL on correct data. The criterion was
wrong, not the data. This is why the gate is the separation vector plus the **off-axis**
core, and it is the same geometric fact that later makes the near-origin core's
render-side transpose displacement a harmless 7.8 px.

## 3. Link B — the brick vs the rendered pixels, on a real GPU

Standing rule (Phase 1's most expensive lesson, Phase 2 §11): an "it renders" claim
comes from a real GPU. Headless Chrome over CDP, HUD polled until a frame is streamed
and not buffering (`M:\claud_projects\temp\t3-drive.mjs`, the `tools/shot.mjs`
discipline plus the page geometry the test needs).

Captures — both `layer=cref`, `el=78`, `d=300`, `sx=1`, `ts=0&fxaa=0&acc=0&precip=0`,
1578×802 CSS px at dpr 1 (canvas == drawing buffer == PNG):

- `frame=600&az=45` → `t3_cref_f600.png`
- `frame=525&az=20` → `t3_cref_f525_az20.png`

**Prediction runs through the viewer's own code.** A probe importing `src/camera.ts`,
`src/mat.ts` and `src/scene.ts` (the 5c scale-bar trick: verify against the render's
own view-projection by an independent path) inverts the shader's `fuv` mapping to place
a CM1 coordinate in scene km, projects it, and converts NDC to pixels. Predicted
*versus* measured is then a pure number.

**Measurement** (`M:\claud_projects\temp\t3_measure_capture.py`): magenta→white is the
only ≥65 dBZ colour on the platter (`R>0.8 & B>0.8`, DOM overlays cropped away), so
blobs are labelled and centroided in pixels, and the *same* ≥65 dBZ mask is applied to
the brick so the comparison is like-for-like.

**Azimuth is pinned, and the screen basis is established with chirality.** A transpose
is a *reflection*; a 90° camera rotation is a *rotation*; two points give one vector and
cannot separate them. Projecting (0,0), (+20 km, 0) and (0, +20 km) fixes both:

| capture | +20 km EAST | +20 km NORTH | chirality | scale |
|---|---|---|---|---|
| f600, az=45 | (−61.7, +60.4) px | (+61.7, +60.4) px | CCW | 43.0 px / 10 km |
| f525, az=20 | (−30.0, +80.5) px | (+81.6, +29.1) px | CCW | 42.7 px / 10 km |

az=45 makes a transpose *exactly* a horizontal mirror; az=20 is the general case. Both
were captured for that reason.

### Result

| capture | core (km) | predicted px | measured px | residual | transposed prediction is |
|---|---|---|---|---|---|
| f600 az=45 | (−0.86, −7.56) | (768.6, 379.1) | (767.8, 378.9) | **0.8 px** | 41.6 px away |
| f600 az=45 | (−15.96, +37.57) | (954.4, 469.5) | (954.3, 468.9) | **0.6 px** | **330.7 px** away |
| f525 az=20 | (−3.12, −4.20) | (776.6, 385.7) | (775.8, 387.0) | **1.5 px** | 7.8 px away |
| f525 az=20 | (−18.95, +27.39) | (927.5, 368.6) | (929.2, 370.7) | **2.7 px** | **284.0 px** away |

Worst residual **2.7 px ≈ 0.63 km**, on a 179.8 km-wide domain. The off-axis core —
the one that discriminates — is off by **0.6–2.7 px** where a transpose would put it
**284–331 px** away.

Two honesty notes on the method:

- **Both sides are clustered before matching.** Frame 525's truth has four ≥65 dBZ
  components; two of them are 5 km apart and the render merges them into one magenta
  blob (the pixel mask thresholds a colour already alpha-blended with the ground, so it
  is slightly more generous than the brick's exact ≥65). Matching the small component
  against the merged centroid produced an 18.5 px "error" that is a **matching
  artifact, not a placement error**. Clustering both sides on the same neighbourhood
  (8 km / 40 px) removes it; the per-core figures are printed alongside so nothing is
  hidden by the clustering.
- **Terrain parallax is inside the residual.** The prediction intersects the ground at
  z = 0; the ray actually hits the decorative terrain at z = h, displacing the sample
  by h/tan(78°) ≈ 0.21 h. At staging relief of a few hundred metres that is ~0.1 km —
  below the residual, and it is one of the reasons the residual is not zero.

### The physics anchor (reference C)

The render shows the pair separated overwhelmingly **north–south** (Δ = (−7.6, +34.2) km
at frame 600, 4.5:1), with the northern member the one T2 identified as the
anticyclonic left mover. That is what a splitting storm in unidirectional westerly
shear (`iwnd=2`), viewed in a frame moving with the Bunkers right mover (`imove=1`),
*must* show: the movers diverge across the shear vector. A transposed render would put
the separation east–west. This anchor routes through neither the pipeline nor the
viewer and would survive the raw run being deleted — but it is a 4.5:1 dominance, not a
sign test, so it corroborates A and B rather than replacing them.

## 4. The committed half — `pipeline/tests/test_orientation_t3.py` (11/11)

Links A and B are **one-shots**: they read a 218 GB run directory and a 1.5 GB web
package, neither in git. What *can* be committed is the thing T9's argument was
actually about — the write convention — exercised through the production functions on
a fixture that fits in a test file.

Five gates, six negative controls:

- **plan brick**: a hot cell at CM1 (x_i, y_j) writes flat byte index `j*nx + i`, via
  `regrid.build_query_2d` → `resample_dbz_2d` → `encode_linear_u8` → `write_frame` →
  gunzip. The assertion is on the **flat byte index**, not the numpy array's look: the
  viewer uploads these bytes into a width=`nx` texture, so an array that reads right in
  numpy but ravels the other way still renders transposed. The **production** query
  builder is used deliberately — writing a query in the test would test the test's own
  meshgrid order.
- **volume brick**: the same cell writes `(k*ny + j)*nx + i`.
- **plan and volume recover the same (i, j)** — stated as a relationship, because that
  identity is exactly what licenses the viewer sharing one `fuv` expression between the
  cref plane and the volume. If the two bricks ever diverged, the plan view would be
  transposed relative to the cloud drawn above it and nothing in the viewer would
  notice.
- **the manifest's `dims` key matches the bytes actually written** — reads the tracked
  `supercell_333m/web/web_manifest.json` (a dividend of T2's tracked-web-manifest
  decision: a committed test can now read a real contract file), derives the axis order
  from where the hot byte landed, and requires the declaration to equal it.
- **the tracked contract is still what the code emits** — rebuilds the orientation
  fields with `webvol.build_manifest` (a pure function of scenario/frames/qmax, so T2's
  feed-the-shipped-numbers-back trick applies) and demands equality with the shipped
  file.

**Why the fourth gate checks `dims` and not the layout prose** (advisor, post-commit —
the first version asserted `"x fastest" in layout`). That form fires only if the phrase
goes *missing*: flip the pipeline to y-fastest and forget to update the string, and it
passes on a stale contract — the precise hazard T2 carried as item (b). Worse, the prose
it was checking is itself ambiguous:

```
plan_fields.cref.layout = 'uint8 R, x fastest then y -- a (NX, NY) 2D plane...'
```

`(NX, NY)` is the texture's (width, height), which is how the viewer uploads it — but
read as an **array shape** it is the transpose of the `reshape(ny, nx)` that every
consumer actually performs, and on a 540×540 package a misread produces no crash, just a
silently transposed map. The volume block carries no tuple at all, and the asymmetry
between the two strings is the smell. The block already carries the unambiguous,
machine-readable `"dims": ["y", "x"]`, so **that** is what the gate acts on, with the
fifth gate pinning the prose to its generator so it cannot drift unnoticed. Rewording
the tuple itself would stale all three tracked web manifests with no regeneration path
inside T3's budget — it belongs with T2 carried item (b) at T7, and is recorded there.

Controls: a transposed plane, a y-flipped plane (same shape, same ravel order, mirrored
map — nothing about file size or channel count reveals it), a query built x-major (the
realistic upstream mistake — `build_query_2d`'s meshgrid order is one word away from
producing (x, y) pairs against a (y, x) field), a one-word drift between code and
shipped contract, and a transposed `dims` declaration (which the substring form would
have waved through, since `"x fastest"` is still present in it).

**The fourth control is about the fixture itself.** The fixture is **7×5 with the hot
cell off-diagonal**, and the control demonstrates why: on a square grid with a diagonal
feature, the transposed array is byte-identical and the transpose control **stops
firing**. That is T9's trap reproduced deliberately at test scale — *a fixture can mask
a failure mode exactly the way a symmetric storm can*. Without this control, a future
tidy-up to a square fixture would silently defang the file.

## 5. What is discharged — and what is not

**Discharged:** Phase 2 T9's carried note. The cref plan view's orientation is now
earned from measurement, not only from the write convention, and the convention itself
has a permanent gate.

**NOT discharged, unchanged by this task:**

- **The Y-flip (Phase 1 carried item #1)** stays deferred with the UE app, exactly as
  `docs/phase3-plan-2026-07-20.md` §2.4 framed it. It gates UE placement code
  (`scale.y = -100`); this phase ships no placement code. The asymmetric asset was
  never going to discharge it, and did not.
- The owner-owed **UE SVT visual streaming sign-off** and the **diorama 5c pan-gesture
  sign-off** are untouched.
- **T2 carried item (b)** — `web_manifest.json` tracked without a *full* reproduction
  gate — is **narrowed, not closed**, and still due at T7. What T3 added is that gate in
  miniature: the fields that declare orientation are now pinned to `build_manifest`'s
  output. The rest of the document still has no gate.
- **The `(NX, NY)` prose tuple in the cref layout string** is left as-is, deliberately
  (§4): rewording it stales all three tracked web manifests, and the regeneration path
  that would fix it *is* carried item (b). Carried to T7 with it.

**Scope note on Link B's mask:** the render comparison is made at ≥65 dBZ, because
magenta→white is the only colour on the platter that a threshold can isolate
unambiguously. The ≥45 dBZ envelope is not compared pixel-wise — it extends past the
110 km staging platter (`land.ts GROUND_HALF = 55` km) on a 179.8 km domain, so its
outer contour is clipped by the toy landscape and is not a well-defined measurement
target. Both cores, and all four of frame 525's components, sit well inside the platter.

## 6. Artifacts

| Path | What |
|---|---|
| `pipeline/tests/test_orientation_t3.py` | the committed gate (8/8) |
| `docs/phase3-t3-orientation.md` | this doc |
| `M:\claud_projects\temp\t3_probe_nc_vs_brick.py` | Link A (WSL, needs the raw run) |
| `M:\claud_projects\temp\t3_measure_capture.py` | Link B measurement (brick ≥65 cores + PNG blobs) |
| `M:\claud_projects\temp\t3-drive.mjs` | capture driver (CDP, HUD-polled, leak-safe) |
| `M:\claud_projects\temp\t3_cref_f600.png`, `t3_cref_f525_az20.png` | the two captures |

The node-side prediction probe lived at `diorama/test/t3orient.probe.test.ts` during the
task and was **deleted**, deliberately: its measured-pixel inputs are constants from a
past capture, so committing it would add a test that passes no matter what the viewer
later does — a gate that cannot fail is worse than none.

Suites after T3: pipeline **8 files, all exit 0** — checked on the **exit code**, not on
each file's self-reported tally, because `python3 "$t" | tail -1` discards the status and
a file that dies part-way can still print a cheerful last line (advisor). test_deck 15,
test_manifest 17, test_orientation_t3 11, test_regrid_cref 13, test_regrid_dbz 3,
test_regrid_w 10, test_scenario_t6 11, test_supercell_t2 10. **One documented skip:**
`test_regrid_dbz.py` runs 3 synthetic gates by default and prints
`real-frame gates SKIPPED (pass --run-dir to run them)` — the 10/10 the charter records
for Phase 2 T3 is the `--run-dir` figure, so "3/3" here is the skip, not a regression.
Diorama **128/128**, `tsc --noEmit` clean.
