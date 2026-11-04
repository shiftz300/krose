add_executable(render-program render_program.cpp)
target_link_libraries(render-program PRIVATE segrand-engine)
add_executable(benchmark-program benchmark_program.cpp)
target_link_libraries(benchmark-program PRIVATE segrand-engine)
add_executable(render-piano render_piano.cpp)
target_link_libraries(render-piano PRIVATE segrand-engine)
add_executable(benchmark-piano benchmark_piano.cpp)
target_link_libraries(benchmark-piano PRIVATE segrand-engine)

set_target_properties(render-program benchmark-program render-piano benchmark-piano
  PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_executable(benchmark-loading benchmark_loading.cpp)
target_link_libraries(benchmark-loading PRIVATE segrand-engine)
set_target_properties(benchmark-loading PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

add_executable(benchmark-effects benchmark_effects.cpp)
target_link_libraries(benchmark-effects PRIVATE segrand-engine)
set_target_properties(benchmark-effects PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
