set(KROSE_CORE_SOURCES
  samples/PCM24.cpp
  samples/NativeSampleCodec.cpp
  samples/SampleLoader.cpp
  samples/ProgramLibrary.cpp
  samples/SampleBank.cpp
  engine/ProgramEngine.cpp
  engine/InstrumentEngine.cpp
  midi/Arpeggiator.cpp
  engine/PianoEngine.cpp
  voice/NativeVoice.cpp
  voice/NativeLFO.cpp
  voice/PitchEnvelope.cpp
  voice/NativeModulation.cpp
  voice/NativeFilter.cpp
  effects/concert_effects.c)
find_package(Threads REQUIRED)
function(krose_core_library target)
  add_library(${target} STATIC ${KROSE_CORE_SOURCES})
  add_dependencies(${target} segrand-assets segrand-voice-assets krose-factory-assets)
  set_target_properties(${target} PROPERTIES POSITION_INDEPENDENT_CODE ON)
  target_include_directories(${target} PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}" "${SEGRAND_GENERATED}")
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /utf-8)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
  endif()
  target_link_libraries(${target} PUBLIC Threads::Threads)
endfunction()
krose_core_library(krose-core)
add_library(krose::core ALIAS krose-core)
krose_enable_pgo(krose-core)
