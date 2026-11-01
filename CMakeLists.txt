cmake_minimum_required(VERSION 3.25)
project(Krose VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
option(SEGRAND_BUILD_PLUGIN "Build iPlug2 VST3 and standalone app" ON)
option(SEGRAND_BUILD_TOOLS "Build offline renderer and engine benchmark" ON)
option(SEGRAND_SANITIZE "Enable address/undefined sanitizers for engine checks" OFF)
if(SEGRAND_SANITIZE)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()
include(CTest)
include(cmake/RuntimeAssets.cmake)
set(SEGRAND_ASSET_DIR "${CMAKE_SOURCE_DIR}/assets/concert-se-grand" CACHE PATH "Frozen runtime asset bundle")
segrand_check_asset_bundle("${SEGRAND_ASSET_DIR}")
set(SEGRAND_GENERATED "${CMAKE_BINARY_DIR}/generated")
add_custom_command(OUTPUT "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/ConcertEqData.h" "${SEGRAND_GENERATED}/assets.json"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${SEGRAND_GENERATED}"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${SEGRAND_ASSET_DIR}/SEGrand.samples" "${SEGRAND_GENERATED}/SEGrand.samples"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${SEGRAND_ASSET_DIR}/ConcertEqData.h" "${SEGRAND_GENERATED}/ConcertEqData.h"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${SEGRAND_ASSET_DIR}/assets.json" "${SEGRAND_GENERATED}/assets.json"
  DEPENDS "${SEGRAND_ASSET_DIR}/SEGrand.samples" "${SEGRAND_ASSET_DIR}/ConcertEqData.h" "${SEGRAND_ASSET_DIR}/assets.json"
  VERBATIM)
add_custom_target(segrand-assets DEPENDS "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/ConcertEqData.h")
add_custom_command(OUTPUT "${SEGRAND_GENERATED}/NativeVoiceData.h" "${SEGRAND_GENERATED}/voice-assets.json"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${SEGRAND_GENERATED}"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${SEGRAND_ASSET_DIR}/NativeVoiceData.h" "${SEGRAND_GENERATED}/NativeVoiceData.h"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${SEGRAND_ASSET_DIR}/voice-assets.json" "${SEGRAND_GENERATED}/voice-assets.json"
  DEPENDS "${SEGRAND_ASSET_DIR}/NativeVoiceData.h" "${SEGRAND_ASSET_DIR}/voice-assets.json"
  VERBATIM)
add_custom_target(segrand-voice-assets DEPENDS "${SEGRAND_GENERATED}/NativeVoiceData.h")
# Frozen factory starter assets are an explicit offline handoff, not a firmware build step.
set(KROSE_FACTORY_ASSET_DIR "${CMAKE_SOURCE_DIR}/assets/factory-starter" CACHE PATH "Frozen shared factory library")
segrand_check_asset_bundle("${KROSE_FACTORY_ASSET_DIR}")
add_custom_command(OUTPUT "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/FactoryPrograms.h"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${SEGRAND_GENERATED}"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${KROSE_FACTORY_ASSET_DIR}/Factory.samples" "${SEGRAND_GENERATED}/Factory.samples"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.h" "${SEGRAND_GENERATED}/FactoryPrograms.h"
  DEPENDS "${KROSE_FACTORY_ASSET_DIR}/Factory.samples" "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.h" VERBATIM)
add_custom_target(krose-factory-assets DEPENDS "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/FactoryPrograms.h")
add_library(segrand-engine STATIC src/instrument/ProgramLibrary.cpp src/instrument/ProgramEngine.cpp src/instrument/InstrumentEngine.cpp src/instrument/PianoEngine.cpp src/instrument/NativeVoice.cpp src/instrument/NativeFilter.cpp src/dsp/concert_effects.c)
add_dependencies(segrand-engine segrand-assets segrand-voice-assets krose-factory-assets)
set_target_properties(segrand-engine PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(segrand-engine PUBLIC src/instrument src/dsp "${SEGRAND_GENERATED}")
target_compile_options(segrand-engine PRIVATE -Wall -Wextra -Werror)
if(BUILD_TESTING)
set(SEGRAND_FIXTURE_DIR "${CMAKE_SOURCE_DIR}/tests/fixtures/concert-se-grand")
segrand_check_asset_bundle("${SEGRAND_FIXTURE_DIR}")
add_executable(test-program-engine tests/test_program_engine.cpp)
target_link_libraries(test-program-engine PRIVATE segrand-engine)
target_compile_options(test-program-engine PRIVATE -UNDEBUG)
add_test(NAME program-engine COMMAND test-program-engine "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/SEGrand.samples")
add_executable(test-piano-engine tests/test_piano_engine.cpp)
target_link_libraries(test-piano-engine PRIVATE segrand-engine)
target_compile_options(test-piano-engine PRIVATE -UNDEBUG)
add_test(NAME piano-engine COMMAND test-piano-engine "${SEGRAND_GENERATED}/SEGrand.samples")
add_executable(test-native-voice tests/test_native_voice.cpp)
target_link_libraries(test-native-voice PRIVATE segrand-engine)
target_compile_options(test-native-voice PRIVATE -UNDEBUG)
add_test(NAME native-voice COMMAND test-native-voice
  "${SEGRAND_FIXTURE_DIR}/concert-control-map.bin"
  "${SEGRAND_FIXTURE_DIR}/native-voice-traces.bin" "${SEGRAND_FIXTURE_DIR}/native-tg-commands.bin")
add_executable(test-native-filter tests/test_native_filter.cpp)
target_link_libraries(test-native-filter PRIVATE segrand-engine)
target_compile_options(test-native-filter PRIVATE -UNDEBUG)
add_test(NAME native-filter COMMAND test-native-filter
  "${SEGRAND_FIXTURE_DIR}/concert-filter-map.bin"
  "${SEGRAND_FIXTURE_DIR}/concert-filter-traces.bin")
endif()
if(SEGRAND_BUILD_TOOLS)
add_executable(render-program tools/render_program.cpp)
target_link_libraries(render-program PRIVATE segrand-engine)
add_executable(benchmark-program tools/benchmark_program.cpp)
target_link_libraries(benchmark-program PRIVATE segrand-engine)
add_executable(render-piano tools/render_piano.cpp)
target_link_libraries(render-piano PRIVATE segrand-engine)
add_executable(benchmark-piano tools/benchmark_piano.cpp)
target_link_libraries(benchmark-piano PRIVATE segrand-engine)
endif()

if(SEGRAND_BUILD_PLUGIN)
  set(IPLUG2_DIR "${CMAKE_SOURCE_DIR}/build/deps/iPlug2" CACHE PATH "Pinned iPlug2 source checkout")
  if(NOT EXISTS "${IPLUG2_DIR}/iPlug2.cmake")
    message(FATAL_ERROR "Run python3 tools/bootstrap_plugin.py to fetch the pinned dependencies")
  endif()
  set(IPLUG_DEPLOY_PLUGINS OFF CACHE BOOL "Keep plugin outputs inside build/out")
  set(IGRAPHICS_BACKEND "NANOVG" CACHE STRING "Drawing backend")
  set(IGRAPHICS_RENDERER "METAL" CACHE STRING "Drawing renderer")
  include("${IPLUG2_DIR}/iPlug2.cmake")
  find_package(iPlug2 REQUIRED)
  add_subdirectory(src/plugin)
  if(APPLE AND BUILD_TESTING)
    include(cmake/VST3Tests.cmake)
  endif()
endif()
