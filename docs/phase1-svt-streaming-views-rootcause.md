# SVT streaming root cause: mip requests are VIEW-driven (2026-07-16)

**One-line:** the "ghost column / lowest-mip" defect is not a streaming-pool leak and an
editor restart does **not** clear it — SVT mip selection returns FLT_MAX ("stream nothing")
whenever the engine's streaming manager has **zero registered views**, and on this machine
the editor has been running with its main window parked off-screen and background-throttled,
so no view was ever registered while Claude drove it remotely.

## The mechanism (UE 5.8 source, verified line-by-line)

1. `UHeterogeneousVolumeComponent::TickComponent`
   (`Engine/Private/Components/HeterogeneousVolumeComponent.cpp:685`) computes the mip to
   request via `SparseVolumeTexture->GetOptimalStreamingMipLevel(Bounds, StreamingMipBias)`.
2. `USparseVolumeTexture::GetOptimalStreamingMipLevel`
   (`Engine/Private/SparseVolumeTexture/SparseVolumeTexture.cpp:985`) initializes the result
   to **FLT_MAX** and lowers it only by iterating `IStreamingManager` views (projected
   screen-size heuristic). **Zero views ⇒ FLT_MAX is returned verbatim.**
3. The SVT streaming manager honors the request literally: mip mask ends up empty and only
   the always-resident root/lowest mip is ever available. The volume renders as a huge
   blurry "ghost column" (or, at other densities, an invisible wisp / tiny frame-0 bubble).
4. Views are registered each editor tick by `UEditorEngine::UpdateSingleViewportClient`
   (`Editor/UnrealEd/Private/EditorEngine.cpp:2617`, "Always submit view information...")
   — but ONLY for `GCurrentLevelEditingViewportClient`, and only when that client is
   non-null and `IsVisible()`. Real game viewports (standalone / real PIE) register views
   via `UGameViewportClient::Draw`.

### Corollaries (these rewrite two prior claims)

- **"The editor (non-PIE) world never streams SVT frames"** (2026-07-15 handoff) — the
  mechanism is *view-based, not world-based*. The editor world CAN stream when a visible
  viewport registers views; every observation behind that claim was made through offscreen
  captures / a background-throttled editor, i.e. zero views.
- **"Restart the editor to clear the mip degradation"** — REFUTED. Fresh editor, same
  FLT_MAX. The "degradation after ~8 PIE cycles" on 2026-07-15 was almost certainly the
  editor window losing foreground (throttle kicks in → rendering stops → views vanish),
  not pool exhaustion.
- **Offscreen `CaptureViewport` renders do not drive streaming.** They render one frame of
  the scene but never call `AddViewInformation`. Every capture-based "did it stream?" test
  is blind unless something else keeps views alive.

## Why remote driving hit this so hard (this machine, this session)

- The editor main window was **parked off-screen** (rect (−21333,−21333), 158×26 — the
  Windows minimized-park position at 150 % DPI). A parked window's Slate widgets never
  paint → `SLevelViewport::IsVisible()` false → no viewport update → no views.
- `bThrottleCPUWhenNotForeground` (Editor Preferences → Performance, **default true**)
  additionally disables ALL editor rendering when the app has no focus
  (`EditorEngine.cpp:1807`) and drops PIE to "max tick rate 3". Before it was disabled,
  SVT streaming updates ran **only when a CaptureViewport forced a frame** (update counter
  advanced ~once per capture); after disabling, updates run at ~60 fps (needed but not
  sufficient — views were still zero).
- The 60 fps render loop with zero viewport views is sustained by the SkyLight's
  `bRealTimeCapture` — scene renders happen, but they are not viewport draws and register
  no views. Do not take "renderer is ticking" as evidence the viewport paints.

## Diagnostic toolkit that cracked it (reusable)

- `r.SparseVolumeTexture.Streaming.ShowDebugInfo 1` — on-screen overlay, per-instance:
  `Requested Mip: 3402823466...e38` = FLT_MAX = zero views. THE smoking gun. (Set via
  BP_ConsoleExec BeginPlay; capture with `bShowUI: true`.)
- `r.SparseVolumeTexture.Streaming.LogVerbosity 3` + **`EditorToolset.LogsToolset`** MCP
  toolset (`GetLogCategories` / `SetVerbosity` / `GetLogEntries`) — read the UE log over
  MCP; no log-file tailing. SVT categories: `LogSparseVolumeTextureStreamingManager` etc.
  "SVT Streaming Update N" cadence tells you whether the renderer is ticking at all.
- `SearchCVars` arg name is `name` (not `searchTerm`).
- `CaptureEditorImage` (EditorAppToolset) screenshots the whole editor UI even when the
  window is parked off-screen — good for "what state is the editor actually in".
- Component state reads: the SVT props live on the component
  (`...PersistentLevel.<Actor>.HeterogeneousVolumeComponent` — note NO trailing digit).

## State changed this session (SvtProbe throwaway project + editor session)

- `bThrottleCPUWhenNotForeground=false` set on the `EditorPerformanceSettings` CDO —
  **session-only, not yet saved to the editor user ini**; must be re-applied per launch or
  persisted (Editor Preferences → Performance → "Use less CPU when in background" off).
- `BP_ConsoleExec` BeginPlay now also runs the two SVT debug cvars above (harmless;
  remove when visuals are done).
- Editor main window moved on-screen to (100,100)–(1700,1000).
- MI_SvtPlayback "Density Scale" was swept 0.01 → 0.3 → 0.05 during diagnosis;
  **left at 0.05** — the 2026-07-15 sweep plan (0.003/0.01/0.03) still stands once
  streaming works.

## What is still owed (blocked on one manual step)

Streaming still requests FLT_MAX even with the window restored + foregrounded via Win32.
Remaining hypothesis: `GCurrentLevelEditingViewportClient` is null (no human has ever
clicked a level viewport this editor session) and/or the viewport tab never painted while
parked. **Manual unblock: bring the editor window up, click once inside the level
viewport, keep the window visible** (it may sit behind other windows only if Windows still
composites it — safest is visibly on screen). Then the density sweep + two standard views
can resume over MCP exactly as planned in the 2026-07-15 handoff.

**Etiquette note (cost of learning it):** this box is in active interactive use; remote
window-foregrounding and synthetic clicks fight the person at the keyboard — one injected
click landed in the owner's browser before this was caught. Rule going forward: no desktop
input injection; ask the owner to stage the window.

## Alternatives if keeping a visible viewport is unacceptable

- Real PIE in a new window (its `UGameViewportClient` registers views even without the
  level viewport) — but spawns a desktop window and changes the camera model.
- A tiny editor utility/BP that calls `IStreamingManager::AddViewInformation` with a
  lasting duration each tick — would need a C++ toolset (charter says keep C++ out of
  unreal/; fine inside the throwaway probe project if it ever becomes necessary).
- Repeated `CaptureAssetImage` world-thumbnail renders register a view for one frame
  (`WorldThumbnailRenderer.cpp:313`) — hacky, coarse-mip only, not pursued.

Chronology captures: `M:\claud_projects\temp\task5_visuals\cap20…cap34*.png`
(cap24/25/27/29/30/32/33/34 all show `Requested Mip = 3.40282e38`).
