# Phase 1 — custom SVT volume material (2026-07-16, session 5)

**Goal:** replace the engine default `/Engine/EngineMaterials/SparseVolumeMaterial` (whose
`Density Scale` saturates visually above ~1 — lighting-pass doc §5) with a custom
Volume-domain material that maps the four hydrometeor channels to physically motivated
extinction, so the storm core can go solid while the ice anvil stays translucent.

**Status: DONE and verified in Simulate on a real RHI.** New assets
`/Game/SVT_REAL/M_StormVolume` + `/Game/SVT_REAL/MI_StormVolume`; the StormVolume
component's `OverrideMaterials[0]` now points at `MI_StormVolume`. Persistence: see §5.

## 1. Design

Channel contract (pipeline/cm1post/config.py): Tex A RGBA16F = cloud / ice / rain /
graupelhail summed mixing ratios in kg/kg; Tex B R16F = dbz (diagnostic, not sampled
by this material).

```
Extinction = ExtinctionScale × ( K_cloud·A.r + K_ice·A.g + K_rain·A.b + K_graupelhail·A.a )
```

Per-hydrometeor weights follow effective particle size (extinction per unit mass falls
as particles grow, β ∝ q/r_eff): cloud droplets ~10 µm ≫ ice/snow ~50–100 µm ≫ rain
0.5–1 mm ≫ graupel/hail mm–cm.

| Parameter (group "Storm") | Default | Rationale |
|---|---|---|
| Extinction Cloud | 1.0 | reference species, smallest r_eff |
| Extinction Ice | 0.10 | ice/snow ~10× larger r_eff |
| Extinction Rain | 0.02 | mm-scale drops |
| Extinction GraupelHail | 0.005 | largest particles |
| Extinction Scale | **1000** | global calibration (sweep, §4) |
| Albedo (vector) | (0.9, 0.9, 0.93) | slightly blue single-scatter albedo |

This is renderer-side legibility mapping of already-shipped diagnostic fields — no
science moved into UE ("UE is a dumb player" holds).

## 2. Material graph (engine-identical plumbing)

Verified against the engine's own SparseVolumeMaterial via MCP `get_property_input`
before building — Volume materials route **Extinction → MP_SubsurfaceColor** and
**Albedo → MP_BaseColor** (Emissive → MP_EmissiveColor, unused here).

- Material props: `MaterialDomain=MD_Volume`, `BlendMode=BLEND_Additive`,
  `bUsedWithHeterogeneousVolumes=true`.
- UVW chain: `Divide(Subtract(LocalPosition, ObjectLocalBounds.Min), ObjectLocalBounds.Extents)`
  — LocalPosition is the engine material function
  `/Engine/Functions/Engine_MaterialFunctions02/WorldPositionOffset/LocalPosition`.
- Sample node: `MaterialExpressionSparseVolumeTextureSampleParameter`, parameter name
  **`SparseVolumeTexture`** (must stay engine-identical — this is the name the
  HeterogeneousVolumeComponent binds the animated frame to), default texture
  `/Game/SVT_REAL/frame.frame`, UVs ← the chain above.
- Per channel: ComponentMask(R/G/B/A) off "Attributes A" × ScalarParameter, three Adds,
  × Extinction Scale → MP_SubsurfaceColor. VectorParameter Albedo → MP_BaseColor.

## 3. Build method — headless over Unreal MCP

Scripts in `M:\claud_projects\temp\svt_material\` (build_material.py, bind.py,
sweep_ext.py, finalize.py). ~50 MCP calls at ~16 s/call (one dispatch per editor tick)
≈ 13 min; run as background tasks. Gotchas hit:

- `MaterialTools.get_expression_input_names` on ComponentMask returns `['None']` — the
  mask's unnamed input reports as the literal string "None"; passing it back to
  `connect_expressions` works.
- `ObjectTools.get_properties` cannot read `FExpressionInput` properties (mask `Input`,
  multiply `A`/`B` all "could not be read") — interior wiring is not directly
  readable; verify functionally (render) plus `get_property_input` for the output pins.
- `layout_expressions` + `recompile` at the end; verification: MP_BaseColor ←
  VectorParameter, MP_SubsurfaceColor ← final Multiply, parameter group "Storm" listed.

## 4. Extinction Scale sweep (calibration)

One Simulate cycle per value (MI scalar edits apply only at next PIE start — lighting
doc rule), standard south + southwest views, frame ~150 window. Captures
`M:\claud_projects\temp\svt_material\ext{10,100,1000,3000}_{south,sw}.png`; mean-abs
pixel diffs all ≥ 3× the 0.46 drift baseline (10→100: 2.06, 100→1000: 2.45,
1000→3000: 1.34 south).

- **10** — faint ghost; whole storm translucent.
- **100** — reads as cloud; tower translucent, anvil barely there.
- **1000 — chosen default.** Low-level core solid with lumpy convective structure,
  anvil clearly translucent → the target "anvil translucent, core solid" contrast.
- **3000** — core fully solid, sculpted, slightly porcelain; anvil at its most
  legible. Good hero/dramatic setting; useful range is ~1000–3000 via the MI knob.

The engine material's saturation is confirmed bypassed: our graph has no clamp, and
each decade of Extinction Scale produced a distinct visual step.

## 5. Persistence — SAVED over MCP (no owner Save All needed), plus an OFPA lesson

Everything is on disk, saved headlessly via `AssetTools.save_assets`:

- `Content/SVT_REAL/M_StormVolume.uasset` + `MI_StormVolume.uasset` (17:51) —
  `save_assets({"asset_paths": [paths]})` works directly; the MI was saved *after*
  its Extinction Scale override was set to 1000, so 1000 is the on-disk value.
- The component's `OverrideMaterials` → MI_StormVolume (18:04) — this one was a trap:

**The SvtPlayback level uses One File Per Actor (OFPA).** The 13 KB
`SvtPlayback.umap` contains no actors; every actor is its own package under
`Content/__ExternalActors__/Maps/SvtPlayback/…` (hash-named). Consequences:

- `ObjectTools.set_properties` on a component dirties the **actor's external
  package**, never the map package — `is_dirty("/Game/Maps/SvtPlayback")` stays
  False and `save_assets` on the map path writes nothing. (An hour of "why won't
  the level dirty" — transform nudges, metadata tags — was chasing the wrong
  package.)
- The fix: **`save_assets({"asset_paths": []})` = save ALL dirty assets**, which
  sweeps in external actor packages. Verified by timestamp + binary scan of the
  rewritten actor package (contains `MI_StormVolume`, `OverrideMaterials`).
- This also retro-explains earlier sessions: owner Save All persisted MCP scene
  edits fine all along (external actor files carry 15.7 23:28 and 16.7 16:41
  save-batch timestamps); MCP edits do dirty packages — just the actor ones.

Other MCP save/sandbox gotchas hit while getting here:

- `ProgrammaticToolset.execute_tool_script`: script must define `run()` returning a
  dict; inside, call tools as `execute_tool("full.tool.name", json_string)`; results
  are `_StrictDict`s where `.get(k, default)` is banned (use `[]`); imports limited
  to json/math/datetime/copy/re/time. Batches many tool calls into ONE ~16 s MCP
  round-trip — use it for multi-step editor operations.
- `AssetTools.save_assets` requires the `asset_paths` key (schema-required) even for
  the save-all-dirty empty-list form.

## 6. Follow-ups

- Per-species albedo/emissive (e.g. darker rain shafts, dbz-driven tinting) — same
  graph, more parameters; Phase 2/4 polish.
- Rain/hail Niagara + lightning remain the open Phase 1 visual items.
