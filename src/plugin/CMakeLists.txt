iplug_add_plugin(Krose
  SOURCES SEGrand.cpp SEGrand.h resources/resource.h
  RESOURCES "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples"
    "${CMAKE_SOURCE_DIR}/licenses/THIRD_PARTY.txt"
    "${CMAKE_SOURCE_DIR}/licenses/Roboto-Apache-2.0.txt"
    "${IPLUG2_DIR}/Examples/IPlugEffect/resources/fonts/Roboto-Regular.ttf"
  FORMATS VST3 APP
  LINK segrand-engine)
add_dependencies(Krose-vst3 segrand-assets krose-factory-assets)
add_dependencies(Krose-app segrand-assets krose-factory-assets)
if(APPLE)
  target_sources(Krose-app PRIVATE StandaloneStartup.mm)
  foreach(target Krose-vst3 Krose-app)
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND codesign --force --sign - "$<TARGET_BUNDLE_DIR:${target}>"
      VERBATIM)
  endforeach()
endif()
