# sim/templates/ — base CM1 decks for the scenario system

`base.namelist.input` is the **template** half of Phase 2's template + overrides
deck generation (`pipeline/cm1post/deck.py`, plan §4). A scenario config in
`sim/scenarios/<name>.json` declares only what it *changes*; everything else comes
from here and must not drift.

```bash
# generate
python3 pipeline/gen_deck.py --scenario single_cell_500m -o namelist.input

# T1c regression gate: reproduce the committed hand-written deck
python3 pipeline/gen_deck.py --scenario single_cell_500m \
    --verify sim/single_cell/namelist.input
```

## Why a template rather than full generation

The validated deck carries ~8 KB of numerics, boundary conditions, SGS constants and
the NSSL microphysics block that were settled in Phase 0 and must not move.
Regenerating them from scratch would put every one at risk to gain nothing.
Generation touches **17 lines out of 413**; the other 396 stay byte-identical.

## Provenance of this file

It is the **Phase 0 validated supercell deck** (`sim/validation/namelist.input`,
`docs/phase0-validation.md`) with one deliberate change: the `&param9` output block
is retargeted to what the pipeline needs — `output_filetype=2` (one file per output
time), `output_thpert`, and `output_cape/cin/lcl/lfc/pwat` all on.

Basing the template on the *validation* deck rather than on
`sim/single_cell/namelist.input` is what makes the T1c gate non-circular: all 17
scenario keys genuinely differ between template and target, so reproducing
`single_cell_500m` exercises every substitution instead of no-oping against a copy
of itself.

## The key categories

The first lives in the scenario JSON (required), the fifth optionally, and the sixth
is not a namelist key at all.

| Category | Where it comes from | Keys |
|---|---|---|
| **1. Scenario identity** | JSON `sim.namelist`, **required** | grid (`nx/ny/nz/dx/dy/dz`), timing (`timax/tapfrq/dtl/adapt_dt`), storm design (`isnd/iwnd/iinit/irandp/icor/imove/iorigin`), `seed` (semantic → `var7`, Phase 3 T4), microphysics (`ptype/ihail`), terrain (`terrain_flag/itern/stretch_z`) |
| **2. Geometry-derived** | computed by the generator | `dx_inner`, `dy_inner`, `tot_x_len`, `tot_y_len` |
| **3. Motion-coupled** | computed when `imove=0`, required when `imove=1` | `umove`, `vmove` |
| **4. Output block** | this template, verbatim | `&param9` |
| **5. Optional run-control** | JSON `sim.namelist`, optional; template default otherwise | `rstfrq`, `sbc`, `nbc` |
| **6. External sounding** | JSON `sim.sounding` → `input_sounding` file, NOT a namelist key | with `isnd=7` CM1 reads θ/qv/u/v from the file; deck.py requires the block ⇔ `isnd=7` and `iwnd=0`; `pipeline/gen_sounding.py` renders it (docs/plan-science-hurdles-2026-09-02.md) |

Scenario-identity keys are **required, never defaulted from the template** — so a
scenario that forgets one fails loudly instead of silently inheriting Phase 0's
supercell value.

## The output block is checked, not generated

Tempting and wrong: deriving `&param9` from `contract.SOURCE_FIELDS`. The validated
deck writes considerably more than the exporter reads (`tke`, `km`/`kh`, `uh`,
`vort`, `lcl`/`lfc`/`pwat`), and the validation and analysis scripts use those
extras. Generating the block from the contract would quietly shrink the deck and
break the reproduction gate.

Instead the contract is an **assertion** (`deck.check_output_flags`): `output_q`,
`output_dbz` and `output_winterp` must be on, or generation refuses. That catches
the failure mode where a run burns hours and only then turns out to have written no
`dbz`.

## Editing rules

- Substitution is **line-anchored** (`^\s*KEY\s*=`). This is not incidental: an
  unanchored `dz` match also hits `dz_bot` and `dz_top`, and `dx` hits
  `dx_inner`/`dx_outer`. The result still runs — it just isn't the simulation you
  asked for. Keep one key per line so the anchor holds.
- Do not add a key here that a scenario should own; add it to `REQUIRED_KEYS` in
  `deck.py` and to every scenario JSON, so the generator fails loudly on omission.
- After editing, re-run the T1c gate above. It compares by **parsed value**, modulo
  comments and key ordering — the hand-written decks are not column-consistent
  (` ptype     =  5,` vs ` ptype     =  27,`), so a byte gate would fail on
  whitespace while proving nothing about the physics.
