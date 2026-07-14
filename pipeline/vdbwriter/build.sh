#!/usr/bin/env bash
# Build dense2vdb + vdb_inspect inside WSL Ubuntu against a USERSPACE conda-forge
# OpenVDB (no sudo/apt). One-time env setup (see README.md for detail):
#   ~/bin/micromamba create -y -n vdb -c conda-forge \
#       openvdb cmake cxx-compiler tbb-devel libboost-devel zlib
# Working toolchain: conda-forge openvdb 13.0.0 (pending UE SVT round-trip
# validation before it becomes a locked CLAUDE.md pin — see README.md).
# Run from pipeline/vdbwriter/ inside WSL (ext4 path, not /mnt/*).
set -euo pipefail

: "${MAMBA_ROOT_PREFIX:=$HOME/micromamba}"
export MAMBA_ROOT_PREFIX
ENV_PREFIX="${MAMBA_ROOT_PREFIX}/envs/vdb"
if [[ ! -d "${ENV_PREFIX}" ]]; then
  echo "error: micromamba env 'vdb' not found at ${ENV_PREFIX}" >&2
  echo "       create it first (see the header comment / README.md)." >&2
  exit 1
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build="${here}/build"

# Configure/build with the env's compiler + OpenVDB's FindOpenVDB.cmake (module mode).
cmake -S "${here}" -B "${build}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_MODULE_PATH="${ENV_PREFIX}/lib/cmake/OpenVDB" \
  -DCMAKE_PREFIX_PATH="${ENV_PREFIX}"
cmake --build "${build}" -j"$(nproc)"

echo "built: ${build}/dense2vdb , ${build}/vdb_inspect"
echo "run via: '${HOME}/bin/micromamba run -n vdb ${build}/dense2vdb ...'"
echo "         (binaries link the env's shared libs — run them inside the env)"
