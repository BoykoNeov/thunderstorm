// vdb_inspect — minimal independent read-back validator for the .vdb files
// dense2vdb writes. conda-forge openvdb ships no `vdb_print` CLI, so this is the
// stand-in: it re-opens a .vdb with the OpenVDB library and reports structure so
// the pipeline can assert the writer produced what the UE SVT contract requires
// (docs/phase1-svt-budget.md): a fixed set of FloatGrids, ALL sharing ONE linear
// transform (same voxel size + same origin), each with a nonzero active count.
//
// IMPORTANT / scope: this reads with the SAME openvdb build that wrote the file,
// so a clean report proves the *writer* is self-consistent — it does NOT prove
// UE 5.8's SVT importer accepts these files. That round-trip is task #3 and is
// the only thing that can bless the openvdb version pin. Keep this tool minimal;
// it is validation infra, not a deliverable.
//
// Usage: vdb_inspect file.vdb
// Exit:  0 = read OK and all grids share one transform
//        1 = I/O / parse error
//        3 = transforms differ across grids (SVT contract violation)

#include <openvdb/openvdb.h>
#include <iomanip>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: vdb_inspect file.vdb\n";
        return 1;
    }
    const std::string path = argv[1];

    openvdb::initialize();

    openvdb::io::File file(path);
    try {
        file.open();
    } catch (const std::exception& e) {
        std::cerr << "error: cannot open " << path << ": " << e.what() << "\n";
        return 1;
    }

    openvdb::GridPtrVecPtr grids = file.getGrids();
    // On-disk OpenVDB file-format version this .vdb carries (uint, e.g. 224). This
    // is THE number the pending openvdb-pin question hinges on: task #3 asks
    // whether UE 5.8's bundled OpenVDB can read files of this format version.
    const uint32_t fileVer = file.fileVersion();
    const openvdb::VersionId libVer = file.libraryVersion();
    file.close();

    if (!grids || grids->empty()) {
        std::cerr << "error: no grids in " << path << "\n";
        return 1;
    }

    std::cout << path << ": " << grids->size() << " grid(s)"
              << "  fileFormatVersion=" << fileVer
              << "  writerLib=" << libVer.first << "." << libVer.second << "\n";

    // Reference transform = first grid's; every other grid must match it exactly
    // (same voxel size AND same origin) to satisfy the SVT one-transform rule.
    bool haveRef = false;
    openvdb::Vec3d refVoxel, refTranslate;
    bool transformsMatch = true;

    for (const openvdb::GridBase::Ptr& g : *grids) {
        const openvdb::math::Transform& xform = g->transform();
        const openvdb::Vec3d voxel = xform.voxelSize();
        // world origin of index (0,0,0)
        const openvdb::Vec3d translate = xform.indexToWorld(openvdb::Vec3d(0, 0, 0));

        openvdb::Index64 activeVoxels = g->activeVoxelCount();
        openvdb::CoordBBox bbox = g->evalActiveVoxelBoundingBox();

        std::cout << "  grid '" << g->getName() << "'"
                  << "  type=" << g->valueType()
                  << "  class=" << openvdb::GridBase::gridClassToString(g->getGridClass())
                  << "\n"
                  << "      active=" << activeVoxels
                  << "  voxelSize=" << voxel
                  << "  origin=" << translate
                  << "\n"
                  << "      activeBBox=" << bbox.min() << " .. " << bbox.max()
                  << "\n";

        if (activeVoxels == 0) {
            std::cerr << "  WARN: grid '" << g->getName() << "' has 0 active voxels\n";
        }

        if (!haveRef) {
            refVoxel = voxel;
            refTranslate = translate;
            haveRef = true;
        } else {
            if (!voxel.eq(refVoxel) || !translate.eq(refTranslate)) {
                transformsMatch = false;
            }
        }
    }

    if (!transformsMatch) {
        std::cerr << "FAIL: grids do NOT share one transform (SVT contract violation)\n";
        return 3;
    }
    std::cout << "OK: all grids share one transform"
              << " (voxelSize=" << refVoxel << " origin=" << refTranslate << ")\n";
    return 0;
}
