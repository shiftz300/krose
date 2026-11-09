set(IPLUG2_DIR "${CMAKE_SOURCE_DIR}/build/deps/iPlug2" CACHE PATH "Pinned iPlug2 source checkout")
if(NOT EXISTS "${IPLUG2_DIR}/iPlug2.cmake")
  message(FATAL_ERROR "Run python3 tools/bootstrap_plugin.py to fetch the pinned dependencies")
endif()
# Keep the verified download immutable. Compile a generated view with narrow,
# guarded portability/safety fixes; a changed patch set gets its own directory.
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(KROSE_PINNED_IPLUG2_DIR "${IPLUG2_DIR}")
set(_patcher "${CMAKE_SOURCE_DIR}/tools/prepare_plugin_dependencies.py")
file(SHA256 "${_patcher}" _patch_hash)
file(SHA256 "${CMAKE_SOURCE_DIR}/cmake/dependencies.json" _pin_hash)
string(SHA256 _patch_hash "${_patch_hash}${_pin_hash}")
string(SUBSTRING "${_patch_hash}" 0 12 _patch_hash)
set(IPLUG2_DIR "${CMAKE_BINARY_DIR}/generated/dependencies/${_patch_hash}/iPlug2")
execute_process(COMMAND "${Python3_EXECUTABLE}" -B "${_patcher}" "${KROSE_PINNED_IPLUG2_DIR}" "${IPLUG2_DIR}"
  RESULT_VARIABLE _patch_result ERROR_VARIABLE _patch_error)
if(NOT _patch_result EQUAL 0)
  message(FATAL_ERROR "Cannot prepare dependency fixes: ${_patch_error}")
endif()
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_patcher}" "${CMAKE_SOURCE_DIR}/cmake/dependencies.json")
set(IPLUG_DEPLOY_PLUGINS OFF CACHE BOOL "Keep plugin outputs inside build/out")
set(IGRAPHICS_BACKEND "NANOVG" CACHE STRING "Drawing backend")
if(APPLE)
  set(IGRAPHICS_RENDERER "METAL" CACHE STRING "Drawing renderer")
elseif(WIN32)
  set(IGRAPHICS_RENDERER "GL2" CACHE STRING "Drawing renderer")
endif()
include("${IPLUG2_DIR}/iPlug2.cmake")
find_package(iPlug2 REQUIRED)
include("${CMAKE_CURRENT_LIST_DIR}/StandaloneHost.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/GraphicsInput.cmake")
include("${CMAKE_CURRENT_LIST_DIR}/VST3Input.cmake")

# Opt into stb_image's allocation API without modifying the pinned dependency.
# Keep all texture pixels, filtering, render buffers and refresh behavior intact.
if(APPLE AND TARGET iPlug2_IGraphics_NanoVG_Metal_obj)
  target_compile_options(iPlug2_IGraphics_NanoVG_Metal_obj PRIVATE
    -include "${CMAKE_SOURCE_DIR}/src/plugin/editor/native/ImageMemory.h")
endif()
