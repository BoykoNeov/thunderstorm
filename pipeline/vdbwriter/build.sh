#!/usr/bin/env bash
# Build dense2vdb inside WSL Ubuntu. Prereqs (install once, needs sudo):
#   sudo apt-get update
#   sudo apt-get install -y libopenvdb-dev openvdb-tools cmake g++
# Run from pipeline/vdbwriter/ inside WSL (ext4 path, not /mnt/*).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build="${here}/build"
cmake -S "${here}" -B "${build}" -DCMAKE_BUILD_TYPE=Release
cmake --build "${build}" -j"$(nproc)"
echo "built: ${build}/dense2vdb"
