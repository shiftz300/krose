add_library(segrand-engine STATIC
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
target_compile_options(segrand-engine PRIVATE -Wall -Wextra -Werror)
