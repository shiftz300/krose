# Build-only entry point; multi-config Debug must never execute training.
get_filename_component(_directory "${PROFILE}" DIRECTORY)
file(MAKE_DIRECTORY "${_directory}")
if(CONFIG STREQUAL "Release")
  file(REMOVE "${RAW}")
  execute_process(COMMAND "${CMAKE_COMMAND}" -E env "LLVM_PROFILE_FILE=${RAW}"
    "${TRAINER}" "${FACTORY}" "${CONCERT}" COMMAND_ERROR_IS_FATAL ANY)
  execute_process(COMMAND "${PROFDATA}" merge -o "${PROFILE}.incoming" "${RAW}"
    COMMAND_ERROR_IS_FATAL ANY)
  file(RENAME "${PROFILE}.incoming" "${PROFILE}")
else()
  # CMake shares generated-source ordering across configurations. These empty
  # outputs satisfy that ordering; non-Release compiles never consume them.
  file(TOUCH "${PROFILE}")
endif()
# Forced inclusion makes compiler dependency scans rebuild every core object
# after training changes, including with Xcode and Visual Studio generators.
file(TOUCH "${STAMP}")
