# pipeline/vdbwriter/ — dense-array → multi-grid OpenVDB converter

Standalone C++ tools the Python pipeline shells out to. This is the pipeline
README's **#1 (most robust)** VDB-writer path: link OpenVDB from a ~200-line C++
program rather than depend on flaky `pyopenvdb` wheels.

- **`dense2vdb`** — converts one `.densevol` frame → one `.vdb` (one FloatGrid per
  channel, all sharing one transform).
- **`vdb_inspect`** — independent read-back validator (replaces `vdb_print`, which
  the conda-forge OpenVDB package does **not** ship). Reports grid count, per-grid
  active voxels + active bbox, and asserts all grids share one transform.

Phase 1 uses these two ways:
1. **Now (risk-first):** convert *synthetic* storm frames (`gen_synthetic.py`) to
   prove the writer → UE SVT link before real CM1 data exists.
2. **Later:** the real Python pipeline emits `.densevol` frames from regridded CM1
   netCDF and calls `dense2vdb` per frame.

## Toolchain — userspace conda-forge OpenVDB (no sudo)

The build links a **userspace** OpenVDB installed with `micromamba` — no
`apt`/`sudo`. (The apt `libopenvdb-dev` path was abandoned: it needs interactive
root, and the package's `vdb_print`/tooling split differs by distro. micromamba
installs the whole C++ toolchain into `$HOME` with zero privilege.)

**Working toolchain (PIN LOCKED — round-trip CONFIRMED against UE 5.8, task 3):**
- **conda-forge `openvdb` 13.0.0** — the lib the converters link against.
- `cmake` 4.x, `cxx-compiler` (gcc/g++ 14), `tbb-devel`, `libboost-devel`, `zlib`
  (OpenVDB's configure-time header deps).
- env python: 3.14 (only used to run `gen_synthetic.py`).

> **Format-version compat CONFIRMED (2026-07-14):** UE 5.8 bundles
> **`openvdb-13.0.0`** at
> `W:\UE_5.8\Engine\Source\ThirdParty\OpenVDB\Deploy\openvdb-13.0.0`, whose
> `version.h` declares the identical **`OPENVDB_FILE_VERSION = 225`** that these
> tools write. Same serializer version + same Blosc compression ⇒ UE's reader
> decodes exactly what the writer emits; there is no version skew to fear. This is
> dispositive at the *file-format* layer and answers the narrow "does v225 read"
> question **without UE running**.
>
> **Empirical round-trip CONFIRMED (2026-07-14, task 3 —
> `docs/phase1-task3-svt-import.md`):** UE 5.8's `USparseVolumeTextureFactory`
> imported the full 300-frame v225 sequence *headless* into a 300-frame
> `AnimatedSparseVolumeTexture` (160×160×64; Tex A RGBA16F = cloud/ice/rain/
> graupelhail, Tex B R16F = dbz) in 21 s, with the default grid assignment
> reproducing the `docs/phase1-svt-budget.md` channel map exactly. The pin is now
> **locked**, not merely header-matched. The only remaining check is *visual
> streaming playback* in the editor (owner-gated — see the task-3 doc's Handoff).

One-time env setup (inside WSL Ubuntu; `~/bin/micromamba` already present):

```bash
export MAMBA_ROOT_PREFIX=$HOME/micromamba
~/bin/micromamba create -y -n vdb -c conda-forge \
    openvdb cmake cxx-compiler tbb-devel libboost-devel zlib
```

## Build

```bash
# inside WSL, from an ext4 checkout (or point -S at the /mnt/m source):
./build.sh          # cmake + make -> build/dense2vdb , build/vdb_inspect
```

`build.sh` auto-discovers the `vdb` env and passes OpenVDB's `FindOpenVDB.cmake`
(module mode) via `-DCMAKE_MODULE_PATH`/`-DCMAKE_PREFIX_PATH`. The binaries link
the env's shared libs, so **run them with the env lib dir on `LD_LIBRARY_PATH`**
(or via `micromamba run -n vdb`):

```bash
export LD_LIBRARY_PATH=$HOME/micromamba/envs/vdb/lib
./build/dense2vdb in.densevol out.vdb
./build/vdb_inspect out.vdb
```

## Synthetic end-to-end test (no CM1, no UE needed)

```bash
# 1. generate 300 frames (160x160x64 @ 250 m; stationary centered cell)
micromamba run -n vdb python3 gen_synthetic.py --out synthetic_seq --frames 300

# 2. convert all frames (inside WSL a plain loop just works — the shell-var /
#    leading-slash traps below are Git-Bash→WSL bridge artifacts, not native WSL)
export LD_LIBRARY_PATH=$HOME/micromamba/envs/vdb/lib
for f in synthetic_seq/frame_*.densevol; do ./build/dense2vdb "$f" "${f%.densevol}.vdb"; done

# 3. validate a mature-phase frame
./build/vdb_inspect synthetic_seq/frame_00133.vdb
```

`vdb_inspect` should list **5 FloatGrids** (`cloud`, `ice`, `rain`, `graupelhail`,
`dbz`), each `fog volume`, all sharing one linear transform (250 m voxel, origin
[0,0,0]), each with a nonzero active count — and print `OK: all grids share one
transform`. The active fraction `dense2vdb` prints per grid is the real sparsity
that drives SVT frame size (cross-check against `docs/phase1-svt-budget.md`).

### Validated (2026-07-14)

Full 300-frame synthetic run, **0 failures**:
- **peak frame = `frame_00133` at 5.92 MB** VDB-on-disk — the SVT-budget stress
  frame; mean 3.43 MB/frame; sequence total **1.03 GB** VDB on disk.
- **What this validates about the budget:** the load-bearing assumption in
  `docs/phase1-svt-budget.md` is the **~35 % active-voxel sparsity** figure. Measured
  peak fractions **cloud 37.2 % / ice 42.7 %** bracket it, and every frame sits far
  under the 30–50 MB/frame streaming ceiling with order-of-magnitude headroom.
- **What this does NOT verify:** the 5.92 MB VDB *file* (blosc-compressed 4-byte
  floats + tree topology) is a **different quantity** from the doc's ~5.7 MB fp16
  SVT *texture memory* (10 B/active-voxel) — their closeness is coincidental. The
  **binding** per-frame test is task 5's *real* CM1 frames, which spread wider
  (cold-pool secondary cells — see `sim/single_cell/README.md`).
- **On-disk format:** these VDBs are **file-format version 225** (writer lib
  openvdb 13.0). **Task 3 confirmed** UE 5.8 reads v225 and built a 300-frame
  animated SVT from this sequence (`docs/phase1-task3-svt-import.md`); the openvdb
  pin is now **locked**.

## `.densevol` format (little-endian)

```
char   magic[4] = "DVOL"
uint32 version  = 1
uint32 nx, ny, nz
uint32 nchannels
float  voxel_size_m                       (isotropic)
float  origin_x_m, origin_y_m, origin_z_m (world coords of voxel (0,0,0))
per channel:
  uint32 name_len
  char   name[name_len]
  float  threshold                        (|v| <= threshold -> inactive)
  float  data[nx*ny*nz]                    (index = x + nx*(y + ny*z))
```

## Design notes

- **One shared transform** across all grids in a frame (UE SVT requires it).
  `voxel_size` + `origin` are identical across channels *and* frames; the caller
  pads a fixed box so the bbox center is static across the sequence.
- **Thresholding = sparsity.** Voxels at/below a channel's threshold stay
  background and never allocate — this is what keeps the SVT under budget.
- Channel names are the format contract (`docs/phase1-svt-budget.md`). The manifest
  records the channel→SVT-texture mapping; UE reads it, never hardcodes it.
- Endianness is native x86 (WSL). Not portable to big-endian — fine, we only ever
  run this in WSL Ubuntu.

## WSL-invocation gotcha (Git Bash bridge)

Driving WSL from the Windows Git-Bash tool has two traps that silently waste time:
1. **A `bash -lc '…'` string must not *start* with `/`** — MSYS path-conversion
   rewrites a leading-slash arg into `C:/Program Files/Git/…`. Prefix with a
   harmless token (`cd /home/boiko; …`).
2. **Shell variables inside inline `-lc '…'` are unreliable** (`$f` in a loop can
   come back empty). Put any real looping/variables in a **script file on disk**
   (or a Python driver) and invoke that; don't build multi-step logic in the inline
   string.

## Not committed

`build/`, `*.densevol`, and `*.vdb` are generated/large — git-ignored. Batch
conversion is driven by a scratch Python script (not part of the shipped pipeline;
the real pipeline calls `dense2vdb` per frame from Python — task 5).
