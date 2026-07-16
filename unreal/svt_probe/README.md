# SvtProbe — rebuild recipe (disaster recovery for the Phase 1 probe project)

The live UE 5.8 probe project is **`M:\claud_projects\temp\svt_probe\SvtProbe\`** — it is
deliberately NOT in git (throwaway by design; 536 MB of binary `.uasset`s, and the repo
policy gitignores `*.uasset`/`*.umap` anyway). This folder is the insurance policy: the
small text configs verbatim, the scripts that built everything, and the recipe below.
Everything binary is regenerable — the VDB sequence from CM1 output in ~7.5 min
(`pipeline/export_scenario.py`), the SVT asset from the VDBs in ~12 s, the level from
scripts + the scene-state table below.

Snapshot date: **2026-07-16**, after the lighting/exposure pass (session 4) and the
owner's Save All. Rationale for every value lives in the docs listed at the bottom;
this file is deliberately just the *what*, so a rebuild is mechanical.

## ⚠ The one trap: the builder scripts carry a superseded placement rule

`scripts/build_playback_level.py` and `scripts/build_v7.py` set the StormVolume actor
transform from the SVT frame transform ×100 (scale 25000, location −23125 m). That rule
came from `-nullrhi` runs and is **falsified on a real GPU**, where the
`HeterogeneousVolumeComponent` applies the SVT frame transform itself
(docs/session-handoff-2026-07-15-visuals.md §1). The scripts are archived verbatim as
they ran. **After running them, correct the actor:**

- StormVolume **scale = (100, 100, 100)** (pure m→cm), **location = (0, 0, 0)**.

Check: `get_actor_bounds` must report ≈46.5 × 46.5 × 16.4 km centered on the origin.

## Rebuild steps

Prereqs: UE **5.8.0** at `W:\UE_5.8`; the 301-frame VDB sequence (regenerate with
`pipeline/export_scenario.py` from the CM1 netCDF in WSL, or from a kept copy at
`M:\claud_projects\temp\task5\vdb\`).

1. **Project shell.** Make an empty folder, copy in `SvtProbe.uproject` and
   `Config/DefaultEngine.ini` from here. The `.uproject` enables the five plugins
   (PythonScriptPlugin, ModelContextProtocol, EditorToolset, NiagaraToolsets,
   ConfigSettingsToolset); the ini persists the render cvars (100 km HV trace
   distance — the 300 m default makes a km-scale volume invisible) and the startup map.
   Do NOT add `r.SparseVolumeTexture.Streaming.ForceBlockingRequests=1` (frames never
   stream with it — comment in the ini).
2. **Import the SVT** (headless, ~12 s):
   ```
   cd <project dir>
   W:\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe SvtProbe.uproject ^
     -ExecutePythonScript="<...>\scripts\import_real.py" -unattended -nosplash -nullrhi
   ```
   (Edit `SEQ_DIR` in the script if the VDBs are elsewhere.) Produces
   `/Game/SVT_REAL/frame`: 301 frames, 186×186×65 voxels, frame-transform translation
   (−23125, −23125, 125) m, scale 250 m/voxel — UE trims empty padding on import;
   expected values in the script are UE's post-trim numbers and the run self-checks
   them (`verdict = PASS` in `Saved/Logs/SvtProbe.log`; output goes to the log, not
   stdout).
3. **Material + level.** Run `scripts/build_playback_level.py` the same way (creates
   `MI_SvtPlayback` with the correct static switches and builds the level from the
   `TimeOfDay_Default` template), then `scripts/build_v7.py` (rebuilds the level with a
   save that is verified to hit disk — v5/v6 saves failed silently) and
   `scripts/verify_v7.py` from a separate process. Then apply the placement correction
   above.
4. **Scene state** (hand-applied over MCP across 07-15/07-16; the builders do NOT do
   this). Target state:

   | Actor / asset | State |
   |---|---|
   | Deleted | `SM_SkySphere` (32.8 km legacy skydome), duplicate script-added SkyAtmosphere/SkyLight/DirectionalLight |
   | DirectionalLight | intensity **75000 lux**, rotation pitch **−32**, yaw **55** |
   | SkyLight | `bRealTimeCapture = True` |
   | ExponentialHeightFog | density **5e-5**, height falloff **0.01**, start distance 1 km |
   | VolumetricCloud (template) | **hidden** (`bVisible=False`) — it camouflages the storm |
   | GroundPlane | engine Plane, scale 200000 (200×200 km), z=−40, material `/Game/SVT_REAL/M_Terra` (dark grass-green, roughness 0.95) |
   | GlobalPostProcess (unbound PPV) | **Manual** exposure, `ApplyPhysicalCameraExposure=False`, **bias −13.0**, bloom 0.15 |
   | BP_ConsoleExec (`/Game/SVT_REAL/BP_ConsoleExec`, placed) | BeginPlay = exactly two idempotent resets: `r.SparseVolumeTexture.Streaming.ShowDebugInfo 0`, `r.SparseVolumeTexture.Streaming.LogVerbosity 0` |
   | StormVolume (HeterogeneousVolume) | scale (100,100,100), location (0,0,0), material slot 0 = `MI_SvtPlayback`, **Frame=150**, Playing=False, Looping=True, frame rate 25, **`bIssueBlockingRequests=False`** (True was the whole streaming bug), `StreamingMipBias=0`, `bVisibleInRealTimeSkyCaptures=False` (else the volume feeds back into ambient light) |
   | MI_SvtPlayback | parent `/Engine/EngineMaterials/SparseVolumeMaterial`; `SparseVolumeTexture=/Game/SVT_REAL/frame`; switches `StaticSparseVolumeTexture=False` (else frames never advance), `Density (Attributes A)=True`, `Clamp SVT Density=False`, `Use Blackbody Temperature=False`; **Density Scale=5.0, Albedo Scale=0.9** (daylight placeholders — a custom physical material is a pending task) |

5. **MCP wiring.** `Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini` lives
   in `Saved/` and is not part of this snapshot — re-add:
   ```ini
   [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
   ServerUrlPath=/mcp
   ServerPortNumber=8000
   bAutoStartServer=True
   ```
   (or Editor Preferences → Model Context Protocol → auto-start). Copy `.mcp.json`
   (here) to the Claude Code project root that will drive the editor. Also turn OFF
   Editor Preferences → Performance → "Use less CPU when in background"
   (`bThrottleCPUWhenNotForeground=False`) — a background-throttled editor stalls
   streaming and captures.
6. **Verify.** All visual checks in **Simulate/PIE** — the editor world only ever shows
   frame 0. Start Simulate over MCP (`StartPIE {"options":{"bSimulate":true,
   "playMode":"PlayMode_Simulate","warmupSeconds":3}}`), wait ~25 s for streaming, then
   capture the two standard views with `scripts/cap.py`:
   ```
   python cap.py south.png 0 -3500000 300000 8 90
   python cap.py sw.png -3200000 -2700000 350000 6 40
   ```
   Expect: full daylight, a classic cumulonimbus (frame 150 is the hero frame; 255 is a
   late-stage diffuse cloud) legible at 35 km, ≈46.5 km across.

## Scripts in `scripts/`

Archived verbatim from `M:\claud_projects\temp\task5{,_visuals}\` — paths inside them
point at the temp locations; edit before running from elsewhere.

- `import_real.py` — headless VDB→SVT import + self-checks (step 2)
- `build_playback_level.py` — creates MI_SvtPlayback + first level build (step 3; ⚠ placement)
- `build_v7.py` / `verify_v7.py` — level rebuild with disk-verified save + out-of-process check (⚠ placement)
- `cap.py` — direct MCP-over-HTTP viewport capture (`cap.py out.png X Y Z PITCH YAW`)
- `extract_cap.py` — decode a harness-saved CaptureViewport JSON into a PNG
- `sweep5_cycle.py` — the correct MI-parameter sweep pattern: **one Simulate cycle per
  value** (MI scalar edits apply only at the next PIE start, never live)

## Where the rationale lives

- `docs/phase1-task3-svt-import.md` — headless import mechanics, openvdb pin
- `docs/phase1-task5-pipeline.md` — real-data import, level build, UE box-trim behaviour
- `docs/session-handoff-2026-07-15-visuals.md` — placement-rule correction, cvar causes,
  editor-world-never-streams, scene foundation, MCP toolsets + gotchas ledger
- `docs/phase1-svt-streaming-views-rootcause.md` — `bIssueBlockingRequests` root cause,
  teardown contract
- `docs/phase1-lighting-pass-2026-07-16.md` — final lighting values, MI-edits-at-PIE-start,
  frame timeline (150 = hero), Density-Scale saturation
