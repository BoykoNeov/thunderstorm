// dense2vdb — standalone dense-array -> multi-grid OpenVDB converter.
//
// The Python pipeline shells out to this (pipeline/README.md ranks a standalone
// C++ converter as the most robust VDB-writer path). It reads one ".densevol"
// file (one storm frame, N named channels) and writes one ".vdb" holding one
// FloatGrid per channel. Only voxels above each channel's threshold become
// active, which is what gives the Sparse Volume Texture its sparsity.
//
// All grids share ONE transform object (UE SVT requires all grids share one
// transform). Voxel size + origin are identical across channels and frames; the
// caller pads a fixed box so the bbox center is static across the sequence.
//
// .densevol format (little-endian; x86/WSL native):
//   char   magic[4]      = "DVOL"
//   uint32 version       = 1
//   uint32 nx, ny, nz
//   uint32 nchannels
//   float  voxel_size_m           (isotropic)
//   float  origin_x_m, origin_y_m, origin_z_m   (world coords of voxel (0,0,0))
//   then, per channel:
//     uint32 name_len
//     char   name[name_len]
//     float  threshold            (|value| <= threshold => inactive background)
//     float  data[nx*ny*nz]       (index = x + nx*(y + ny*z))
//
// Build: see build.sh / CMakeLists.txt (links userspace conda-forge OpenVDB via
// micromamba — no sudo). Validate output with the vdb_inspect sibling tool.
// Usage: dense2vdb input.densevol output.vdb

#include <openvdb/openvdb.h>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

template <typename T>
bool readPod(std::istream& is, T& out) {
    return static_cast<bool>(is.read(reinterpret_cast<char*>(&out), sizeof(T)));
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: dense2vdb input.densevol output.vdb\n";
        return 2;
    }
    const std::string inPath = argv[1];
    const std::string outPath = argv[2];

    std::ifstream in(inPath, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open " << inPath << "\n";
        return 1;
    }

    char magic[4];
    if (!in.read(magic, 4) || std::memcmp(magic, "DVOL", 4) != 0) {
        std::cerr << "error: bad magic (not a .densevol file)\n";
        return 1;
    }
    uint32_t version = 0, nx = 0, ny = 0, nz = 0, nchannels = 0;
    float voxel = 0.f, ox = 0.f, oy = 0.f, oz = 0.f;
    if (!readPod(in, version) || version != 1u) {
        std::cerr << "error: unsupported version\n";
        return 1;
    }
    readPod(in, nx); readPod(in, ny); readPod(in, nz); readPod(in, nchannels);
    readPod(in, voxel); readPod(in, ox); readPod(in, oy); readPod(in, oz);
    if (!in || nx == 0 || ny == 0 || nz == 0 || nchannels == 0 || voxel <= 0.f) {
        std::cerr << "error: invalid header\n";
        return 1;
    }

    const size_t voxelsPerChannel = static_cast<size_t>(nx) * ny * nz;

    openvdb::initialize();

    // ONE shared transform for every grid (SVT requirement). world = voxel*index + origin.
    openvdb::math::Transform::Ptr xform =
        openvdb::math::Transform::createLinearTransform(static_cast<double>(voxel));
    xform->postTranslate(openvdb::Vec3d(ox, oy, oz));

    openvdb::GridPtrVec grids;
    std::vector<float> data(voxelsPerChannel);

    for (uint32_t c = 0; c < nchannels; ++c) {
        uint32_t nameLen = 0;
        if (!readPod(in, nameLen) || nameLen == 0 || nameLen > 256) {
            std::cerr << "error: bad channel name length\n";
            return 1;
        }
        std::string name(nameLen, '\0');
        if (!in.read(&name[0], nameLen)) {
            std::cerr << "error: truncated channel name\n";
            return 1;
        }
        float threshold = 0.f;
        readPod(in, threshold);
        if (!in.read(reinterpret_cast<char*>(data.data()),
                     static_cast<std::streamsize>(voxelsPerChannel * sizeof(float)))) {
            std::cerr << "error: truncated channel data for '" << name << "'\n";
            return 1;
        }

        openvdb::FloatGrid::Ptr grid = openvdb::FloatGrid::create(/*background=*/0.0f);
        grid->setName(name);
        grid->setTransform(xform);  // shared pointer -> all grids share one transform
        grid->setGridClass(openvdb::GRID_FOG_VOLUME);

        openvdb::FloatGrid::Accessor acc = grid->getAccessor();
        size_t active = 0;
        for (uint32_t z = 0; z < nz; ++z) {
            for (uint32_t y = 0; y < ny; ++y) {
                const size_t rowBase = static_cast<size_t>(nx) * (y + static_cast<size_t>(ny) * z);
                for (uint32_t x = 0; x < nx; ++x) {
                    const float v = data[rowBase + x];
                    if (std::fabs(v) > threshold) {
                        acc.setValue(openvdb::Coord(static_cast<int>(x),
                                                    static_cast<int>(y),
                                                    static_cast<int>(z)),
                                     v);
                        ++active;
                    }
                }
            }
        }
        grid->pruneGrid();
        std::cerr << "  grid '" << name << "': " << active << "/" << voxelsPerChannel
                  << " active (" << (100.0 * active / voxelsPerChannel) << "%)\n";
        grids.push_back(grid);
    }

    openvdb::io::File file(outPath);
    file.write(grids);
    file.close();
    std::cerr << "wrote " << grids.size() << " grids -> " << outPath << "\n";
    return 0;
}
