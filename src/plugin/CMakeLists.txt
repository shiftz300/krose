include("${CMAKE_SOURCE_DIR}/cmake/EditorResources.cmake")
iplug_add_plugin(Krose
  SOURCES
    KrosePlugin.cpp KrosePlugin.h
    Parameters.cpp Parameters.h
    editor/WebEditor.cpp resources/resource.h
  RESOURCES "${CMAKE_CURRENT_BINARY_DIR}/editor.html" "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples"
    "${CMAKE_SOURCE_DIR}/licenses/THIRD_PARTY.txt"
    "${CMAKE_SOURCE_DIR}/licenses/Roboto-Apache-2.0.txt"
    "${IPLUG2_DIR}/Examples/IPlugEffect/resources/fonts/Roboto-Regular.ttf"
  FORMATS VST3 APP
  LINK segrand-engine iPlug2::Extras::IWebViewControl)
add_dependencies(Krose-vst3 segrand-assets krose-factory-assets)
add_dependencies(Krose-app segrand-assets krose-factory-assets)
if(APPLE)
  target_sources(Krose-app PRIVATE StandaloneStartup.mm)
  foreach(target Krose-vst3 Krose-app)
    set_property(TARGET ${target} APPEND PROPERTY LINK_DEPENDS "${CMAKE_CURRENT_BINARY_DIR}/editor.html")
    target_include_directories(${target} PRIVATE "${IPLUG2_DIR}/Dependencies/Extras/nlohmann")
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND codesign --force --sign - "$<TARGET_BUNDLE_DIR:${target}>"
      VERBATIM)
  endforeach()
endif()
