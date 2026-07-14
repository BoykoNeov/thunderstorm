# Decision record: Unreal Engine MCP server

**Date:** 2026-07-14
**Status:** Decided (default). Confirm at UE version pin (Phase 0/1).
**Context:** Selecting an MCP server so Claude Code / AI agents can drive the
`unreal/` UE5 project (scene inspection, actor spawning, automation tests) during
Phase 1+ playback work. Must respect the charter boundary: **UE is a dumb player** —
MCP tools may touch playback/scene/editor, never physics or derived science.

## Decision

**Default to Epic's official first-party Unreal MCP**, embedded in the editor,
shipping with **UE 5.8** (Experimental). This factors into the still-open UE version
pin and favors pinning **5.8**.

If a hard constraint forces UE **5.5–5.7**, fall back to a **Remote Control API**–based
MCP server (rides UE's built-in Remote Control HTTP plugin; no custom C++ shipped into
`unreal/`) — e.g. `remiphilippe/mcp-unreal`.

## Setup (official, UE 5.8)

1. Edit → Plugins → search "Unreal MCP" → Enabled (auto-enables Toolset Registry) → restart.
2. Console command `ModelContextProtocol.GenerateClientConfig ClaudeCode` → writes
   `.mcp.json` to project root; launch Claude Code from that directory.
3. Binds loopback `http://127.0.0.1:8000/mcp` (HTTP + SSE; no stdio/WebSocket; no auth
   — acceptable for local single-node dev only).

**Caveats:** Experimental (APIs/schemas may change); reflection-driven tool schemas can
be incomplete; no remote access; Live Coding changes need a full editor restart to surface.

## Options considered

| Option | UE | License | Maturity | Mechanism | Notes |
|---|---|---|---|---|---|
| **Official Unreal MCP** (Epic) | 5.8 | first-party | Experimental | embedded editor server (HTTP+SSE) | Maintained with the engine; lowest maintenance; extensible via Python/C++ custom tools |
| chongdashu/unreal-mcp | 5.5+ | MIT | ~2k★, experimental | C++ plugin (TCP) + FastMCP Python bridge | Most-starred community option; adds maintained C++ to the project |
| remiphilippe/mcp-unreal | 5.7 | — | single Go binary, 49 tools | built-in Remote Control API (port 30010) | No custom C++; cleanest 5.5–5.7 fallback |
| cwilson-uno UE MCP | 5.x | — | 110 tools, no C++ | Remote Control API + optional Python executor | No custom C++; broad tool coverage |

## Rationale

- **Lowest maintenance / churn-resistant:** first-party moves with the engine — no
  third-party plugin to re-vet against experimental-feature churn (already tracked for
  SVT). Avoids adding maintained C++ to `unreal/`.
- **Boundary-safe:** custom-tool extensibility lets us expose only playback/scene
  tools; physics and derived quantities stay in the pipeline.
- **Timing:** UE playback work doesn't begin until Phase 1 and the UE version is
  unpinned until Phase 0/1, so choosing 5.8 costs nothing now.

## Sources

- Epic docs — Unreal MCP in Unreal Editor (UE 5.8):
  https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor
- https://github.com/chongdashu/unreal-mcp
- https://github.com/remiphilippe/mcp-unreal
- https://lobehub.com/mcp/cwilson-uno-ue-mcp
