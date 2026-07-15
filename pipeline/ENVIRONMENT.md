# Pipeline environment (the "Python env lockfile", Phase 1)

Recorded 2026-07-15, from the WSL2 Ubuntu box that produced the task 5 package
(`docs/phase1-task5-pipeline.md`). These are the versions the 301-frame single-cell
export **actually ran on**.

There are **two separate environments**, and conflating them is the mistake this file
exists to prevent. They do not share an interpreter.

## 1. Pipeline runtime — system apt Python

`export_scenario.py` and `cm1post/` run on Ubuntu's **system** `python3`. There is no
venv and no pip: `/usr/lib/python3.12/EXTERNALLY-MANAGED` is present and `pip list` is
empty. Every dependency comes from apt.

| Package | Version |
|---|---|
| distro | Ubuntu **24.04.4 LTS** (WSL2) |
| `python3` | **3.12.3**-0ubuntu2.1 |
| `python3-numpy` | **1:1.26.4**+ds-6ubuntu1 |
| `python3-scipy` | **1.11.4**-6build1 |
| `python3-netcdf4` | **1.6.5**-1build3 |
| `python3-matplotlib` | 3.6.3-1ubuntu5 — *installed, not yet load-bearing* (see below) |

**There is deliberately no `requirements.txt`.** Pinning `numpy==1.26.4` in a pip file
would advertise a `pip install -r` reproducibility that does not exist against this
interpreter — it fails, or demands `--break-system-packages`, which is the opposite of a
lock. The apt version strings above *are* the lock: they reconstruct on Ubuntu 24.04,
which is why the distro release is recorded with them and not as a footnote.

`matplotlib` is present because Phase 0 used it for validation plots. The pipeline does
**not** import it, and MetPy is not installed — skew-T/hodograph rendering is Phase 2/4.
Treat that row as aspirational, not as part of the proven stack.

## 2. VDB writer — micromamba conda-forge `vdb` env

Full export: **`env-vdb.yml`** (`micromamba env export -n vdb`, version + build strings).
Key pins:

| Package | Version | Build |
|---|---|---|
| `openvdb` | **13.0.0** | `py314h72130fb_3` |
| `python` | **3.14.6** | `habeac84_100_cp314` |
| `libboost` | 1.90.0 | `hd24cca6_1` |
| `tbb` | 2023.0.0 | `hab88423_2` |
| `blosc` | 1.21.6 | `he440d0b_1` |
| `zlib` | 1.3.2 | `h25fd6f3_2` |
| gcc / gxx | 14.3.0 | |
| micromamba | 2.8.1 | userspace, no sudo |

Two things worth being explicit about:

- **This env's Python (3.14.6) is *not* the pipeline's Python (3.12.3).** It is an
  artifact of how conda-forge builds the `openvdb` package. Nothing in `cm1post/` runs on
  3.14 — the two interpreters never meet, because the handoff between them is a file
  (`.densevol`) and a subprocess, not an import.
- **The env is a *runtime* dependency of `export`, not just a build-time one.**
  `dense2vdb` dynamically links `$HOME/micromamba/envs/vdb/lib` (openvdb, tbb, blosc,
  boost, zlib), which is why `pipeline/README.md` has you `export LD_LIBRARY_PATH` before
  exporting. The "no OpenVDB Python binding" claim stays true — there is no Python
  *import* — but the shared libraries are load-bearing at export time.

`env-vdb.yml`'s trailing `prefix:` is this machine's path; `micromamba` ignores it on
create.

## Scope of this record

This is a **spike-grade lock**: it records the versions that are true, in each env's
native form, so the task 5 package is reconstructable. It is not a hardened,
byte-reproducible lock — that would want `micromamba env export --explicit` (URL-pinned)
plus an apt pin manifest. Deliberately deferred: it is Phase 2 hardening, and the light
version does not foreclose it.
