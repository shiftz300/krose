# Run at build time so incremental builds do not retain the configure timestamp.
# CMake honors SOURCE_DATE_EPOCH when a reproducible build timestamp is requested.
if(NOT DEFINED OUTPUT OR NOT DEFINED VERSION)
  message(FATAL_ERROR "OUTPUT and VERSION are required")
endif()
string(TIMESTAMP _built "%Y-%m-%d %H:%M:%S UTC" UTC)
set(_content "#pragma once\nnamespace krose::build {\ninline constexpr char kVersion[] = \"${VERSION}\";\ninline constexpr char kTimestamp[] = \"${_built}\";\n}\n")
file(CONFIGURE OUTPUT "${OUTPUT}" CONTENT "${_content}" @ONLY)
