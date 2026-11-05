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
