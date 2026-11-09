#include "midi/ArpPatterns.h"
#include "ArpPatternData.h"
#include <algorithm>
#include <cstring>
namespace segrand {
int ArpPattern::Length() const noexcept { return bytes ? std::clamp(int(bytes[25]),1,64) : 1; }
ArpStep ArpPattern::Step(unsigned i) const noexcept {
  if(!bytes)return {};
  const auto *p=bytes+40+8*(i%unsigned(Length()));
  return {int(int8_t(p[0])),p[1],p[2],int(int8_t(p[3])),unsigned(p[4])|(unsigned(p[5]&15)<<8)};
}
ArpPattern Pattern(int index) noexcept {
  return {index>=5 && index<kArpPatternCount ? kArpPatternBytes+(index-5)*552 : nullptr};
}
std::array<char,25> ArpPatternName(int index) noexcept {
  std::array<char,25> result{};
  static const char *builtins[]={"UP","DOWN","ALT 1","ALT 2","RANDOM"};
  if(index>=0&&index<5)std::copy_n(builtins[index],std::strlen(builtins[index]),result.begin());
  else if(auto pattern=Pattern(index);pattern.bytes)std::copy_n(pattern.bytes,24,result.begin());
  else std::copy_n("UNKNOWN",7,result.begin());
  for(int i=23;i>=0&&result[i]==' ';--i)result[i]=0;
  return result;
}
} // namespace segrand
