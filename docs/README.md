# docs/ — index

Every parameterization cites its paper; every task leaves a report; every owner
decision leaves a record. This index groups the files by kind. The per-task status
log (the charter's former status section, verbatim) is `STATUS.md`.

## Start here

| File | What it is |
|---|---|
| `../CLAUDE.md` | The charter: principles, architecture, constraints, pinned versions, conventions, one-line-per-phase status table, open owner calls. |
| `STATUS.md` | Full per-task record — every gate count, measured number, retraction and lesson, Phase 0 → today. |
| `plan-science-hurdles-2026-09-02.md` | **The open scientific hurdles, ranked, with the proposed way through each** — the current plan for finishing Phase 3 and the prerequisites for 3T and 4. |

## Plans (one per phase, with the owner's scope pins)

| File | Phase |
|---|---|
| `phase2-plan-2026-07-20.md` | Phase 2 — scenario system, selectable layers, radar plan view (COMPLETE). |
| `phase3-plan-2026-07-20.md` | Phase 3 — flat convective regimes: supercell, seed, multicell (IN PROGRESS; §10 amendment points to the 2026-09-02 plan). |
| `plan-diorama-beauty-2026-07-17.md` | Diorama visual plan. |

## Decision records and reviews

| File | Decision |
|---|---|
| `advisor-review-2026-07-09.md` | Adversarial pressure-test of the original plan. Most of its items became charter constraints. |
| `decision-unreal-mcp-2026-07-14.md` | Unreal MCP: official embedded (UE 5.8) vs Remote-Control fallback. |
| `design-diorama-web-viewer-2026-07-16.md` | Storm Diorama web viewer design — the second "dumb player". |

## Task reports, by phase

**Phase 0 — benchmark gate**

| File | Result |
|---|---|
| `phase0-cm1-build.md` | CM1 built in WSL; stock binary sha256. |
| `phase0-validation.md` | Canonical WK supercell validated (split, peak w 60.6 m/s @ 83 min). |
| `phase0-benchmark.md` | Throughput → 333 m default / 250 m flat hero / 500 m preview; np=8; bitwise reproducible. |

**Phase 1 — pipeline spike**

| File | Result |
|---|---|
| `phase1-task3-svt-import.md` | 300-frame VDB sequence imported headless into a UE SVT; openvdb pin locked. |
| `phase1-svt-budget.md` | SVT streaming budget → decimation budget; crop-box lessons. |
| `phase1-task5-pipeline.md` | Real CM1 netCDF → 301-frame VDB + manifest. |
| `session-handoff-2026-07-15-visuals.md` | First real-RHI render; placement rule corrected. |
| `phase1-svt-streaming-views-rootcause.md` | The "blob" root cause (`bIssueBlockingRequests`); VHDX ACL gotcha. |
| `phase1-lighting-pass-2026-07-16.md` | Daylight scene, exposure, fog; MI-edit timing rule. |
| `phase1-svt-custom-material-2026-07-16.md` | Physical-extinction volume material. |
| `phase1-completion-2026-07-20.md` | Phase close-out; package-storage and env-lockfile decisions. |

**Phase 3 — flat convective regimes**

| File | Result |
|---|---|
| `phase3-t2-run-health.md` | Supercell run health + bbox gate. |
| `phase3-t3-orientation.md` | cref orientation test discharged end to end (netCDF → brick → real-GPU pixels). |
| `phase3-t4-seed.md` | Seed-driven variation; CM1 forked (nine-line uncomment of its own hook); spread measured. |
| `phase3-t5-multicell.md` | Multicell initiation: three pre-registered classifier rounds, six 1 km probes, **no multicell reachable from the namelist**; classifier reach measured. |
| `plan-science-hurdles-2026-09-02.md` | Why T5 was blocked at the root (environment computed inside CM1) and the external-sounding path through it. |

## Standing method rules (where they were learned)

- **Read the source before writing code** — T4 (no seed knob exists), T5 (`iinit`/`iwnd`
  are option selectors; everything inside is hardcoded), T5s (`isnd=7` exists).
- **Pre-register, commit, then score** — T5 §§3, 8, 12; the T5s sweep carries its BRN
  prediction inside each config.
- **A gate that has only ever passed is not known to work** — negative controls in every
  test file; a self-referential control cannot fail (T5 §7.2).
- **Measure the box, never match it** — Phase 1 task 5, Phase 2 T6, Phase 3 T1.
- **Gate the data, never the container** — `.vdb` and `.gz` are not byte-reproducible
  (Phase 2 T1).
- **A copy needs a consistency check; a pointer does not** — Phase 2 T2 (manifest `web`
  block), T4 hash single-source gate.
- **Any "it renders" claim comes from a real GPU** — `-nullrhi` is structurally blind
  (Phase 1).
- **Never tune a threshold after seeing the candidates** — T5 §7.4, §11.5, §13.6.
