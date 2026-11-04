set(panel "${CMAKE_SOURCE_DIR}/docs/design/krose-fixed-ui.html")
set(catalog "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.json")
set(bridge "${CMAKE_CURRENT_SOURCE_DIR}/resources/editor-bridge.js")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${panel}" "${bridge}" "${catalog}")
file(READ "${panel}" KROSE_PANEL)
file(READ "${bridge}" KROSE_BRIDGE)
file(READ "${catalog}" KROSE_CATALOG)
configure_file(resources/editor.html.in "${CMAKE_CURRENT_BINARY_DIR}/editor.html" @ONLY)
iplug_add_plugin(Krose
  SOURCES SEGrand.cpp SEGrand.h resources/resource.h
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
