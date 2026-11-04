add_executable(render-program audio/render_program.cpp)
target_link_libraries(render-program PRIVATE krose::core)
add_executable(benchmark-program audio/benchmark_program.cpp)
target_link_libraries(benchmark-program PRIVATE krose::core)
add_executable(render-piano audio/render_piano.cpp)
target_link_libraries(render-piano PRIVATE krose::core)
add_executable(benchmark-piano audio/benchmark_piano.cpp)
target_link_libraries(benchmark-piano PRIVATE krose::core)

set_target_properties(render-program benchmark-program render-piano benchmark-piano
  PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_executable(benchmark-loading audio/benchmark_loading.cpp)
target_link_libraries(benchmark-loading PRIVATE krose::core)
set_target_properties(benchmark-loading PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_executable(benchmark-effects audio/benchmark_effects.cpp)
target_link_libraries(benchmark-effects PRIVATE krose::core)
set_target_properties(benchmark-effects PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_executable(benchmark-core audio/benchmark_core.cpp)
target_link_libraries(benchmark-core PRIVATE krose::core)
set_target_properties(benchmark-core PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
