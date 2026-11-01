# Build the SDK's unchanged CLI validator using Apple's Command Line Tools.
# The SDK's top-level project insists on the Xcode IDE, which is unnecessary
# for these command-line targets. This file supplies only the source/link setup.
set(SDK_ROOT "${CMAKE_SOURCE_DIR}/build/deps/vst3sdk")
set(_sdk_sources
  base/source/baseiids.cpp base/source/fbuffer.cpp base/source/fdebug.cpp
  base/source/fdynlib.cpp base/source/fobject.cpp base/source/fstreamer.cpp
  base/source/fstring.cpp base/source/timer.cpp base/source/updatehandler.cpp
  base/thread/source/fcondition.cpp base/thread/source/flock.cpp
  pluginterfaces/base/conststringtable.cpp pluginterfaces/base/coreiids.cpp
  pluginterfaces/base/funknown.cpp pluginterfaces/base/ustring.cpp
  public.sdk/source/common/commoniids.cpp public.sdk/source/common/commonstringconvert.cpp
  public.sdk/source/common/openurl.cpp public.sdk/source/common/readfile.cpp
  public.sdk/source/common/threadchecker_mac.mm public.sdk/source/common/systemclipboard_mac.mm
  public.sdk/source/vst/vstpresetfile.cpp public.sdk/source/vst/vstinitiids.cpp
  public.sdk/source/vst/hosting/connectionproxy.cpp public.sdk/source/vst/hosting/eventlist.cpp
  public.sdk/source/vst/hosting/hostclasses.cpp public.sdk/source/vst/hosting/module.cpp
  public.sdk/source/vst/hosting/module_mac.mm public.sdk/source/vst/hosting/parameterchanges.cpp
  public.sdk/source/vst/hosting/pluginterfacesupport.cpp public.sdk/source/vst/hosting/processdata.cpp
  public.sdk/source/vst/utility/stringconvert.cpp)
list(TRANSFORM _sdk_sources PREPEND "${SDK_ROOT}/")
add_library(segrand-sdk-hosting STATIC ${_sdk_sources})
target_include_directories(segrand-sdk-hosting PUBLIC "${SDK_ROOT}")
target_compile_definitions(segrand-sdk-hosting PUBLIC RELEASE=1)
target_link_libraries(segrand-sdk-hosting PUBLIC "-framework Cocoa" "-framework CoreFoundation")
set_source_files_properties("${SDK_ROOT}/public.sdk/source/vst/hosting/module_mac.mm" PROPERTIES COMPILE_FLAGS "-fobjc-arc")
add_library(sdk_hosting ALIAS segrand-sdk-hosting)
set(SMTG_MAC TRUE)
function(smtg_target_codesign target)
  add_custom_command(TARGET ${target} POST_BUILD COMMAND codesign --force --sign - "$<TARGET_FILE:${target}>" VERBATIM)
endfunction()
function(smtg_target_setup_universal_binary target)
  if(CMAKE_OSX_ARCHITECTURES)
    set_target_properties(${target} PROPERTIES OSX_ARCHITECTURES "${CMAKE_OSX_ARCHITECTURES}")
  endif()
endfunction()
add_subdirectory("${SDK_ROOT}/public.sdk/samples/vst-hosting/validator" "${CMAKE_BINARY_DIR}/sdk-validator")
add_executable(test-vst3-host tests/test_vst3_host.cpp
  "${SDK_ROOT}/public.sdk/source/vst/hosting/plugprovider.cpp"
  "${SDK_ROOT}/public.sdk/source/common/memorystream.cpp")
target_link_libraries(test-vst3-host PRIVATE segrand-sdk-hosting)
target_compile_options(test-vst3-host PRIVATE -UNDEBUG)
add_dependencies(test-vst3-host Krose-vst3)
add_test(NAME vst3-host COMMAND test-vst3-host "${CMAKE_BINARY_DIR}/out/Krose.vst3")
