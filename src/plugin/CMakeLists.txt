include("${CMAKE_SOURCE_DIR}/cmake/NativeEditorResources.cmake")
if(BUILD_TESTING)
  krose_test(user-preset "${CMAKE_SOURCE_DIR}/tests/plugin/test_user_preset.cpp")
  target_include_directories(test-user-preset PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
    "${IPLUG2_DIR}/Dependencies/Extras/nlohmann")
  target_link_libraries(test-user-preset PRIVATE krose::core)
endif()
set(KROSE_LICENSE_RESOURCES
  "${CMAKE_SOURCE_DIR}/LICENSE"
  "${CMAKE_SOURCE_DIR}/NOTICE"
  "${CMAKE_SOURCE_DIR}/docs/LICENSING.md"
  "${CMAKE_SOURCE_DIR}/licenses/THIRD_PARTY.txt"
  "${CMAKE_SOURCE_DIR}/licenses/Roboto-Apache-2.0.txt")
iplug_add_plugin(Krose
  SOURCES
    KrosePlugin.cpp KrosePlugin.h
    Parameters.cpp Parameters.h storage/UserPreset.cpp
    midi/ControllerInput.cpp midi/ControllerState.cpp
    editor/NativeEditor.cpp editor/native/NativePanel.cpp editor/native/PanelBrowser.cpp editor/native/PanelInput.cpp editor/native/PanelFavorites.cpp editor/native/PanelControllers.cpp editor/native/PanelEffects.cpp editor/native/PanelMotion.cpp resources/resource.h
  RESOURCES ${KROSE_NATIVE_IMAGES} "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples"
    ${KROSE_LICENSE_RESOURCES}
    "${IPLUG2_DIR}/Examples/IPlugEffect/resources/fonts/Roboto-Regular.ttf"
  FORMATS VST3 APP
  LINK krose::core)
# Apply to SDK translation units as well as the plugin: all channels expose CC input.
target_compile_definitions(Krose-vst3 PRIVATE VST3_NUM_CC_CHANS=16)
target_include_directories(Krose-vst3 BEFORE PRIVATE "${CMAKE_BINARY_DIR}/generated/iplug-vst3")
add_dependencies(Krose-vst3 segrand-assets krose-factory-assets)
add_dependencies(Krose-app segrand-assets krose-factory-assets)
foreach(target Krose-vst3 Krose-app)
  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${IPLUG2_DIR}/Dependencies/Extras/nlohmann")
endforeach()
if(APPLE)
  target_sources(Krose-app PRIVATE StandaloneStartup.mm)
  include("${CMAKE_SOURCE_DIR}/cmake/MacOSAppIcon.cmake")
  krose_add_macos_icon(Krose-app)
  # Re-sign the bundle when an icon-only edit updates its sealed resources.
  set_property(TARGET Krose-app APPEND PROPERTY LINK_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/resources/Krose.icns")
  foreach(target Krose-vst3 Krose-app)
    target_include_directories(${target} PRIVATE "${IPLUG2_DIR}/Dependencies/Extras/nlohmann")
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E rm -f "$<TARGET_BUNDLE_DIR:${target}>/Contents/Resources/editor.html"
      COMMAND codesign --force --sign - "$<TARGET_BUNDLE_DIR:${target}>"
      VERBATIM)
  endforeach()
endif()
if(WIN32)
  # iPlug2 marks resources for Apple bundles; Windows needs explicit copies.
  foreach(target Krose-vst3 Krose-app)
    if(target STREQUAL "Krose-vst3")
      set(_destination "${CMAKE_BINARY_DIR}/out/Krose.vst3/Contents/Resources")
    else()
      set(_destination "${CMAKE_BINARY_DIR}/out/Resources")
    endif()
    add_custom_command(TARGET ${target} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory "${_destination}"
      COMMAND ${CMAKE_COMMAND} -E copy_if_different ${KROSE_NATIVE_IMAGES}
        "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples"
        ${KROSE_LICENSE_RESOURCES} "${_destination}"
      VERBATIM)
    target_compile_options(${target} PRIVATE /utf-8)
  endforeach()
endif()
