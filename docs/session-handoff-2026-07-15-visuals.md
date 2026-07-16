# Session handoff — 2026-07-15 evening: "fix the project visuals, then improve them"

**Where things stand in one line:** the SVT render defect is ROOT-CAUSED and the storm has
rendered full-size on a real GPU (multiple captures); scene foundation (sky/sun/fog/terrain
plane) is built and saved; the one live problem is that after ~8 PIE cycles the SVT
degraded to lowest-mip ("ghost column"), and the decisive test — **restart the editor,
Simulate, capture** — was queued when the session was paused.

User's order (verbatim scope): *fix the project visuals, then improve them — volumetric
clouds, fog, thunder, rain (different intensities), hail, lighting, terrain, sky, sun.*

## THE HEADLINE FINDINGS (these rewrite prior docs)

1. **The placement rule in docs/phase1-task5-pipeline.md was wrong.** On a real RHI the
   `HeterogeneousVolumeComponent` **DOES apply the SVT asset's frame transform**
   (scale 250, translation −23125 m). The `-nullrhi` finding ("1 voxel = 1 UE unit") is
   falsified — exactly the double-apply trap the doc warned about. **Correct actor
   transform: scale = (100,100,100) (m→cm only), location = (0,0,0).** Verified by
   `get_actor_bounds`: 46.5 × 46.5 × 16.4 km centered on origin, base at z=0. The manifest
   `ue_placement_rule` still needs this correction (task 3, not yet done). The Y-flip is
   still unresolved (visually irrelevant for this symmetric cell; matters for supercell
   chirality in Phase 3 — a true mirror needs scale.y = −100, not a translation shuffle).
2. **`r.HeterogeneousVolumes.MaxTraceDistance` (default 300 m) was a real cause of
   invisibility** — set to 100 km. Now persisted in the probe project's
   `Config/DefaultEngine.ini` `[ConsoleVariables]` (plus MaxShadowTraceDistance, Shadows=1,
   IndirectLighting=1/Mode=1).
3. **The editor (non-PIE) world never streams non-resident SVT frames.** Only frame 0 (the
   ~3 KB warm bubble) is resident; scrubbing Frame in the Details panel shows frame 0
   content regardless. **All visual verification must happen in Simulate/PIE** (StartPIE →
   frames stream). This is also why every earlier "black volume" capture was structurally
   doomed: saved level had Playing=False/Frame=0 AND editor world doesn't stream.
4. **`r.SparseVolumeTexture.Streaming.ForceBlockingRequests=1` correlates with frames NOT
   streaming at all** in Simulate (tested; reverted; warning comment left in the ini).
5. **The storm DID render full-size** (frame 255, 46.5 km wide, correct anvil silhouette) —
   see captures under `M:\claud_projects\temp\task5_visuals\` (cap02, cap06/07, cap10,
   cap11). So import, placement, material binding, streaming and the ray marcher all work.
6. **Self-shadowing physics gotcha:** with `r.HeterogeneousVolumes.Shadows=1`, a
   physically-dense 46-km cloud is light-tight — Beer-shadow single scattering has no
   multiple-scatter interior glow, so the volume reads near-black except a thin lit skin.
   The standard trick is lowering Density Scale until light penetrates ~0.5–2 km.
   Sweep was in progress (0.3 → 0.01) when the mip-degradation problem masked the results.

## LIVE PROBLEM (next session starts here)

After ~8 StartPIE/StopPIE cycles, the volume renders only as a huge blurry "ghost column"
(= lowest mip) with a small bright smudge at ground center (frame 0 bubble / densest
low-mip voxel). PIE-world state verified correct (sun 75000, bounds 46.5 km, MI bound,
frame 255, visible). Hypothesis: SVT streaming pool degradation/leak across PIE sessions,
or mip selection never requesting higher mips for a 35-km-away camera
(`r.SparseVolumeTexture.Streaming.RequestMipBias`).

**Next actions, in order:**
1. Quit and relaunch the editor (level/assets ARE saved), StartPIE Simulate, capture the
   two standard views (below). If the storm is sharp again → confirm "restart clears it",
   note it, and cap the number of PIE cycles per session / investigate pool cvars later.
2. Resume the Density Scale sweep at 0.003 / 0.01 / 0.03 from both standard views; pick
   the value where the anvil is translucent and the core reads solid with a shading
   gradient. Consider Albedo Scale/Color for warmth.
3. If exposure feels dark: Manual EV bias is on the PPV (−14.5); brighten toward −15 is
   *brighter*? No — LESS negative = brighter image (factor 2^bias). Current scene reads
   dusk-y also because the template VolumetricCloud layer shades the ground; consider
   thinning its coverage or accepting the moody look.
4. Then continue the improvement list: rain/hail Niagara (NiagaraToolsets registered),
   lightning flashes + thunder (BP_ConsoleExec pattern generalizes: author BPs via the
   blueprint DSL), landscape material, etc. Task list in the session tracker (tasks #3–#9).

Standard verification views (used all session, cap.py args):
- South (shadow side): `0 -3500000 300000 8 90`
- Southwest (sun side): `-3200000 -2700000 350000 6 40`

## HOW TO DRIVE UNREAL FROM CLAUDE (the big enabler this session)

Editor project: `M:\claud_projects\temp\svt_probe\SvtProbe\SvtProbe.uproject` (UE 5.8,
launch plain — MCP auto-starts on port 8000, `bAutoStartServer=True` in per-project user
settings). **Plugins now enabled in the .uproject:** `EditorToolset`, `NiagaraToolsets`,
`ConfigSettingsToolset` (all Epic first-party, Experimental, under
`W:\UE_5.8\Engine\Plugins\Experimental\Toolsets\`). These register 25 toolsets over MCP —
the AgentSkillToolset-only situation is fixed.

Key tools (exact names matter; describe_toolset for schemas):
- `EditorToolset.EditorAppToolset`: **CaptureViewport** (offscreen PNG + camera pose —
  bypasses the broken tiled HighResShot path entirely), **StartPIE/StopPIE**
  (`{"options": {"bSimulate": true, "playMode": "PlayMode_Simulate", "warmupSeconds": 3}}`),
  SearchCVars (read-only), SetCameraTransform, FocusOnActors, CaptureAssetImage.
- `editor_toolset.toolsets.scene.SceneTools`: find_actors (args `name`,`tag`,
  `collision_channels` all required), add_to_scene_from_asset (`asset_path`,`name`,`xform`),
  add_to_scene_from_class (`actor_type`), remove_from_scene, load_level.
- `editor_toolset.toolsets.object.ObjectTools`: get_properties(`instance`,`properties`),
  set_properties(`instance`,`values`=JSON-STRING), list_properties. Works on ANY UObject
  incl. components and PIE-world objects (path prefix `/Game/Maps/UEDPIE_0_SvtPlayback.`).
- `editor_toolset.toolsets.material_instance.MaterialInstanceTools`:
  get/set_scalar_parameter(`instance`,`name`[,`value`]). ~~**MI edits apply LIVE into a
  running PIE session** — the density sweep loop is: set param → capture, no PIE restart.~~
  **RETRACTED 2026-07-16 (docs/phase1-lighting-pass-2026-07-16.md §2): MI edits apply only
  at the NEXT PIE start, never live — sweep = one Simulate cycle per value.**
- `editor_toolset.toolsets.material.MaterialTools`: create_material, add_expression,
  connect_to_output(`expression`,`output_name`,`material_property` e.g. "MP_BaseColor"),
  recompile(`material_or_function`).
- `editor_toolset.toolsets.blueprint.BlueprintTools`: create(`folder_path`,`asset_name`,
  `asset_type`), write_graph_dsl(`graph`,`code`) — s-expression DSL, event node is
  `EventBeginPlay`, console node is `Development|ExecuteConsoleCommand`.
- `editor_toolset.toolsets.programmatic.ProgrammaticToolset.execute_tool_script` — batch
  tool calls in sandboxed Python (no `unreal` module). **Runs in ONE editor transaction:
  ANY uncaught exception rolls back EVERYTHING the script did** — and asset creations can
  survive as broken "zombie" packages (a name that "already exists" but can't load →
  pick a new name). Wrap fallible calls in try/except and always return a dict.

**Console commands / cvar writes** (no direct MCP tool): `/Game/SVT_REAL/BP_ConsoleExec`
actor is placed in the level; its BeginPlay runs an ExecuteConsoleCommand list (edit via
write_graph_dsl). Cvars set in PIE persist for the whole editor session. For boot-time
persistence use `[ConsoleVariables]` in `Config/DefaultEngine.ini` (already carries the
HV/SVT settings).

**Fast capture path (avoids huge MCP results in context):**
`python3 M:\claud_projects\temp\task5_visuals\cap.py out.png X Y Z PITCH YAW` — a direct
MCP-over-HTTP client (initialize → tools/call `call_tool`→CaptureViewport; SSE response
arrives ON the POST connection — read it line-wise; a plain GET /mcp is 405).
`extract_cap.py` decodes captures that came through the harness into PNGs.
All captures so far: `M:\claud_projects\temp\task5_visuals\cap01…cap19*.png` (chronology =
the whole debugging story).

## SCENE STATE (saved into /Game/Maps/SvtPlayback)

- Deleted: duplicate script-added SkyAtmosphere/SkyLight/DirectionalLight("Sun")
  (UAID_7CC2C63F…), and `SM_SkySphere` (32.8 km legacy skydome — smaller than the 46.5 km
  storm; caused the repeated on-screen warnings).
- Kept template stack: SkyAtmosphere, SkyLight (bRealTimeCapture=True), DirectionalLight
  (**intensity 75000 lux**, rot pitch −32 yaw 55 — physical-ish sun), ExponentialHeightFog
  (fogDensity 0.0003, falloff 0.0001, start 1 km), VolumetricCloud (template ambient
  cumulus layer — reads nicely in captures), Landscape (only 2×2 km — background detail).
- Added: `GroundPlane` (engine Plane × 200000 → 200×200 km at z=−40) with
  `/Game/SVT_REAL/M_Terra` (dark grass-green, roughness .95); `GlobalPostProcess`
  (unbound PPV: **Manual exposure, ApplyPhysicalCameraExposure=False, bias −14.5**, bloom
  0.15); `ConsoleExec` (BP above).
- StormVolume actor (`HeterogeneousVolume_UAID_7CC2C63F084389EE02_1782317938`):
  **scale 100, location 0,0,0**, frame 255, Playing=False, bIssueBlockingRequests=True,
  `bVisibleInRealTimeSkyCaptures=False` (a giant white volume in the realtime sky capture
  feeds back into ambient light).
- MI_SvtPlayback: Density Scale last set to **0.01** (sweep unfinished; 1.0 = solid
  blinding white when unshadowed; 2e-4 claimed in older docs never actually persisted).

## GOTCHAS LEDGER (cost hours; don't repay)

- Tool arg names are strict and inconsistent (`instance` vs `material`, `asset_path` vs
  `asset`, `actor_type` vs `actor_class`, `values` is a JSON *string*). On error the
  schema comes back in the message — read it, don't guess twice.
- `AutoExposureMin/MaxBrightness` clamps behaved unpredictably here; Manual exposure via
  bias is deterministic and is what's in place.
- The template sun was **6 lux** (arcade units): with it, nothing about volume lighting or
  exposure was calibratable. 75000 lux + EV≈15 is the physical regime.
- "max tick rate 3" appears in PIE logs (background editor throttling) — captures still
  work, but streaming/adaptation may be slow; give warmupSeconds ≥3.
- CaptureViewport results >~200 KB come back through the harness as saved-to-file; the
  cap.py direct client avoids that entirely.

## WHAT WAS *NOT* DONE

- Tasks #3 (manifest placement-rule correction + docs), #5 (final material), #6 rain,
  #7 hail, #8 lightning+thunder, #9 final screenshots/docs/commit of results.
- docs/phase1-task5-pipeline.md "Render investigation" has been updated to point here;
  detailed rewrite of its suspects table (PIE-streams-only confirmed, placement corrected)
  still pending as part of task 3.
- Nothing in `unreal/` yet — all of this is in the throwaway svt_probe project by design.
