# Train only the audio core. Profiles are rebuilt from the current sources and
# frozen banks; neither profiles nor instrumented binaries enter a plugin bundle.
option(KROSE_ENABLE_PGO "Automatically train and use Clang PGO in Release builds" ON)

function(krose_enable_pgo target)
  if(NOT KROSE_ENABLE_PGO OR SEGRAND_SANITIZE)
    return()
  endif()
  if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE STREQUAL "Release")
    return()
  endif()
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang" OR NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "PGO requires Clang/clang-cl. Use that toolchain or set KROSE_ENABLE_PGO=OFF.")
  endif()
  if(APPLE)
    list(LENGTH CMAKE_OSX_ARCHITECTURES _arch_count)
    if(_arch_count GREATER 1)
      message(FATAL_ERROR "PGO requires a native build per architecture. Merge the trained arm64/x86_64 bundles afterwards.")
    endif()
  endif()
  get_filename_component(_compiler_dir "${CMAKE_CXX_COMPILER}" DIRECTORY)
  find_program(KROSE_LLVM_PROFDATA llvm-profdata HINTS "${_compiler_dir}")
  if(NOT KROSE_LLVM_PROFDATA AND APPLE)
    execute_process(COMMAND xcrun --find llvm-profdata OUTPUT_VARIABLE _profdata
      OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    set(KROSE_LLVM_PROFDATA "${_profdata}" CACHE FILEPATH "Matching LLVM profile merger" FORCE)
  endif()
  if(NOT EXISTS "${KROSE_LLVM_PROFDATA}")
    message(FATAL_ERROR "PGO requires llvm-profdata from the active Clang toolchain")
  endif()

  krose_core_library(krose-core-instrumented)
  set_target_properties(krose-core-instrumented PROPERTIES EXCLUDE_FROM_ALL TRUE)
  add_executable(krose-pgo-train EXCLUDE_FROM_ALL "${CMAKE_SOURCE_DIR}/tools/audio/train_pgo.cpp")
  target_link_libraries(krose-pgo-train PRIVATE krose-core-instrumented)

  set(_directory "${CMAKE_CURRENT_BINARY_DIR}/pgo/$<CONFIG>")
  set(_raw "${_directory}/training.profraw")
  set(_profile "${_directory}/core.profdata")
  set(_stamp "${_directory}/ProfileStamp.h")
  set(_generate "-fprofile-generate=${_directory}")
  set(_use "-fprofile-use=${_profile}")
  if(CMAKE_CXX_COMPILER_FRONTEND_VARIANT STREQUAL "MSVC")
    target_compile_options(krose-core-instrumented PRIVATE
      "$<$<CONFIG:Release>:/clang:${_generate}>"
      "$<$<CONFIG:Release>:/clang:-fprofile-update=atomic>")
    target_compile_options(${target} PRIVATE
      "$<$<CONFIG:Release>:/clang:${_use}>"
      "$<$<CONFIG:Release>:/clang:-Werror=profile-instr-out-of-date>"
      "$<$<CONFIG:Release>:/FI${_stamp}>")
    # CMake invokes lld-link directly for clang-cl; make its auto-linked
    # profiling runtime discoverable without changing the production link.
    execute_process(COMMAND "${CMAKE_CXX_COMPILER}" --print-runtime-dir
      OUTPUT_VARIABLE _runtime_dir OUTPUT_STRIP_TRAILING_WHITESPACE
      COMMAND_ERROR_IS_FATAL ANY)
    target_link_options(krose-core-instrumented INTERFACE
      "$<$<CONFIG:Release>:/LIBPATH:${_runtime_dir}>")
  else()
    target_compile_options(krose-core-instrumented PRIVATE
      "$<$<CONFIG:Release>:${_generate}>" "$<$<CONFIG:Release>:-fprofile-update=atomic>")
    target_link_options(krose-core-instrumented INTERFACE "$<$<CONFIG:Release>:${_generate}>")
    target_compile_options(${target} PRIVATE
      "$<$<CONFIG:Release>:${_use}>" "$<$<CONFIG:Release>:-Werror=profile-instr-out-of-date>"
      "$<$<CONFIG:Release>:-include>" "$<$<CONFIG:Release>:${_stamp}>")
    target_link_options(${target} INTERFACE "$<$<CONFIG:Release>:${_use}>")
  endif()

  add_custom_command(OUTPUT "${_profile}" "${_stamp}"
    COMMAND ${CMAKE_COMMAND} "-DCONFIG=$<CONFIG>" "-DPROFILE=${_profile}" "-DSTAMP=${_stamp}"
      "-DTRAINER=$<$<CONFIG:Release>:$<TARGET_FILE_DIR:krose-pgo-train>/$<TARGET_FILE_NAME:krose-pgo-train>>"
      "-DPROFDATA=${KROSE_LLVM_PROFDATA}" "-DRAW=${_raw}"
      "-DFACTORY=${SEGRAND_GENERATED}/Factory.samples" "-DCONCERT=${SEGRAND_GENERATED}/SEGrand.samples"
      -P "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/TrainProfile.cmake"
    DEPENDS "$<$<CONFIG:Release>:$<TARGET_FILE_DIR:krose-pgo-train>/$<TARGET_FILE_NAME:krose-pgo-train>>"
      "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/TrainProfile.cmake"
      "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/SEGrand.samples"
    COMMENT "Preparing architecture-local Release PGO data" VERBATIM USES_TERMINAL)
  add_custom_target(krose-pgo-profile DEPENDS "${_profile}")
  set_source_files_properties("${_profile}" "${_stamp}" PROPERTIES GENERATED TRUE HEADER_FILE_ONLY TRUE)
  # Multi-config generators may schedule this rule for all configurations.
  # TrainProfile only runs the instrumented executable in Release.
  target_sources(${target} PRIVATE "$<$<CONFIG:Release>:${_profile}>" "$<$<CONFIG:Release>:${_stamp}>")
endfunction()
