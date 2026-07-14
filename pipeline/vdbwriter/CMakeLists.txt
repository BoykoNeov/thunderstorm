cmake_minimum_required(VERSION 3.16)
project(dense2vdb CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Ubuntu 24.04 (noble): libopenvdb-dev 10.0.1 ships an OpenVDBConfig.cmake.
find_package(OpenVDB QUIET)

add_executable(dense2vdb dense2vdb.cpp)

if(OpenVDB_FOUND)
  target_link_libraries(dense2vdb PRIVATE OpenVDB::openvdb)
else()
  # Fallback: link the system shared libs directly (apt layout).
  message(STATUS "OpenVDBConfig.cmake not found; linking system libs directly")
  find_library(OPENVDB_LIB openvdb REQUIRED)
  find_package(TBB REQUIRED)
  target_link_libraries(dense2vdb PRIVATE ${OPENVDB_LIB} TBB::tbb)
endif()
