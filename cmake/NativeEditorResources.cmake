set(_native "${CMAKE_CURRENT_SOURCE_DIR}/editor/native/assets")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  "${_native}/native-data.json" "${_native}/lcd-resources.json"
  "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.json"
  "${KROSE_FACTORY_ASSET_DIR}/FactoryBrowser.json")
file(GLOB KROSE_NATIVE_IMAGES CONFIGURE_DEPENDS "${_native}/*@2x.png")
file(READ "${_native}/native-data.json" _data)
file(READ "${KROSE_FACTORY_ASSET_DIR}/FactoryPrograms.json" _programs)
file(READ "${KROSE_FACTORY_ASSET_DIR}/FactoryBrowser.json" _browser)
file(READ "${_native}/lcd-resources.json" _lcd)
set(_names "[")
foreach(_image IN LISTS KROSE_NATIVE_IMAGES)
  get_filename_component(_name "${_image}" NAME)
  string(REPLACE "@2x.png" "" _name "${_name}")
  string(APPEND _names "\"${_name}\",")
endforeach()
string(REGEX REPLACE ",$" "]" _names "${_names}")
# Large JSON literals exceed MSVC's string-literal limit. Byte initializers also
# preserve the UTF-8 source bytes without relying on a compiler execution charset.
set(_header "#pragma once\n")
foreach(_pair IN ITEMS "Data|_data" "Programs|_programs" "Browser|_browser" "LCD|_lcd" "ImageNames|_names")
  string(REPLACE "|" ";" _pair "${_pair}")
  list(GET _pair 0 _symbol)
  list(GET _pair 1 _variable)
  string(HEX "${${_variable}}" _hex)
  string(REGEX REPLACE "(..)" "char(0x\\1),\n" _bytes "${_hex}")
  string(APPEND _header "inline constexpr char kNative${_symbol}[]={\n${_bytes}0};\n")
endforeach()
file(CONFIGURE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/NativeData.h" CONTENT "${_header}" @ONLY)
