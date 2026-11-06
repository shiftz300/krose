# Preserve timed controller events and automation points in the pinned SDK.
set(_vst3_processor "${IPLUG2_DIR}/IPlug/VST3/IPlugVST3_ProcessorBase.cpp")
file(READ "${_vst3_processor}" _vst3_source)
function(_vst3_replace old new)
  string(FIND "${_vst3_source}" "${old}" match)
  if(match LESS 0)
    message(FATAL_ERROR "Pinned iPlug VST3 processor source changed")
  endif()
  string(REPLACE "${old}" "${new}" _vst3_source "${_vst3_source}")
  set(_vst3_source "${_vst3_source}" PARENT_SCOPE)
endfunction()

_vst3_replace("if (paramQueue->getPoint(numPoints - 1,  offsetSamples, value) == kResultTrue)"
  [=[for (int32 point = 0; point < numPoints; ++point)
        if (paramQueue->getPoint(point, offsetSamples, value) == kResultTrue)]=])
_vst3_replace("          int idx = paramQueue->getParameterId();"
  [=[          if (!std::isfinite(value)) continue;
          value = std::clamp(value, 0., 1.);
          int idx = paramQueue->getParameterId();]=])
_vst3_replace("else if (idx >= kMIDICCParamStartIdx)"
  "else if (idx >= kMIDICCParamStartIdx && idx < kMIDICCParamStartIdx + 16 * kCountCtrlNumber)")
_vst3_replace("            msg.MakeNoteOnMsg(event.noteOn.pitch, event.noteOn.velocity * 127, event.sampleOffset, event.noteOn.channel);"
  [=[            if (!std::isfinite(event.noteOn.velocity) || event.noteOn.pitch < 0 || event.noteOn.pitch > 127 || event.noteOn.channel < 0 || event.noteOn.channel > 15) break;
            msg.MakeNoteOnMsg(event.noteOn.pitch, std::clamp(event.noteOn.velocity, 0.f, 1.f) * 127, event.sampleOffset, event.noteOn.channel);]=])
_vst3_replace("            msg.MakePolyATMsg(event.polyPressure.pitch, event.polyPressure.pressure * 127., event.sampleOffset, event.polyPressure.channel);"
  [=[            if (!std::isfinite(event.polyPressure.pressure) || event.polyPressure.pitch < 0 || event.polyPressure.pitch > 127 || event.polyPressure.channel < 0 || event.polyPressure.channel > 15) break;
            msg.MakePolyATMsg(event.polyPressure.pitch, std::clamp(event.polyPressure.pressure, 0.f, 1.f) * 127., event.sampleOffset, event.polyPressure.channel);]=])
_vst3_replace("            msg.MakeNoteOffMsg(event.noteOff.pitch, event.sampleOffset, event.noteOff.channel);"
  [=[            if (event.noteOff.pitch < 0 || event.noteOff.pitch > 127 || event.noteOff.channel < 0 || event.noteOff.channel > 15) break;
            msg.MakeNoteOffMsg(event.noteOff.pitch, event.sampleOffset, event.noteOff.channel);]=])
string(CONCAT _immediate_parameter "mPlug.GetParam(idx)->SetNormalized(value);\n              \n"
  "                // In VST3 non distributed the same parameter value is also set via IPlugVST3Controller::setParamNormalized(ParamID tag, ParamValue value)\n"
  "                mPlug.OnParamChange(idx, kHost, offsetSamples);")
_vst3_replace("${_immediate_parameter}"
  [=[static_cast<KrosePlugin&>(mPlug).QueueHostParameter(idx, value, offsetSamples, data.numSamples);]=])
_vst3_replace("  ProcessAudio(data, setup, ins, outs);"
  "  if (GetBypassed())\n    static_cast<KrosePlugin&>(mPlug).FlushHostParameters();\n  ProcessAudio(data, setup, ins, outs);")
_vst3_replace([=[    memcpy(&mProcessContext, data.processContext, sizeof(ProcessContext));]=]
  [=[    mProcessContext = *data.processContext;
  else
    mProcessContext = {};]=])
_vst3_replace("if (mProcessContext.state & ProcessContext::kProjectTimeMusicValid)"
  [=[const auto clockFields = ProcessContext::kProjectTimeMusicValid | ProcessContext::kTempoValid;
  if ((mProcessContext.state & clockFields) == clockFields)]=])
string(PREPEND _vst3_source "#include \"KrosePlugin.h\"\n")
set(_vst3_overlay "${CMAKE_BINARY_DIR}/generated/iplug-vst3/IPlugVST3_ProcessorBase.cpp")
file(CONFIGURE OUTPUT "${_vst3_overlay}" CONTENT "${_vst3_source}" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_vst3_processor}")
get_target_property(_vst3_sources iPlug2::VST3 INTERFACE_SOURCES)
string(REPLACE "${_vst3_processor}" "${_vst3_overlay}" _vst3_sources "${_vst3_sources}")
set_property(TARGET iPlug2::VST3 PROPERTY INTERFACE_SOURCES "${_vst3_sources}")

# The pinned view dereferences a missing host frame and ignores resize rejection.
# Generate narrow overlays; never edit the SDK checkout in place.
set(_view_header "${IPLUG2_DIR}/IPlug/VST3/IPlugVST3_View.h")
set(_api_header "${IPLUG2_DIR}/IPlug/VST3/IPlugVST3.h")
set(_api_source "${IPLUG2_DIR}/IPlug/VST3/IPlugVST3.cpp")
file(READ "${_view_header}" _view)
string(FIND "${_view}" "plugFrame->resizeView(this, &newSize);" _match)
if(_match LESS 0)
  message(FATAL_ERROR "Pinned VST3 view resize implementation changed")
endif()
string(REPLACE "void Resize(int w, int h)" "bool Resize(int w, int h)" _view "${_view}")
string(REPLACE "plugFrame->resizeView(this, &newSize);"
  "return plugFrame && plugFrame->resizeView(this, &newSize) == Steinberg::kResultTrue;" _view "${_view}")
file(CONFIGURE OUTPUT "${CMAKE_BINARY_DIR}/generated/iplug-vst3/IPlugVST3_View.h" CONTENT "${_view}" @ONLY)
file(READ "${_api_header}" _api)
file(CONFIGURE OUTPUT "${CMAKE_BINARY_DIR}/generated/iplug-vst3/IPlugVST3.h" CONTENT "${_api}" @ONLY)
file(READ "${_api_source}" _api)
string(FIND "${_api}" "      mView->Resize(viewWidth, viewHeight);" _match)
if(_match LESS 0)
  message(FATAL_ERROR "Pinned VST3 editor resize implementation changed")
endif()
string(REPLACE "      mView->Resize(viewWidth, viewHeight);"
  "      if (!mView || !mView->Resize(viewWidth, viewHeight)) return false;" _api "${_api}")
set(_api_overlay "${CMAKE_BINARY_DIR}/generated/iplug-vst3/IPlugVST3.cpp")
file(CONFIGURE OUTPUT "${_api_overlay}" CONTENT "${_api}" @ONLY)
get_target_property(_sources iPlug2::VST3 INTERFACE_SOURCES)
string(REPLACE "${_api_source}" "${_api_overlay}" _sources "${_sources}")
set_property(TARGET iPlug2::VST3 PROPERTY INTERFACE_SOURCES "${_sources}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_view_header}" "${_api_header}" "${_api_source}")
