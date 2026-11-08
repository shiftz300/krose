# Route the macOS middle mouse button through the same existing IGraphics path
# as Windows. IMouseMod has no middle bit: both L and R are false for this event.
# Generate an overlay instead of modifying the hash-pinned dependency.
if(APPLE)
  set(_view_original "${IPLUG2_DIR}/IGraphics/Platforms/IGraphicsMac_view.mm")
  file(READ "${_view_original}" _view_source)
  set(_marker "- (void) rightMouseDown: (NSEvent*) pEvent")
  string(FIND "${_view_source}" "${_marker}" _found)
  if(_found LESS 0)
    message(FATAL_ERROR "Pinned iPlug macOS mouse input source changed")
  endif()
  set(_middle [=[- (void) otherMouseDown: (NSEvent*) event
{
  if (event.buttonNumber != 2 || !mGraphics) return;
  IMouseInfo info = [self getMouseRight:event];
  info.ms.R = false;
  std::vector<IMouseInfo> events{info};
  mGraphics->OnMouseDown(events);
}
- (void) otherMouseUp: (NSEvent*) event
{
  if (event.buttonNumber != 2 || !mGraphics) return;
  IMouseInfo info = [self getMouseRight:event];
  info.ms.R = false;
  std::vector<IMouseInfo> events{info};
  mGraphics->OnMouseUp(events);
}

]=])
  string(REPLACE "${_marker}" "${_middle}${_marker}" _view_source "${_view_source}")
  set(_view_overlay "${CMAKE_BINARY_DIR}/generated/iplug-graphics/IGraphicsMac_view.mm")
  file(CONFIGURE OUTPUT "${_view_overlay}" CONTENT "${_view_source}" @ONLY)
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_view_original}")
  get_target_property(_graphics_sources iPlug2::IGraphics INTERFACE_SOURCES)
  string(REPLACE "${_view_original}" "${_view_overlay}" _graphics_sources "${_graphics_sources}")
  set_property(TARGET iPlug2::IGraphics PROPERTY INTERFACE_SOURCES "${_graphics_sources}")
endif()
