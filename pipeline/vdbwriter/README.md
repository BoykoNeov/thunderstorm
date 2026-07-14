# pipeline/vdbwriter/ — dense-array → multi-grid OpenVDB converter

Standalone C++ tool the Python pipeline shells out to. This is the pipeline
README's **#1 (most robust)** VDB-writer path: link the system OpenVDB from a
~200-line C++ program rather than depend on flaky `pyopenvdb` wheels.

Phase 1 uses it two ways:
1. **Now (risk-first):** convert *synthetic* storm frames (`gen_synthetic.py`)
   to prove the writer → UE SVT link before real CM1 data exists.
2. **Later:** the real Python pipeline emits `.densevol` frames from regridded
   CM1 netCDF and calls `dense2vdb` per frame.

## Toolchain (pinned target: Ubuntu 24.04 / noble)

- `libopenvdb-dev` **10.0.1-2.1build5** (apt, noble/universe) — the OpenVDB the
  converter links against. **This is the OpenVDB pin candidate for CLAUDE.md**
  (confirm after the build validates).
- `openvdb-tools` — provides `vdb_print` for validation.
- `cmake`, `g++` (13.3.0 present).

Install (once; needs sudo — run it yourself):

```bash
sudo apt-get update
sudo apt-get install -y libopenvdb-dev openvdb-tools cmake g++
```

## Build

```bash
./build.sh          # cmake + make -> build/dense2vdb
```

## Synthetic end-to-end test (no CM1, no UE needed)

```bash
python3 gen_synthetic.py --out synthetic_seq            # 300 frames, 160x160x64 @250 m
for f in synthetic_seq/frame_*.densevol; do
  ./build/dense2vdb "$f" "${f%.densevol}.vdb"
done
vdb_print -l synthetic_seq/frame_00150.vdb              # inspect a mature-phase frame
```

`vdb_print -l` should list 5 FloatGrids (`cloud`, `ice`, `rain`, `graupelhail`,
`dbz`), each with a shared linear transform (250 m voxel) and a nonzero active
voxel count. Active fraction printed by `dense2vdb` per grid is the real sparsity
that drives the SVT frame size (cross-check against docs/phase1-svt-budget.md).

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
- Channel names are the format contract (docs/phase1-svt-budget.md). The manifest
  records the channel→SVT-texture mapping; UE reads it, never hardcodes it.
- Endianness is native x86 (WSL). Not portable to big-endian — fine, we only ever
  run this in WSL Ubuntu.

## Not committed

`build/`, `*.densevol`, and `*.vdb` are generated/large — git-ignored.
