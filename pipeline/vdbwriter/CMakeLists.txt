cmake_minimum_required(VERSION 3.16)
project(dense2vdb CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# OpenVDB toolchain: this project builds against a userspace conda-forge OpenVDB
# installed with micromamba (NO sudo/apt needed) — see build.sh and README.md.
# The env ships FindOpenVDB.cmake (module mode) under
# $CONDA_PREFIX/lib/cmake/OpenVDB, so build.sh passes:
#   -DCMAKE_MODULE_PATH=$CONDA_PREFIX/lib/cmake/OpenVDB
#   -DCMAKE_PREFIX_PATH=$CONDA_PREFIX
# NOTE (pending UE validation): the working toolchain is conda-forge openvdb
# 13.0.0. This is NOT yet a locked version pin in CLAUDE.md — it stays "working,
# pending UE SVT round-trip" until task #3 confirms UE 5.8's SVT importer reads
# these files. OpenVDB's on-disk file-format version can outrun an older reader.
find_package(OpenVDB QUIET)

foreach(tool dense2vdb vdb_inspect)
  add_executable(${tool} ${tool}.cpp)
  if(OpenVDB_FOUND)
    target_link_libraries(${tool} PRIVATE OpenVDB::openvdb)
  else()
    # Fallback: link the shared libs directly (e.g. an apt/system layout).
    message(STATUS "OpenVDBConfig.cmake not found; linking libs directly")
    find_library(OPENVDB_LIB openvdb REQUIRED)
    find_package(TBB REQUIRED)
    target_link_libraries(${tool} PRIVATE ${OPENVDB_LIB} TBB::tbb)
  endif()
endforeach()
