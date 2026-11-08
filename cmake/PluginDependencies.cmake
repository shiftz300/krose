set(IPLUG2_DIR "${CMAKE_SOURCE_DIR}/build/deps/iPlug2" CACHE PATH "Pinned iPlug2 source checkout")
if(NOT EXISTS "${IPLUG2_DIR}/iPlug2.cmake")
  message(FATAL_ERROR "Run python3 tools/bootstrap_plugin.py to fetch the pinned dependencies")
endif()
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
