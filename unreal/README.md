# unreal/

UE5 playback app. Renders scenario packages — no science lives here (see the "UE is a
dumb player" principle in the root `CLAUDE.md`).

Key constraints (from `docs/advisor-review-2026-07-09.md`):

- **Sparse Volume Textures are Experimental.** Max 2 attribute textures / 8 channels
  total per SVT; all grids share one transform; bounding-box center must be static
  across the sequence (pad a fixed box); streaming degrades above ~30–50 MB/frame.
- Niagara particles are driven from **2D near-surface textures**, not by sampling SVTs.
- Vertical exaggeration is applied at **render time only**, never baked into data;
  text/annotations counter-scaled, particle motion velocity-compensated.

Build artifacts (`Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`) and UE
binary assets are git-ignored. UE version pinned at Phase 1: **5.8.0** (root `CLAUDE.md`).

`svt_probe/` is NOT the app — it is the disaster-recovery snapshot (configs verbatim,
builder scripts, rebuild recipe) for the Phase 1 throwaway probe project that lives
out-of-repo at `M:\claud_projects\temp\svt_probe\`. See `svt_probe/README.md`.

_The playback app itself is still empty until its build phase. Do not start a phase
without explicit go from the owner._
