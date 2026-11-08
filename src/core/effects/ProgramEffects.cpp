#include "effects/ProgramEffects.h"
#include "effects/NativeEffectData.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <string_view>
namespace segrand {
namespace {
int Raw(const uint8_t *payload, const effect_data::Field &f) noexcept {
  const unsigned bytes = std::array<unsigned,6>{1,2,4,1,2,4}[f.kind < 6 ? f.kind : 0];
  uint32_t value = 0;
  for (unsigned i=0;i<bytes;++i) value |= uint32_t(payload[f.offset+i]) << (8*i);
  unsigned width = f.width ? f.width : bytes*8;
  if (f.width) value = (value >> f.shift) & (width == 32 ? UINT32_MAX : (uint32_t(1)<<width)-1);
  if (f.kind < 3 && width < 32 && (value & (uint32_t(1)<<(width-1)))) value |= UINT32_MAX << width;
  int32_t signedValue; std::memcpy(&signedValue,&value,4);
  return std::clamp(signedValue,f.min,f.max);
}
double Display(int value, uint32_t display) noexcept {
  switch(display) {
  // Native v1.2.4 0x7457c -> 0x745b8: hundredths of Hz, three linear ranges.
  // The descriptor stores an index; interpreting it as Hz hits the host ceiling.
  case 0x745b8:return (value<=40 ? 2*value : value<=52 ? 10*value-320 : 100*value-5000)/100.;
  // Native 0x97bf4 -> 0x746b4: samples at 48 kHz, formatted as milliseconds.
  case 0x746b4:return value<=99 ? value : 10*value-900;
  case 0x7624c:return value*10+20;
  case 0x7625c:return value*10+50;
  case 0x7626c:return value*100+300;
  case 0x76280:return value*100+500;
  case 0x9b0b4:return (value+5)/10.;
  case 0x9b180: case 0x9b1c8:return value/2.;
  case 0x9cfd4:return value/10.;
  case 0x9cf88:return value/10.;
  case 0x9b34c:return value<=99 ? value/10. : value-90;
  case 0x9af10: case 0x9af38: {
    const int a=std::abs(value);
    const int v=a<=99?2*a:a<=159?5*a-300:a<=209?10*a-1100:50*a-9500;
    return (value<0?-v:v)/100.;
  }
  case 0x741d0:return value<=90?(value+10)/10.:value<=130?value-80:40;
  case 0x80890:return value/10.;
  case 0x80a34:return value<20?value*.05:value<110?(value-10)/10.:value<200?value-100:10*value-1900;
  default:return value;
  }
}
int HostType(int id, bool send) noexcept {
  int algorithm = 1;
  if(id==7) algorithm=2;
  if(id==1||id==2) algorithm=3;
  if(id==3||id==5) algorithm=4;
  if(id==9) algorithm=6;
  if(id==20||id==26||id==27||id==122) algorithm=5;
  if(id==8) algorithm=7;
  if(id==29||id==30||id==31||id==32) algorithm=8;
  if(id==37||id==38) algorithm=9;
  if(id==40) algorithm=10;
  if(!send)return algorithm;
  if(algorithm>=2)return algorithm+4;
  if(id>=64&&id<=70) return 2;
  if(id==89||id==90||id==91||id==92||id==93||id==95||id==96) return 3;
  if(id>=105&&id<=112) return id==106||id==111?5:4;
  return 1;
}
void Parameters(FxSlot &slot, const uint8_t *payload, int id) noexcept {
  if(id<=0||id>=int(effect_data::kEffects.size())||slot.type<=1)return;
  const auto &definition=effect_data::kEffects[id];
  unsigned frequency=0, q=0, gain=0, graphic=0, tapCount=0;
  double tapDepth=0;
  for(unsigned i=0;i<definition.count;++i) {
    const auto &f=effect_data::kFields[definition.first+i];
    const std::string_view label(f.label);
    const int raw=Raw(payload,f);
    const double value=Display(raw,f.display);
    if(label=="Wet/Dry:")slot.amount=std::abs(value);
    if(id==7) {
      if(label.find("Fc [Hz]")!=label.npos&&frequency<4)slot.detail[kEqFreq+3*frequency++]=value;
      if(label=="Q:"&&q<4)slot.detail[kEqQ+3*q++]=value;
      if(label=="Gain[dB]:"&&gain<4)slot.detail[kEqGain+3*gain++]=value;
    }
    if(id==8 && label.find("Band ")==0 && graphic<7)slot.detail[kGraphicGain+graphic++]=value;
    if(id==8 && label=="Type:")slot.detail[kGraphicType]=raw;
    if((id==7||id==8) && label=="Trim:")slot.detail[kFxTrim]=raw;
    if(label=="Ratio:")slot.detail[kRatio]=value;
    if(label=="Thrsh[dB]:")slot.detail[id==3?kCeiling:kThreshold]=id==5?raw/10.:value;
    if(label=="Ceil [dB]:")slot.detail[kCeiling]=raw/10.;
    // Ordinary limiter Attack/Release are indices, not milliseconds. Keep the
    // host defaults until the detector time law is recovered; do not relabel.
    if(label=="Rel [ms]:")slot.detail[kRelease]=value;
    if(label=="Drive:"||label=="1 Saturate:")slot.detail[kDrive]=value;
    if(label=="Blend:")slot.detail[kBlend]=std::abs(value);
    if(label=="Depth:")slot.detail[kDepth]=value;
    if(id==69 && label=="Dep:") { tapDepth+=value; ++tapCount; }
    if(label=="LFO [Hz]:"||label=="Speed[Hz]:")slot.detail[kLfoRate]=std::abs(value);
    if(label=="L Dly[ms]:")slot.detail[kDelayLeft]=value;
    if(label=="R Dly[ms]:")slot.detail[kDelayRight]=value;
    if(label=="L Feedbck:"||label=="Feedback:"||label=="Feedbck C:")slot.detail[kFeedback]=std::abs(value);
    if(label=="Time [s]:")slot.detail[kDecay]=value;
    if(label=="HiDamp[%]:")slot.detail[kHiDamp]=value;
  }
  // Four independent tap depths are represented by one depth in the current
  // chorus approximation. Preserve their mean instead of the unrelated default.
  if(tapCount) slot.detail[kDepth]=tapDepth/tapCount;
  for(int i=0;i<kFxDetailCount;++i)slot.detail[i]=std::clamp(slot.detail[i],kFxValues[i].min,kFxValues[i].max);
  slot.amount=std::clamp(slot.amount,0.,100.);
}
}
const char *ProgramEffects::Name(int id) noexcept {
  return id>=0&&id<int(effect_data::kEffects.size())?effect_data::kEffects[id].name:"Unknown effect";
}
ProgramEffects ProgramEffects::Decode(const uint8_t *program) noexcept {
  ProgramEffects result;
  for(auto &s:result.slots){s.type=1;s.amount=0;s.enabled=false;}
  if(!program)return result;
  int source=(program[0x50f]&31)-1, output=0, last=-1;
  std::array<unsigned,5> widths{};
  for (int i=0;i<5;++i) {
    const unsigned id=program[0x18+76*i+64];
    widths[i] = i && widths[i-1]==2 ? 0 : id < effect_data::kEffects.size() ? effect_data::kEffects[id].units : 1;
  }
  unsigned visited=0;
  while(source>=0&&source<5&&!(visited&(1u<<source))) {
    visited|=1u<<source;
    const int payload=0x18+76*source, id=program[payload+64];
    const bool enabled=program[payload+65]&64;
    last=payload;
    if(id>0&&enabled) {
      if(output<2) {
        auto &slot=result.slots[output];
        result.sourceIDs[output]=id;result.sourceSlots[output]=source;
        slot.type=HostType(id,false);slot.enabled=slot.type>1;slot.amount=100;
        Parameters(slot,program+payload,id);++output;
      } else ++result.omittedInserts;
    }
    if(!(program[payload+65]&128)||source==4)break;
    int target=std::clamp(int(program[payload+66]&15),source+2,5)-1;
    while (target < 5 && !widths[target]) ++target;
    source=target;
  }
  for(int i=0;i<2;++i) {
    const int payload=0x194+68*i, id=program[payload+64];
    result.sourceIDs[i+2]=id;
    auto &slot=result.slots[i+2];slot.type=HostType(id,true);
    slot.enabled=slot.type>1&&bool(program[payload+65]&64);slot.amount=100;
    Parameters(slot,program+payload,id);
    const double send=last>=0?program[last+70+i]/127.:program[0x6ae + i]/127.;
    slot.amount*=send*program[0x21c+i]/127.;
  }
  result.masterChain=bool(program[0x21e]&2);
  return result;
}
} // namespace segrand
