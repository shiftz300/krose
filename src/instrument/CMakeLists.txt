add_library(segrand-engine STATIC
  PCM24.cpp
  SampleLoader.cpp
  ProgramLibrary.cpp
  ProgramEngine.cpp
  InstrumentEngine.cpp
  Arpeggiator.cpp
  PianoEngine.cpp
  NativeVoice.cpp
  NativeFilter.cpp
  ../dsp/concert_effects.c)
add_dependencies(segrand-engine segrand-assets segrand-voice-assets krose-factory-assets)
set_target_properties(segrand-engine PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(segrand-engine PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}"
  "${CMAKE_CURRENT_SOURCE_DIR}/../dsp"
  "${SEGRAND_GENERATED}")
if(MSVC)
  target_compile_options(segrand-engine PRIVATE /W4 /utf-8)
else()
  target_compile_options(segrand-engine PRIVATE -Wall -Wextra -Werror)
endif()

find_package(Threads REQUIRED)
target_link_libraries(segrand-engine PUBLIC Threads::Threads)
