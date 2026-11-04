set(SEGRAND_FIXTURE_DIR "${CMAKE_SOURCE_DIR}/tests/fixtures/concert-se-grand")
segrand_check_asset_bundle("${SEGRAND_FIXTURE_DIR}")
add_executable(test-program-engine test_program_engine.cpp)
target_link_libraries(test-program-engine PRIVATE segrand-engine)
target_compile_options(test-program-engine PRIVATE -UNDEBUG)
segrand_check_asset_bundle("${CMAKE_SOURCE_DIR}/tests/fixtures/full-programs")
add_test(NAME program-engine COMMAND test-program-engine "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/SEGrand.samples" "${CMAKE_SOURCE_DIR}/tests/fixtures/full-programs")
add_executable(test-piano-engine test_piano_engine.cpp)
target_link_libraries(test-piano-engine PRIVATE segrand-engine)
target_compile_options(test-piano-engine PRIVATE -UNDEBUG)
add_test(NAME piano-engine COMMAND test-piano-engine "${SEGRAND_GENERATED}/SEGrand.samples")
add_executable(test-native-voice test_native_voice.cpp)
target_link_libraries(test-native-voice PRIVATE segrand-engine)
target_compile_options(test-native-voice PRIVATE -UNDEBUG)
add_test(NAME native-voice COMMAND test-native-voice
  "${SEGRAND_FIXTURE_DIR}/concert-control-map.bin"
  "${SEGRAND_FIXTURE_DIR}/native-voice-traces.bin" "${SEGRAND_FIXTURE_DIR}/native-tg-commands.bin")
add_executable(test-native-filter test_native_filter.cpp)
target_link_libraries(test-native-filter PRIVATE segrand-engine)
target_compile_options(test-native-filter PRIVATE -UNDEBUG)
add_test(NAME native-filter COMMAND test-native-filter
  "${SEGRAND_FIXTURE_DIR}/concert-filter-map.bin"
  "${SEGRAND_FIXTURE_DIR}/concert-filter-traces.bin")

set_target_properties(test-program-engine test-piano-engine test-native-voice test-native-filter
  PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

segrand_check_asset_bundle("${CMAKE_SOURCE_DIR}/tests/fixtures/performance")
add_executable(test-performance test_performance.cpp)
target_link_libraries(test-performance PRIVATE segrand-engine)
target_compile_options(test-performance PRIVATE -UNDEBUG)
set_target_properties(test-performance PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_test(NAME performance COMMAND test-performance "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples" "${CMAKE_SOURCE_DIR}/tests/fixtures/performance")

segrand_check_asset_bundle("${CMAKE_SOURCE_DIR}/tests/fixtures/arpeggiator")
add_executable(test-arpeggiator test_arpeggiator.cpp)
target_link_libraries(test-arpeggiator PRIVATE segrand-engine)
target_compile_options(test-arpeggiator PRIVATE -UNDEBUG)
set_target_properties(test-arpeggiator PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_test(NAME arpeggiator COMMAND test-arpeggiator "${SEGRAND_GENERATED}/SEGrand.samples" "${SEGRAND_GENERATED}/Factory.samples" "${CMAKE_SOURCE_DIR}/tests/fixtures/arpeggiator")

add_executable(test-sample-loading test_sample_loading.cpp)
target_link_libraries(test-sample-loading PRIVATE segrand-engine)
target_compile_options(test-sample-loading PRIVATE -UNDEBUG)
set_target_properties(test-sample-loading PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_test(NAME sample-loading COMMAND test-sample-loading "${SEGRAND_GENERATED}/Factory.samples" "${SEGRAND_GENERATED}/SEGrand.samples")

add_executable(test-image-memory test_image_memory.cpp)
target_compile_options(test-image-memory PRIVATE -UNDEBUG)
set_target_properties(test-image-memory PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_test(NAME image-memory COMMAND test-image-memory)

add_executable(test-effects test_effects.cpp)
target_link_libraries(test-effects PRIVATE segrand-engine)
target_compile_options(test-effects PRIVATE -UNDEBUG)
set_target_properties(test-effects PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
add_test(NAME effects COMMAND test-effects)
