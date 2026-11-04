include("${CMAKE_SOURCE_DIR}/cmake/EditorResources.cmake")
include("${CMAKE_SOURCE_DIR}/cmake/NativeEditorResources.cmake")
iplug_add_plugin(Krose
  SOURCES
    KrosePlugin.cpp KrosePlugin.h
    Parameters.cpp Parameters.h
    editor/NativeEditor.cpp editor/native/NativePanel.cpp editor/native/PanelBrowser.cpp editor/native/PanelInput.cpp  resources/resource.h
  RESOURCES ${KROSE_NATIVE_IMAGES} "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples"
    "${CMAKE_SOURCE_DIR}/licenses/THIRD_PARTY.txt"
    "${CMAKE_SOURCE_DIR}/licenses/Roboto-Apache-2.0.txt"
    "${IPLUG2_DIR}/Examples/IPlugEffect/resources/fonts/Roboto-Regular.ttf"
  FORMATS VST3 APP
  LINK segrand-engine)
add_dependencies(Krose-vst3 segrand-assets krose-factory-assets)
add_dependencies(Krose-app segrand-assets krose-factory-assets)
foreach(target Krose-vst3 Krose-app)
  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${IPLUG2_DIR}/Dependencies/Extras/nlohmann")
endforeach()
if(APPLE)
  target_sources(Krose-app PRIVATE StandaloneStartup.mm)
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
        "${CMAKE_SOURCE_DIR}/licenses/THIRD_PARTY.txt" "${_destination}"
      VERBATIM)
    target_compile_options(${target} PRIVATE /utf-8)
  endforeach()
endif()
