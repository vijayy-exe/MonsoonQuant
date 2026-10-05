cmake_minimum_required(VERSION 3.26)
project(mq_core_sim LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Python 3.12 COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

# Apple Clang ships no OpenMP runtime of its own — find_package(OpenMP)
# fails silently on macOS unless pointed at Homebrew's libomp (a
# well-known CMake/macOS gotcha, not specific to this project).
if(APPLE)
  execute_process(
    COMMAND brew --prefix libomp
    OUTPUT_VARIABLE LIBOMP_PREFIX
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
  )
  if(LIBOMP_PREFIX AND EXISTS "${LIBOMP_PREFIX}/include/omp.h")
    set(OpenMP_C_FLAGS "-Xpreprocessor -fopenmp -I${LIBOMP_PREFIX}/include")
    set(OpenMP_CXX_FLAGS "-Xpreprocessor -fopenmp -I${LIBOMP_PREFIX}/include")
    set(OpenMP_C_LIB_NAMES "omp")
    set(OpenMP_CXX_LIB_NAMES "omp")
    set(OpenMP_omp_LIBRARY "${LIBOMP_PREFIX}/lib/libomp.dylib")
  endif()
endif()
find_package(OpenMP)

pybind11_add_module(mq_core_sim bindings/module.cpp src/simulate.cpp)
target_include_directories(mq_core_sim PRIVATE include)

if(OpenMP_CXX_FOUND)
  target_link_libraries(mq_core_sim PRIVATE OpenMP::OpenMP_CXX)
else()
  message(WARNING "OpenMP not found — building mq_core_sim single-threaded")
endif()

install(TARGETS mq_core_sim DESTINATION .)

# core/tests/test_rng.cpp is a plain executable (no Python/pybind11
# involvement, no OpenMP needed) — built only when this project is
# configured directly, not part of the wheel scikit-build-core ships.
add_executable(test_rng tests/test_rng.cpp)
target_include_directories(test_rng PRIVATE include)
