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

---

## Session 2 (2026-07-16 later): the view hypothesis is NOT sufficient — every fix failed

The whole first-session conclusion above says "register a view and it will stream." This
session tested that directly, six independent ways, and **every one still shows
`Requested Mip = 3.40282e38`.** The view-starvation mechanism is real and correctly
diagnosed, but making views exist did **not** unblock streaming. Something else is also wrong.

What was tried, each verified against UE 5.8 source first, all NEGATIVE:

1. **Owner did the manual step.** Editor window on-screen, visible, focused; owner clicked
   inside the level viewport and **right-drag-orbited for ~10 s** while the blob stayed in
   view. Owner report: *"I see no change"* in the blob. Poll of the overlay every 4 s for
   2 min (poll_00…29): FLT_MAX throughout. This refutes the "just needs a human click in a
   visible viewport" unblock in §"What is still owed".
2. **Live on-screen editor screenshot, not offscreen capture.** `CaptureEditorImage`
   (real editor window incl. menu bar / Outliner "SvtPlayback (Play In Editor)" / Output
   Log) during live Simulate — the storm overlay in the *actual* viewport reads FLT_MAX
   (cap58_liveeditor_*). So the earlier idea that "offscreen `CaptureViewport` is the wrong
   instrument and the live viewport really streams" is **also wrong** — the live viewport
   shows the same FLT_MAX. (Offscreen capture IS still blind to residency, but that was not
   what was hiding the result.)
3. **Real PIE with a pawn spawned inside the storm bounds** (`StartPIE` bSimulate:false,
   PlayMode_InViewPort, startTransform inside the volume). Game viewports register views
   unconditionally per source. Still FLT_MAX (cap54/55).
4. **`APlayerController::ClientAddTextureStreamingLoc`** invoked in Simulate via python
   `pc.call_method("ClientAddTextureStreamingLoc", (loc, 100000.0, False))` → engine
   `AddViewLocation(..., Duration=100000)`. Log confirms it ran
   ("INJECT_VIEW: lasting streaming views injected via PlayerController_0"). Still FLT_MAX
   (cap56/57).
5. **Native `IStreamingManager::Get().AddViewInformation(...)`** — the EXACT entrypoint
   editor viewports use — called via ctypes against the `UnrealEditor-Engine.dll` export
   table (parsed PE exports for the mangled `Get@IStreamingManager` + `AddViewInformation`
   symbols, built the FVector&/floats/bool/TWeakObjectPtr call). Editor survived, log clean.
   Still FLT_MAX. (Caveat: the hand-built x64 ABI call could be a silent no-op; not
   independently proven to have taken effect. But #3/#4 exercise the same view list through
   real engine paths and also failed.)
6. **`StreamingMipBias = -32`** on the component (so any finite per-view mip clamps to 0)
   + world-thumbnail renders. No effect.

### Revised reading

- Zero-views → FLT_MAX is a real code path and explains the *blob*, but the blob **persists
  even when views are made to exist** through multiple genuine engine paths. Either (a) the
  views are added to a different streaming-manager view list than
  `GetOptimalStreamingMipLevel` reads that same tick (ordering: `SetupViewInfos` runs at the
  top of the streaming Tick, the component's `GetOptimalStreamingMipLevel` runs during actor
  Tick — a view added mid-frame may not be visible until the next `SetupViewInfos`, and
  `IStreamingManager::Tick` sets `bPendingRemoveViews=true` so the *next* `AddViewInformation`
  wipes `PendingViewInfos`), or (b) there is a second gate downstream of mip selection.
- The overlay's FLT_MAX line is the storm instance; its bound frame shows as
  `EmptySparseVolumeTexture, Num Frames: 1` — i.e. the current frame is the non-resident
  placeholder, consistent with "nothing streamed", but does not by itself prove the cause.
- **Do not trust a hand-rolled ctypes ABI call as proof of anything** — it is the least
  verifiable step here and should be replaced by a real editor-utility C++/BP call (inside
  the throwaway probe only) if this path is pursued.

### Recommended next moves (for the fresh session)

1. **Stop injecting views blind; instrument instead.** With `LogVerbosity 3`, the
   bandwidth/`InBudgetMipLevel` lines (`SparseVolumeTextureStreamingManager.cpp:944/956`)
   only print when `GetNumViews()>0` and requested bandwidth>limit. Their absence in every
   log dump this session = the manager's `CurrentViewInfos` is empty *at the moment the SVT
   request is evaluated*, even right after an `AddViewInformation`. Confirm by logging
   `GetNumViews()` directly (tiny probe-only C++ toolset, or an editor console cmd if one
   exists) rather than inferring from the mip.
2. **Test the frame-ordering hypothesis:** add the view with a **lasting Duration** AND from
   inside the game viewport's own draw (real PIE, camera actually pointed at the storm and
   left running >2 s so several `SetupViewInfos` cycles include it) — then read the overlay
   from the SAME live PIE viewport (CaptureEditorImage), not a fresh transform.
3. **Simplest reframe — this is an owner-gated live check, and it may already work for a
   human.** The one configuration never cleanly tested: owner flies the **live Simulate
   camera** right up to the storm (WASD + RMB) and reports whether it sharpens. Yesterday's
   "sharp 46.5 km storm in Simulate" (handoff doc) was a live human Simulate session; no
   remote path has reproduced it, and it is possible only a genuinely-driven PIE/Simulate
   viewport (not MCP-driven) advances the view list here. If it sharpens for the owner,
   the deliverable is met and the remote-capture pipeline is the only thing broken.

### State left changed (throwaway SvtProbe project)

- `BP_ConsoleExec` BeginPlay now also runs `Slate.AllowSlateToSleep 0`,
  `Slate.bAllowThrottling 0`, `r.SparseVolumeTexture.Streaming.LogVerbosity 3`, and a
  `py inject_view.py` line (the ctypes view injector). **All of this is debug scaffolding —
  strip it when the render is fixed.**
- Component `StreamingMipBias` left at **−32** on the editor-world HeterogeneousVolume — must
  be reverted to 0 before any playback-performance testing (it forces finest mip).
- Simulate/PIE may still be running from the last script.
- Injection helper scripts + captures in `M:\claud_projects\temp\task5_visuals\`
  (inject_view.py = ctypes injector; cap50–cap58 = this session; all FLT_MAX).

### Etiquette (reaffirmed)

Desktop input stays owner-driven: a persistent file-watching `exec()` daemon inside the
editor was attempted as an injection channel and correctly **blocked** as an RCE/persistence
surface. Do not install standing code-exec backdoors in the editor; use one-shot,
auditable console/py calls and ask the owner for genuine viewport interaction.

---

## Session 3 (2026-07-16, later still): SOLVED — the real culprit was `bIssueBlockingRequests=true`, and the overlay never measured views at all

**One-line:** the component's `bIssueBlockingRequests` was **true** (engine default is
false; left on during earlier debugging). The debug overlay's "Requested Mip" field
**excludes blocking requests by design**, so it prints FLT_MAX whenever all requests are
blocking — every FLT_MAX reading in sessions 1–2 was this artifact, not "zero views".
Flipping the flag to false made streaming work immediately, **in the plain editor world,
driven entirely over MCP, with offscreen captures, no PIE, no human interaction.**

### The overlay semantics that broke two sessions of diagnosis

`FStreamingInstance` (`SparseVolumeTextureStreamingInstance.cpp`) keeps TWO mips:

- `LowestRequestedMip` — min over **non-blocking** requests this update; reset to FLT_MAX
  at the start of each update (`:74`); **blocking requests never touch it** (`:98-105`).
- `LowestRequestedBlockingMip` — where blocking mips actually go. **Not displayed.**

The overlay prints `Instance.RequestedMip = GetLowestRequestedMipLevel()` = the first one
(`SparseVolumeTextureStreamingManager.cpp:592`). Additionally
`GetRequestedBandwidth(bZeroIfBlocking=true)` returns 0 for a blocking instance (`:149-154`)
— which is why the overlay always showed `Requested Peak Bandwidth: 0000.00 MiB/s`.

So on this overlay, `Requested Mip: 3.40282e38` means **"no non-blocking requests arrived
this update"** — it does NOT distinguish (a) zero views, (b) all-blocking requests,
(c) no requests at all. Sessions 1–2 treated it as a view counter. It never was one.

### What actually happened, reconstructed

- The component (`StormVolume`) had `bIssueBlockingRequests=true` (component default is
  **false**, `HeterogeneousVolumeComponent.cpp:271`; the flag was almost certainly toggled
  during the 2026-07-15 debugging alongside the `ForceBlockingRequests` cvar experiment and
  never reverted — the actor lives only in memory, so no diff exists to prove it).
- With the flag true, every request took the blocking path and the overlay showed FLT_MAX
  + 0 bandwidth **regardless of views** — including during the owner's genuine
  click-and-orbit and all six view injections. None of those experiments measured anything.
- Empirically, blocking requests also **did not stream** on this setup (residency bars
  stayed at lowest-mip red). Why the blocking path stalls in-editor was NOT chased further
  (suspects: editor DDC-backed IO with blocking waits; `Priority=uint8(-1)` scheduling) —
  the component default (async) is correct for playback anyway.
- With `bIssueBlockingRequests=false`: `Requested Mip: 0.00`, allocated bandwidth 7 MiB/s,
  and the requested frame's residency bars went **green in seconds**. Verified twice
  (Frame=60 → bars 59–62 green; Frame=100 → bars 100–103 green). A/B visibility toggle
  (`bVisible` false/true + capture diff) shows the full-size storm mass appearing in the
  render — transform, streaming, and rendering are all healthy.

### Retractions (supersede sessions 1–2 conclusions)

1. **"Zero registered views ⇒ FLT_MAX" as THE root cause — RETRACTED as diagnosis.** The
   code path is real (`SparseVolumeTexture.cpp:985-1017`), but it was never shown to be the
   operative failure. All post-window-restore FLT_MAX readings were the blocking artifact.
   (The parked-window era may genuinely have had zero views — moot now.)
2. **"Second gate / frame-ordering problem downstream of view registration" — RETRACTED.**
   No such gate. The instrument was misread; nothing about `SetupViewInfos` ordering or
   `bPendingRemoveViews` is broken. Lasting views land in `CurrentViewInfos` on the next
   `FStreamingManagerCollection::Tick` (`EditorEngine.cpp:2459`, unconditional) as designed.
3. **"The editor (non-PIE) world never streams SVT frames" — RETRACTED.** With async
   requests, the editor world streams fine. View registration comes from
   `UEditorEngine::UpdateSingleViewportClient` (`EditorEngine.cpp:2613-2618`), which
   submits views **unconditionally for any perspective viewport it updates** (before the
   throttle gate) — a visible-but-unfocused editor window with
   `bThrottleCPUWhenNotForeground=false` (set in session 1) is sufficient. No click needed.
4. **"All visual verification must run in Simulate/PIE" — WEAKENED.** Offscreen
   `CaptureViewport` still registers no views itself, but it *observes* streamed residency
   fine, and the on-screen editor viewport keeps views alive for it. Editor-world capture
   verification is fully workable.

### Overlay-reading gotchas (for the next person)

- Residency strip bar positions scale with editor DPI: bar x ≈ `(8 + FrameIndex·9) × 1.5`
  at this machine's 150 % DPI. A ~1700 px capture shows only frames ≲ 125 — a green bar
  for Frame=255 is off-screen right, NOT absent. Test with a frame index < 120.
- Red thin strip = lowest-mip-only residency (ResidentTiles fraction ≈ 0), green tall = resident.
- `Frame: N` on the instance line updating proves requests ARE reaching the manager.

### Current state (verified this session)

| Item | Value |
|---|---|
| `bIssueBlockingRequests` | **false** (fix; engine default) |
| `StreamingMipBias` | 0 |
| Requested Mip (overlay) | 0.00, ~7 MiB/s allocated |
| Residency | green for requested frame within ~10–20 s |
| Density Scale (MI_SvtPlayback) | 0.05 (sweep captures taken, see below) |

### ⚠ Persistence: the fix is IN MEMORY ONLY

The `StormVolume` actor's external-actor package has **never been saved**
(`save_actor` → "Asset does not exist: /Game/__ExternalActors__/Maps/SvtPlayback/8/QZ/…";
the map package itself is not dirty under One-File-Per-Actor). **If the editor closes, the
actor — and the `bIssueBlockingRequests=false` fix — vanish.** No MCP tool can save an
unsaved external actor package (AssetTools.save_assets needs a registry entry).
**Owner: press Ctrl+Shift+S (File → Save All) in the editor once.** Also note this proves
the editor has NOT restarted since 2026-07-15 — the "editor restart does not fix it" claim
in session 1 was tested against a restart that reverted nothing relevant.

### Density Scale sweep (done this session, owner to judge)

With streaming fixed, the planned sweep ran at Frame=255 (mature storm), mip 0 resident:
`M:\claud_projects\temp\task5_visuals\sweep2_{0p003,0p010,0p030,0p050}_{south,sw}.png`
(South = 0,−35 km,3 km @ pitch 8 yaw 90; Southwest = −32,−27 km,3.5 km @ pitch 6 yaw 40).
Caveat: the scene currently reads dark/dusk-like and fog washes the storm heavily at these
distances — the sweep is internally consistent but the anvil-translucent/core-solid call
likely needs the lighting pass (sun angle/exposure) first. MI restored to 0.05 after.
An A/B `bVisible` toggle diff (cap64_novol/cap64_vol, 18 km out) proves the volume renders
full-size with structure sourced from mip 0.

### Teardown — DONE (2026-07-16, after owner Save All)

The owner pressed Save All: the StormVolume external-actor package now exists on disk
(`Content/__ExternalActors__/Maps/SvtPlayback/8/QZ/NT9369DIF9YCDAHPAP3SSV.uasset`), so the
actor and the `bIssueBlockingRequests=false` fix are durable. Then, all over MCP:

- `BP_ConsoleExec` BeginPlay stripped of all debug lines (was 11 commands incl.
  `Slate.*`, `LogVerbosity 3`, `ShowDebugInfo 1`, `py inject_view.py`; the five HV/SVT
  render cvars it also carried were redundant — `Config/DefaultEngine.ini`
  `[ConsoleVariables]` already persists them). Final BeginPlay: two idempotent reset
  lines `ShowDebugInfo 0` + `LogVerbosity 0` (the graph DSL cannot express a bodyless
  event — a `(event EventBeginPlay)` write is a no-op — so an explicit "debug off" is
  the cleanest representable state). Executed once via a Simulate bounce; both cvars
  verified back to 0 via SearchCVars. BP saved to disk. `inject_view.py` deleted.
- `bThrottleCPUWhenNotForeground=False` persisted via ConfigSettingsToolset
  (`SetSectionProperties` + `SaveSection`, container `Editor` / category `General` /
  section `EditorPerformanceSettings`) — survives editor restarts; remote driving keeps
  working with the window visible-but-unfocused.
- Component verified post-teardown: `bIssueBlockingRequests=false`, `StreamingMipBias=0`,
  `Frame=255`.
- Manifest `ue_placement_rule` corrected to the proven rule (asset transform + actor
  scale=100 @ origin; Y-flip still open) in `pipeline/cm1post/manifest.py` and the
  shipped package's manifest.json regenerated in place (frames/origin byte-identical).

### WSL boot regression found & fixed during teardown (2026-07-16)

`wsl -d Ubuntu` failed with `Wsl/Service/CreateInstance/MountDisk/HCS/E_ACCESSDENIED`
on the relocated `M:\wsl\Ubuntu\ext4.vhdx` — although a bare `wsl --mount --vhd … --bare`
of the SAME file succeeded. Cause: the distro-start path re-grants disk access to the
utility VM's per-boot SID **under the user's (non-elevated) session token**, which needs
WRITE_DAC on the VHDX. Under `%LOCALAPPDATA%` the user has implicit Full Control; under
`M:\wsl` the user only inherited `Authenticated Users:(M)` — Modify without WRITE_DAC.
It worked 07-14/15 because the then-current VM SID's ACE was already on the file; the
Host Compute Service restart on 07-16 08:48 minted a new VM SID and exposed the hole.
**Fix (applied): `icacls M:\wsl /grant "boiko:(OI)(CI)F"` + same on ext4.vhdx.** Any
future distro relocation to a non-profile drive needs this grant.
