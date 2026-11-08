#include "midi/KeyLabEssential.h"
#include "midi/KeyLabControls.h"
#include "midi/KeyLabParameters.h"
#include "standalone/MidiDevices.h"
#include <cassert>
#include <iostream>
using namespace krose::midi::essential;
int main() {
  FxButtonPresses presses;
  assert(presses.Input(0,true,1)==FxPressAction::None);
  assert(presses.Tick(1.3)==0);
  assert(presses.Input(0,false,1.3)==FxPressAction::Edit);
  assert(presses.Input(0,false,1.4)==FxPressAction::None);
  for (unsigned i=0;i<4;++i) assert(presses.Input(i,true,2)==FxPressAction::None);
  presses.Input(0,true,2.3); // Auto-repeat does not postpone the threshold.
  assert(presses.Tick(2.59)==0 && presses.Tick(2.61)==15);
  assert(presses.Tick(9)==0);
  for (unsigned i=0;i<4;++i) assert(presses.Input(i,false,9)==FxPressAction::None);
  presses.Input(1,true,10);
  assert(presses.Input(1,false,10.61)==FxPressAction::Toggle);
  presses.Input(0,true,11);presses.Reset();
  assert(presses.Tick(12)==0 && presses.Input(0,false,12)==FxPressAction::None);
  const std::array<int,9> expectedKnobs{{kGlide,kParamProgram,kParamPan,kParamCutoff,kParamResonance,kParamVelocity,kParamOutput,-1,-1}};
  for (unsigned i=0; i<9; ++i) assert(kKnobControls[i].parameter==expectedKnobs[i]);
  assert(std::string(kKnobControls[6].label)=="Volume");
  assert(kFaderParameters[0]==kAmpAttack && kFaderParameters[4]==kFilterAttack && kFaderParameters[8]==kParamOutput);
  for (unsigned i=0;i<4;++i) {
    assert(FaderParameter(i,false)==kAmpAttack+int(i) && FaderParameter(i,true)==kFilterAttack+int(i));
    assert(FaderParameter(i+4,false)==kFilterAttack+int(i) && FaderParameter(i+4,true)==kAmpAttack+int(i));
  }
  assert(FaderParameter(8,true)==kParamOutput && FaderParameter(9,true)==-1);
  const auto screen = Display("Cutoff", "+12");
  assert(screen.size() == 52 && screen[7] == 1 && screen[9] == 0x12 && screen[10] == 1);
  assert(screen[29] == 0 && screen[30] == 2 && screen[49] == 0 && screen[50] == 0 && screen[51] == 247);
  assert(Line("abcdefghijklmnopqrst") == "abcdefghijklmnopqr");
  assert(Ascii("FX\n\xc3\xa9\xe4\xb8\xad") == "FX???");
  assert(Pad(0, true) == Command({4, 1, 22, 32, 48, 90, 90, 32}));
  assert(Pad(7, false) == Command({4, 1, 22, 31, 0, 0, 0, 32}));
  assert(Pad(8, true).empty());
  assert(FxButton(0,EffectColour(4))==Command({4,1,22,24,127,104,24,32}));
  assert(FxButton(3,{0,0,0})==Command({4,1,22,27,0,0,0,32}));
  assert(FxButton(4,{1,2,3}).empty());
  for (unsigned algorithm=2;algorithm<15;++algorithm) {
    assert((EffectColour(algorithm,false)==RGB{0,0,0}));
    for (unsigned other=2;other<algorithm;++other) assert(EffectColour(algorithm)!=EffectColour(other));
  }
  assert(DisplayHeader("FX / MFX 2") == Command({4,1,96,1,2,'F','X',' ','/',' ','M','F','X',' ','2',0,0}));
  assert(CategoryIcon("PIANO") == 0x28 && CategoryIcon("BASS") == 3);
  assert(ParameterLabel("MFX 2 Release") == "MFX2 Rel");
  assert(ProgramLine("Breathy Bells",0) == "Breathy Bell");
  assert(ProgramLine("Breathy Bells",1.6) == "reathy Bells");
  assert(ProgramLine("Breathy Bells",2.7) == "reathy Bells");
  assert(ProgramLine("Breathy Bells",2.8) == "Breathy Bell");
  assert(ProgramLine("Short Piano",100) == "Short Piano");
  assert(DisplayIcon("Piano", "A000", 0x28) == Command({4,1,96,0x19,1,'P','i','a','n','o',0,2,'A','0','0','0',0,3,0x28,0,0}));
  assert(ControlDisplay(3,"Cutoff","+42") == Command({4,1,96,32,3,32,1,'C','u','t','o','f','f',0,2,'+','4','2',0,3,99,0}));
  for (unsigned i=0; i<18; ++i) {
    const auto packet = ControlDisplay(i,"EG","0");
    const unsigned cc = i<8 ? 96+i : i<16 ? 105+i-8 : i==16 ? 104 : 113;
    assert(packet[10]==i && packet[packet.size()-3]==cc);
  }
  assert(ControlDisplay(18,"bad","0").empty());
  assert(ProgramKnobDelta(65,64)==1 && ProgramKnobDelta(63,64)==-1 && ProgramKnobDelta(127,64)==63);
  assert(ProgramKnobDelta(127,0)==127 && ProgramKnobDelta(0,127)==-127);
  assert(ProgramKnobDelta(15,-1)==0); // First absolute position only establishes a baseline.
  assert(ParameterPage("MFX 2 Send") == "FX / MFX 2");
  assert(ParameterPage("Arp Gate") == "ARP");
  assert(PortScore("KL Essential 49 mk3 (MIDI)") == 2);
  for (const char *bad : {"KeyLab Essential 49", "KeyLab mkII", "KL Essential 49 mk3 (ALV)",
                          "KL Essential 49 mk3 (MCU/HUI)", "KL Essential 49 mk3 (DINTHRU)"})
    assert(!PortScore(bad));
  assert(FindPort({"KL Essential 49 mk3 (MIDI)", "KL Essential 61 mk3 (MIDI)"}) == -1);
  assert(krose::standalone::ChooseMidiInput("Automatic", "", {"KL Essential 49 mk3 (ALV)",
           "KL Essential 49 mk3 (MIDI)"}) == "KL Essential 49 mk3 (MIDI)");
  assert(Relative(63) == -1 && Relative(65) == 1 && Relative(64) == 0);
  assert(Decode(0xb0, 96).kind == Kind::Knob && Decode(0xb0, 113).index == 8);
  for (unsigned i=0;i<4;++i) {
    assert(Decode(0xb0,44+i).kind==Kind::FxEdit && Decode(0xb0,44+i).index==i);
    assert(Decode(0xb1,44+i).kind==Kind::None);
  }
  assert(Decode(0xba, 96).kind == Kind::None && Decode(0x90, 36).kind == Kind::None);
  assert(Decode(0x9a, 40).kind == Kind::Pad && Decode(0x9a,40).index == 0 && Decode(0x8a,39).index == 7);
  for (unsigned n : {1u, 7u, 10u, 64u, 120u, 123u}) assert(Decode(0xb0, n).kind == Kind::None);
  Pickup pickup;
  assert(!pickup.Accept(0, 0, .5));
  Pickup bankPickup;
  assert(bankPickup.Accept(0,.5,.5) && bankPickup.Accept(8,.5,.5));
  bankPickup.Reset(0,8);
  assert(!bankPickup.Accept(0,0,.5));
  assert(bankPickup.Accept(8,.1,.5));
  assert(!pickup.Accept(0, .3, .5));
  assert(pickup.Accept(0, .6, .5));
  assert(pickup.Accept(0, .7, .6));
  assert(!pickup.Accept(0, .6, .9)); // Automation re-arms takeover.
  pickup.Reset();
  assert(!pickup.Accept(0, 0, .5));
  // Fast sweeps must remain caught after integer EG parameter quantization.
  double target = .5;
  for (unsigned value : {80u, 110u, 127u, 95u, 40u, 0u, 90u}) {
    assert(pickup.Accept(0, value / 127., target));
    target = std::round((value / 127.) * 198) / 198;
    pickup.Applied(0, target);
  }
  assert(!pickup.Accept(0, .4, .95)); // Genuine external changes still rearm.
  assert(pickup.Accept(0, 1, .95));
  Feedback feedback;
  feedback.Program("A000 Kross GrandPiano 1");
  std::vector<Packet> sent;
  auto send = [&](auto p) { sent.push_back(p); };
  std::array<bool, 8> pads{};
  feedback.Tick(0, pads, send);
  assert(sent.size() == 10 && sent[1] == DisplayHeader("PROG"));
  assert(sent[0] == DisplayIcon("A000 Kross G", "", 0x28));
  feedback.Tick(.2, pads, send);
  assert(sent.size() == 10); // Idle deduplication.
  feedback.Parameter("Cutoff", "+42", .21);
  feedback.Tick(.22, pads, send);
  assert(sent.size() == 10); // Coalescing.
  pads[0] = true;
  feedback.Tick(.31, pads, send);
  assert(sent.size() == 13 && sent[10] == DisplayIcon("Cutoff", "+42",9) && sent[11] == DisplayHeader("TONE"));
  feedback.Tick(1.5, pads, send);
  assert(sent.size() == 15 && sent.back() == sent[1]); // Parameter timeout.
  feedback.Reset();
  feedback.Tick(1.51, pads, send);
  assert(sent.size() == 25); // Full snapshot after reconnect.
  Feedback physical;
  physical.Control(3,"Cutoff","0");
  sent.clear();
  physical.Tick(0,pads,send);
  assert(sent.front()==ControlDisplay(3,"Cutoff","0"));
  sent.clear();
  physical.ControlTouched(.11);
  physical.Control(3,"Cutoff","+42");
  physical.Tick(.11,pads,send);
  assert(sent.size()==1 && sent[0]==ControlDisplay(3,"Cutoff","+42"));
  physical.ControlTouched(.25); // Continuous turns must never recreate the page.
  physical.Control(3,"Cutoff","+99");
  pads[1]=true;
  physical.Tick(.3,pads,send);
  assert(sent.size()==3 && sent[1]==ControlDisplay(3,"Cutoff","+99") && sent[2]==Pad(1,true));
  physical.Tick(1.6,pads,send);
  assert(sent.size()==5 && sent[3]==DisplayIcon("Krose","",0x28) && sent[4]==DisplayHeader("PROG"));
  physical.Reset();
  sent.clear();
  physical.Tick(2,pads,send);
  assert(sent.size()==11 && sent[0]==ControlDisplay(3,"Cutoff","+99"));
  Feedback effects;
  const std::array<RGB,4> colours{{EffectColour(2),EffectColour(4),EffectColour(11),EffectColour(13)}};
  effects.FxButtons(colours);
  sent.clear();effects.Tick(0,pads,send);
  assert(sent.size()==14);
  for (unsigned i=0;i<4;++i) assert(sent[10+i]==FxButton(i,colours[i]));
  effects.Tick(.2,pads,send);assert(sent.size()==14);
  effects.Reset();effects.Tick(.4,pads,send);assert(sent.size()==28);
  std::cout << "KeyLab mk3 protocol, routing, pickup, feedback timing passed\n";
}
