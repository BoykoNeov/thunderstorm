# Phase 1 — completion record (2026-07-20)

**Verdict: CLOSED.** The de-risking spike did its job, including failing in two ways
that mattered. Phase 2 is unblocked; nothing carried forward blocks it.

Phase 1's charter definition was narrow and worth restating, because it is the bar this
record is measured against:

> pipeline de-risking spike — a full-length, multi-grid, few-hundred-frame VDB sequence
> through UE SVT (explicitly NOT a one-frame demo); single-cell storm playback end to end.

That is a *risk* deliverable, not a *feature* deliverable. Rain/hail particles and
lightning are Phase 4 and were never Phase 1's to ship. (A session note in
`phase1-svt-custom-material-2026-07-16.md` §6 had drifted into calling them "open Phase 1
visual items"; corrected 2026-07-20 — the charter is authoritative over session notes.)

## 1. Risks the spike was built to retire

| Risk | Outcome | Evidence |
|---|---|---|
| OpenVDB writer ↔ UE version mismatch | **RETIRED.** UE 5.8 bundles the identical `openvdb-13.0.0`, file format v225; pin locked | `phase1-task3-svt-import.md` |
| SVT can't hold a few-hundred-frame animated sequence | **RETIRED.** 300 synthetic + 301 real frames both import to a full-length `AnimatedSparseVolumeTexture` | task3 + task5 docs |
| 2-texture / 8-channel SVT limit won't fit the channel set | **RETIRED.** Tex A RGBA16F = cloud/ice/rain/graupelhail, Tex B R16F = dbz — fits with room | manifest `svt_texture_map` |
| Static-bbox requirement breaks on a growing storm | **RETIRED**, with a caveat found in the doing (§3) | task5 |
| Per-frame streaming budget (30–50 MB) blown | **RETIRED with margin.** Peak **3.51 MB/frame**, ~14× under budget; whole package 0.46 GB | `phase1-svt-budget.md` |
| Volume renders wrong / not at all | **RETIRED**, after three distinct root causes (§4) | 07-15/07-16 session docs |
| Wall-clock makes iteration impractical | **RETIRED.** Full export 7.5 min; SVT import 11.6 s | task5 |

Upstream of all of it, Phase 0 had already locked the sim side: np=8, 333 m default /
250 m flat hero / 500 m preview, **bitwise reproducible**.

## 2. What actually ships

`scenarios/single_cell_500m/` — 525 MB, one folder, one package:

- `manifest.json` — **tracked in git**, 48 KB. Carries `format_version`, the units and
  single-conversion-site contract, channel sources and thresholds, the SVT texture map,
  the dBZ diagnostic block with its citations, CM1 provenance, and the UE placement rule.
- `vdb/` — 301 frames, 437 MB, gitignored.
- `web/` — 603 files, 86 MB, gitignored. The Storm Diorama rendition of the same volumes.

Storage was the last open charter item and is resolved (owner, 2026-07-20): packages live
in-tree under `scenarios/`, payload out of git *history*, **no Git LFS anywhere in this
repo**, manifest tracked. Rationale and the accepted consequence — packages are not backed
up by git, regeneration is the recovery path — are in `scenarios/README.md`. This also
closed the diorama design doc's §10 question: the web export ships **inside** the package.

## 3. What the spike caught that a one-frame demo could not

This is the part that justifies the charter's "explicitly NOT a one-frame demo", and the
strongest argument for the same discipline in Phase 2/3.

**Two silent contract errors, both invisible on synthetic data and on any single frame:**

1. **The locked 40×40 km crop clipped the real cold-pool outflow.** Real half-width is
   23.25 km. Nothing errored — the data was simply cut. Box widened to 52×52×18 km.
   Note the interaction with the static-bbox requirement: the box must be padded for the
   storm's *whole life*, so the crop can only be validated against a full-length run.
2. **`ice = qi` silently dropped snow.** Corrected to `qi + qs`; snow is not a rounding
   term at qs/qi ≈ 0.29–0.53 by mass.

**One UE behaviour that would have looked like a bug forever:** the SVT factory unions
active voxels across the sequence and re-bases the box (208×208×72 @ −25875 →
186×186×65 @ −23125). Lossless, but it means **placement must come from the imported
asset's transform, never from the manifest's `origin_m`** — adding it on top lands the
volume 2750 m off. That rule is now written into the manifest itself, where the UE app
will read it.

## 4. Method lessons worth more than the artifact

- **`-nullrhi` is structurally incapable of validating rendering.** It underpinned task 3
  and task 5 and reported `verdict = READY` over an unsaved level, a lightless scene, a
  non-persisting actor label, and a screenshot loop that wrote no files. **Any future
  "SVT works" claim must come from a real RHI.** This is the single most load-bearing
  lesson of the phase.
- **The three render root causes were all environmental, none were the data:** the
  placement rule was wrong (scale 100, not 25000 — the ×25000 rule made it 250×
  oversized); `r.HeterogeneousVolumes.MaxTraceDistance` defaults to 300 m against a
  100 km scene; and `bIssueBlockingRequests=true` (engine default false, left on while
  debugging) was what stalled streaming at lowest mip. The "zero views / second gate"
  theories built on the debug overlay's `Requested Mip` field were **wrong and are
  retracted** — that field excludes blocking requests by design and is not a view counter.
- **MI scalar edits apply only at the NEXT PIE start, never live.** A parameter sweep is
  one Simulate cycle per value, verified by pixel diff against a drift control. Earlier
  "live in PIE" claims are retracted.
- **The level is One-File-Per-Actor.** Component edits dirty the actor's package under
  `__ExternalActors__`, never the map package — an hour was spent asking why the level
  wouldn't dirty. `AssetTools.save_assets {"asset_paths": []}` saves everything headlessly.

## 5. Honest ledger — Claude-verified vs owner-confirmed

Carried forward deliberately, in the same spirit as the diorama's OWNER-OWED notes.
Neither blocks Phase 2.

- **Task 3's namesake in-editor visual streaming playback — capability proven, owner
  sign-off never given.** The 07-15 render fix, the 07-16 streaming root-cause session
  and the 07-16 material session all ran on a real RHI in Simulate and showed the storm
  streaming and rendering full-size. So the *risk* is retired on evidence. What has not
  happened is the owner sitting in front of it and saying so. Recorded as unsigned rather
  than quietly upgraded to done.
- **Diorama slice 5c pan gestures** — driven only by synthetic `PointerEvent`s, which
  bypass native button handling. Real middle-drag vs Chrome's autoscroll puck, and the
  shift+left / alt+left fallbacks, are untested by anything. See the design doc.

## 6. Carried into Phase 2

1. **The Y-flip is not applied or verified.** The manifest's placement rule §(3) is
   explicit: CM1 is right-handed, UE left-handed; the candidate is actor `scale.y = -100`,
   and it **must be confirmed against a known-asymmetric storm feature before Phase 2
   placement code ships.** The zero-shear pulse cell in this package is nearly
   axisymmetric — it is close to the worst possible test case for a handedness bug, which
   is exactly why this is still open. A sheared Phase 3 storm would expose it immediately;
   Phase 2 must not wait that long.
2. **`manifest.json` does not declare the `web/` rendition** — `web/web_manifest.json`
   stands alone. A `web` block in `pipeline/cm1post/manifest.py` makes the package
   self-describing; no re-export needed. Small.
3. **dBZ resampling interpolates in dB, not linear Z** (manifest `diagnostics.dbz.caveat`).
   Acceptable for a plumbing spike; revisit before dBZ is used quantitatively in the UI —
   which is precisely Phase 2's radar view.
4. **The VDB max virtual size is 1024 GB** and the 250 m terrain hero runs in Phase 3 can
   approach it. Provision before that run, staying under M:'s headroom — owner's number.
5. Deferred cosmetic backlog from the diorama beauty gate (warmer sun/ambient split,
   shore shallows, softer horizon band) — render-time only, blocks nothing.
