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
# Frozen complete factory/GM/expansion assets are an explicit offline handoff, not a firmware build step.
if(KROSE_FACTORY_ASSET_DIR STREQUAL "${CMAKE_SOURCE_DIR}/assets/factory-starter")
  set(KROSE_FACTORY_ASSET_DIR "${CMAKE_SOURCE_DIR}/assets/program-library" CACHE PATH "Frozen shared program library" FORCE)
endif()
set(KROSE_FACTORY_ASSET_DIR "${CMAKE_SOURCE_DIR}/assets/program-library" CACHE PATH "Frozen shared factory library")
segrand_check_asset_bundle("${KROSE_FACTORY_ASSET_DIR}")
add_custom_command(OUTPUT "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/FactoryPrograms.h"
  COMMAND ${CMAKE_COMMAND} -E make_directory "${SEGRAND_GENERATED}"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${KROSE_FACTORY_ASSET_DIR}/Factory.samples" "${SEGRAND_GENERATED}/Factory.samples"
  COMMAND ${CMAKE_COMMAND} -E copy_if_different "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.h" "${SEGRAND_GENERATED}/FactoryPrograms.h"
  DEPENDS "${KROSE_FACTORY_ASSET_DIR}/Factory.samples" "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.h" VERBATIM)
add_custom_target(krose-factory-assets DEPENDS "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/FactoryPrograms.h")
