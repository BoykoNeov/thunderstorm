# Probes

Throwaway diagnostic runs — **not** shippable scenarios. Nothing here produces a
scenario package; `sim/scenarios/` is for configs that can be exported, and a probe
config in there would be a config that `export_scenario.py` cannot honour.

## Why the configs are tracked

`docs/phase3-t5-multicell.md` §§7, 9 and 11 rest on six 1 km runs. Per the T4
finding, **the namelist is CM1's sole scenario input** (`isnd=5` computes the WK
sounding internally), and these configs are the sole input to the namelist
generator — so config + `pipeline/` + the pinned fork binary is the whole recovery
path for every number in those sections. The run directories are large and
disposable; these six files are ~15 KB and are what makes the record reproducible.
That is the same argument the charter's data policy makes for scenario packages.

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
