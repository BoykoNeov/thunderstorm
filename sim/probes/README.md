# Probes

Throwaway diagnostic runs — **not** shippable scenarios. Nothing here produces a
scenario package; `sim/scenarios/` is for configs that can be exported, and a probe
config in there would be a config that `export_scenario.py` cannot honour.

## Why the configs are tracked

`docs/phase3-t5-multicell.md` §§7, 9 and 11 rest on six 1 km runs. Per the T4
finding, **the namelist is CM1's sole scenario input** (`isnd=5` computes the WK
sounding internally), and these configs are the sole input to the namelist
generator. The run directories are large and disposable; these six files are ~15 KB
and are what makes the record reproducible — the same argument the charter's data
policy makes for scenario packages.

**Measured claim, stated exactly:** config + `pipeline/` reproduces **the deck each
run used, byte-for-byte** (verified on all six). Reproducing the *run* additionally
needs the pinned fork binary `5fc93016…` **and the rank count**, because T4 banked
"same seed ⇒ bitwise identical" only *at fixed rank count* — and `nranks` is not a
config key. All six T5 probes ran at **`-np 4`**; each run's own `run_meta.txt`
records it, and that file is not tracked, so the number is written here.

| config | §2 role | key overrides |
|---|---|---|
| `t5probe_sc.json` | control — known supercell | `iwnd=2`, `imove=1` |
| `t5probe_pc.json` | control — known single pulse cell | `iwnd=0` |
| `t5probe_a.json` | candidate A | `iwnd=4` (CM1's own "multicell" profile) |
| `t5probe_b.json` | candidate B | `iwnd=1` (10 m/s bulk shear) |
| `t5probe_c.json` | candidate C — line thermal | `iwnd=1`, `iinit=8` |
| `t5probe_c2.json` | candidate C2 — C with periodic y | `iwnd=1`, `iinit=8`, `sbc=nbc=1` |

C2 differs from C in exactly two deck lines, both boundary keys (§10.3). All six
run `irandp=0` and the fork binary `5fc93016…`.

### T5s — external sounding (`isnd=7`), pre-registered 2026-09-02, NOT YET RUN

`docs/plan-science-hurdles-2026-09-02.md`. These configs carry a `sim.sounding` block;
`run_probe.sh`/`run_scenario.sh` generate `input_sounding` from it and record its
sha256. Each config's `provenance` records the BRN and the WK82 regime it PREDICTS,
computed from the sounding alone before any run (`test_sounding_t5s.py` gates that the
recorded prediction equals what the config's own sounding computes).

| config | role | environment | prediction |
|---|---|---|---|
| `t5s_neutral_pc.json` | control — PC re-run through the file path | WK82 14 g/kg, no wind | base state ≡ `t5probe_pc` (θ/qv to interpolation accuracy); same pulse cell |
| `t5s_neutral_a.json` | control — A re-run through the file path | WK82 + tanh U_s=35 | u0 ≡ `t5probe_a`'s (settles "wind from file, iwnd ignored"); same supercell |
| `t5s_us15.json` | sweep | WK82 + tanh U_s=15 (14.5 m/s 0–6 km) | BRN 59 → **multicell** |
| `t5s_us20.json` | sweep | WK82 + tanh U_s=20 (19.3 m/s) | BRN 33 → supercell |
| `t5s_us25.json` | sweep | WK82 + tanh U_s=25 (24.1 m/s) | BRN 21 → supercell |

The neutrality controls run FIRST and gate everything else: if `t5s_neutral_pc` does
not reproduce `t5probe_pc`'s base state, `isnd=7` is not what the plan believes and the
sweep is not run.

## Running one

```sh
bash sim/probes/run_probe.sh sim/probes/configs/t5probe_c2.json 4
```

Two at 4 ranks beats one at 8 on this machine (charter, "Wall-clock matters").

## Scoring

```sh
python3 sim/probes/classify_t5.py --only sc,pc          # controls first
python3 sim/probes/classify_t5.py --only sc,pc,a,b,c,c2
```

The classifier implements a **pre-registered** rule and no threshold in it may be
moved to make a candidate come out a particular way — see its docstring and the
doc's header. Its guards are gated by `pipeline/tests/test_classifier_t5.py`, which
needs no run data and must stay green.
