#include "midi/Arpeggiator.h"
#include <algorithm>
#include <cmath>

namespace segrand {
void Arpeggiator::Prepare(double sampleRate) noexcept {
  mRate = sampleRate;
  Reset();
}
void Arpeggiator::Reset() noexcept {
  mChannels = {};
  mBeat = 0;
  mRandom = 1;
  mTransportSeen = false;
  mRoutingReset = mRestart = mDropReleased = false;
  UpdateClock();
}
void Arpeggiator::SetControls(ArpControls c) noexcept {
  c.pattern = std::clamp(c.pattern, 0, kArpPatternCount-1);
  c.swing = std::clamp(c.swing, -100, 100);
  c.velocity = std::clamp(c.velocity, 1, 129);
  c.resolution = std::clamp(c.resolution, 0, 7);
  c.gate = std::clamp(c.gate, 1, 101);
  c.octaves = std::clamp(c.octaves, 1, 4);
  c.tempo = std::isfinite(c.tempo) ? std::clamp(c.tempo, 20., 300.) : 120.;
  if (c.enabled != mControls.enabled || c.keyboard != mControls.keyboard)
    mRoutingReset = true;
  if (c.pattern != mControls.pattern || c.resolution != mControls.resolution ||
      c.octaves != mControls.octaves || c.sort != mControls.sort ||
      c.keySync != mControls.keySync || c.hostSync != mControls.hostSync)
    mRestart = true;
  if (!c.latch && mControls.latch)
    mDropReleased = true;
  if (c.hostSync != mControls.hostSync)
    mTransportSeen = false;
  mControls = c;
  UpdateClock();
}
void Arpeggiator::UpdateClock() noexcept {
  const bool host = mControls.hostSync && mTransport.available;
  mTempo = host ? mTransport.tempo : mControls.tempo;
  mClockRunning = !host || mTransport.running;
  mIncrement = mTempo / (60 * mRate);
}
void Arpeggiator::SetTransport(Transport t) noexcept {
  t.available = t.available && std::isfinite(t.tempo) && t.tempo > 0 && t.tempo <= 1000 &&
                std::isfinite(t.ppq);
  const bool wasRunning = mClockRunning;
  const bool hadHost = mControls.hostSync && mTransport.available;
  const bool relocated = mTransport.midiClock != t.midiClock ||
                         mTransport.positionRevision != t.positionRevision;
  mTransport = t;
  UpdateClock();
  if (mControls.hostSync && t.available) {
    const double phaseError = t.ppq - mBeat;
    if (!mTransportSeen || !hadHost || wasRunning != mClockRunning || relocated ||
        (!t.midiClock && t.running && std::abs(phaseError) > 4 * mIncrement)) {
      mBeat = t.ppq;
      mRestart = true;
    } else if (t.midiClock && t.running) {
      // Follow a jittery MIDI pulse train without stopping sounding notes.
      // Explicit Start and Song Position still re-anchor the sequence.
      const double limit = mIncrement * .25;
      mIncrement += std::clamp(phaseError / (mRate * .15), -limit, limit);
    }
    mTransportSeen = true;
  } else if (hadHost)
    mRestart = true;
}
void Arpeggiator::Channel::Remove(unsigned note) noexcept {
  if (!velocity[note])
    return;
  unsigned at = 0;
  while (at < count && order[at] != note)
    ++at;
  for (unsigned i = at + 1; i < count; ++i)
    order[i - 1] = order[i];
  if (at < count)
    --count;
  velocity[note] = 0;
  down[note] = false;
}
void Arpeggiator::Channel::RemoveReleased() noexcept {
  if (pedal)
    return;
  for (unsigned note = 0; note < 128; ++note)
    if (!down[note])
      Remove(note);
}
unsigned Arpeggiator::Channel::Ordered(unsigned index, bool sort) const noexcept {
  if (!sort)
    return order[index];
  for (unsigned note = 0; note < 128; ++note)
    if (velocity[note] && index-- == 0)
      return note;
  return 0;
}
uint16_t Arpeggiator::RandomNext(uint16_t s) noexcept {
  return uint16_t((s << 1) | ((s ^ (s >> 2) ^ (s >> 11) ^ (s >> 15)) & 1));
}
unsigned Arpeggiator::Position(int pattern, unsigned n, uint64_t step, uint16_t &random) noexcept {
  if (!n)
    return 0;
  switch (pattern) {
  case 1:
    return n - 1 - unsigned(step % n);
  case 2: {
    if (n == 1)
      return 0;
    const auto at = unsigned(step % (2 * n - 2));
    return at < n ? at : 2 * n - 2 - at;
  }
  case 3: {
    const auto at = unsigned(step % (2 * n));
    return at < n ? at : 2 * n - 1 - at;
  }
  case 4:
    random = RandomNext(random);
    return random % n;
  default:
    return unsigned(step % n);
  }
}
void Arpeggiator::Silence(int channel, int offset, void *context, Emit emit) noexcept {
  auto &c = mChannels[channel];
  if (c.sounding >= 0)
    emit(context, {offset, uint8_t(0x80 | channel), uint8_t(c.sounding), 0});
  c.sounding = -1;
  c.eventDue = 1e100;
  for(auto &note:c.notes) {
    if(note.pitch>=0 && note.playing) emit(context,{offset,uint8_t(0x80|channel),uint8_t(note.pitch),0});
    note = {};
  }
}
void Arpeggiator::Schedule(Channel &c) noexcept {
  const double step = kTicks[mControls.resolution] / 480.;
  c.next = mControls.keySync ? mBeat : std::ceil((mBeat - 1e-10) / step) * step;
  c.step = 0;
  c.scheduled = true;
}
void Arpeggiator::Input(MidiEvent e, int offset, void *context, Emit emit) noexcept {
  e.offset = offset;
  e.data1 &= 127;
  e.data2 &= 127;
  const int channel = e.status & 15, type = e.status & 240;
  auto &c = mChannels[channel];
  if (type == 0x90 && e.data2) {
    c.RemoveReleased();
    const bool first = c.count == 0;
    if (!c.velocity[e.data1])
      c.order[c.count++] = e.data1;
    c.down[e.data1] = true;
    c.velocity[e.data1] = e.data2;
    if (first)
      Schedule(c);
    if (mControls.keyboard) emit(context,e);
    return;
  }
  if (type == 0x80 || (type == 0x90 && !e.data2)) {
    c.down[e.data1] = false;
    if (!mControls.latch && !c.pedal)
      c.Remove(e.data1);
    if (!c.count) {
      Silence(channel, offset, context, emit);
      c.scheduled = false;
    }
    if (mControls.keyboard) emit(context,e);
    return;
  }
  if (type == 0xb0) {
    if (e.data1 == 64) {
      c.pedal = e.data2 >= 64;
      if (!mControls.latch)
        c.RemoveReleased();
      if (!c.count) {
        Silence(channel, offset, context, emit);
        c.scheduled = false;
      }
      return; // Pedal holds the source keys, not every generated note.
    }
    if (e.data1 == 120 || e.data1 == 123) {
      Silence(channel, offset, context, emit);
      c = {};
    } else if (e.data1 == 121) {
      c.pedal = false;
      if (!mControls.latch)
        c.RemoveReleased();
      if (!c.count) {
        Silence(channel, offset, context, emit);
        c.scheduled = false;
      }
    }
  }
  emit(context, e);
}
void Arpeggiator::Process(int frames, const MidiEvent *events, unsigned count, void *context,
                          Emit emit) noexcept {
  if (frames <= 0)
    return;
  if (mRoutingReset) {
    for (int ch = 0; ch < 16; ++ch) {
      Silence(ch, 0, context, emit);
      emit(context, {0, uint8_t(0xb0 | ch), 64, 0});
      emit(context, {0, uint8_t(0xb0 | ch), 120, 0});
    }
    mChannels = {};
    mRandom = 1;
    mRoutingReset = false;
  }
  if (mRestart || mDropReleased) {
    for (int ch = 0; ch < 16; ++ch) {
      auto &c = mChannels[ch];
      if (mDropReleased)
        c.RemoveReleased();
      if (mRestart || !c.count) {
        Silence(ch, 0, context, emit);
        c.scheduled = false;
      }
    }
    mRestart = mDropReleased = false;
  }
  if (!mControls.enabled) {
    for (unsigned i = 0; i < count; ++i)
      emit(context, events[i]);
    if (mClockRunning)
      mBeat += frames * mIncrement;
    return;
  }
  unsigned input = 0;
  const double step = kTicks[mControls.resolution] / 480.;
  for (int frame = 0; frame < frames; ++frame) {
    while (input < count && events[input].offset == frame)
      Input(events[input++], frame, context, emit);
    for (int ch = 0; ch < 16; ++ch) {
      auto &c = mChannels[ch];
      if (!mClockRunning || !c.count)
        continue;
      if (!c.scheduled)
        Schedule(c);
      if (mControls.pattern >= 5) {
        if (mBeat + 1e-10 >= c.next) PatternStep(c, ch, frame, step, context, emit);
        if (mBeat + 1e-10 >= c.eventDue) PatternNotes(c, ch, frame, context, emit);
        continue;
      }
      if (c.sounding >= 0 && mBeat + 1e-10 >= c.off)
        Silence(ch, frame, context, emit);
      if (mBeat + 1e-10 >= c.next) {
        Silence(ch, frame, context, emit);
        const unsigned at =
            Position(mControls.pattern, c.count * mControls.octaves, c.step++, mRandom);
        const unsigned source = c.Ordered(at % c.count, mControls.sort);
        int note = int(source) + 12 * int(at / c.count);
        while (note > 127)
          note -= 12;
        c.sounding = note;
        emit(context, {frame, uint8_t(0x90 | ch), uint8_t(note), c.velocity[source]});
        c.off = c.next + step * mControls.gate / 100.;
        c.next += step;
      }
    }
    if (mClockRunning)
      mBeat += mIncrement;
  }
}
} // namespace segrand

namespace segrand {
void Arpeggiator::PatternNotes(Channel &c, int channel, int frame, void *context, Emit emit) noexcept {
  c.eventDue = 1e100;
  for (auto &note : c.notes) {
    if(note.pitch < 0) continue;
    if(!note.playing && mBeat+1e-10>=note.on) {
      emit(context,{frame,uint8_t(0x90|channel),uint8_t(note.pitch),uint8_t(note.velocity)});
      note.playing=true;
      for (auto &previous : c.notes) {
        if (&previous != &note && previous.pitch >= 0 && previous.playing && previous.tie && previous.tone == note.tone) {
          emit(context,{frame,uint8_t(0x80|channel),uint8_t(previous.pitch),0});
          previous = {};
        }
      }
    }
    if(note.playing && mBeat+1e-10>=note.off) {
      emit(context,{frame,uint8_t(0x80|channel),uint8_t(note.pitch),0});note={};
    }
    if (note.pitch >= 0) c.eventDue = std::min(c.eventDue, note.playing ? note.off : note.on);
  }
}
void Arpeggiator::PatternStep(Channel &c, int channel, int frame, double step,
                              void *context, Emit emit) noexcept {
  const auto pattern=Pattern(mControls.pattern);
  const unsigned length=unsigned(pattern.Length()), index=unsigned(c.step%length);
  const auto data=pattern.Step(index);
  auto swing = [&](unsigned at) {
    const unsigned group=1u<<std::min(2u,pattern.SwingGrid());
    return at<length && at%(2*group)==group ? step*mControls.swing/100. : 0.;
  };
  const double origin=c.next;
  c.next+=step-swing(index)+swing((index+1)%length);
  // Pattern wrap ends on the original bar grid, without accumulating swing.
  if(index+1==length)c.next-=swing(0);
  const auto cycle=c.step++/length;
  if(!data.tones)return;
  const unsigned flags=pattern.Flags(), kind=(flags>>2)&3;
  const bool fixed=flags&16, all=flags&32;
  std::array<unsigned,12> sources{};
  std::array<int,12> pitches{};
  unsigned count=0;
  const int motion=int(flags&3);
  const auto octave=motion == 3 ? 0u : Position(motion,mControls.octaves,cycle,mRandom);
  for(unsigned tone=0;tone<12;++tone) {
    if(!(data.tones&(1u<<tone)))continue;
    unsigned source=tone;
    if(!(fixed&&all)&&tone>=c.count) {
      if(kind==0)source=tone;
      else if(kind==1)source=c.count-1;
      else if(kind==2)source=tone%c.count;
      else {
        const unsigned period=c.count>1?2*c.count-2:1, at=tone%period;
        source=at<c.count?at:period-at;
      }
    }
    if(!(fixed&&all) && std::find(sources.begin(),sources.begin()+count,source)!=sources.begin()+count)continue;
    const unsigned note=c.Ordered(source%c.count,mControls.sort);
    int pitch=fixed?pattern.Note(tone):source<c.count?int(note):-1000;
    pitch+=data.pitch+12*int(octave);
    if (source < c.count || (fixed && all)) {
      while(pitch<0)pitch+=12;
      while(pitch>127)pitch-=12;
    }
    sources[count]=source;pitches[count++]=pitch;
  }
  if(data.flam<0) {
    std::reverse(sources.begin(),sources.begin()+count);
    std::reverse(pitches.begin(),pitches.begin()+count);
  }
  for(unsigned i=0;i<count;++i) {
    const int basePitch=pitches[i];
    if (basePitch < 0) continue;
    for (int parallel = 0; parallel < (motion == 3 && mControls.octaves > 1 ? 2 : 1); ++parallel) {
    int pitch = basePitch + 12 * (mControls.octaves-1) * parallel;
    while (pitch > 127) pitch -= 12;
    const int tone = int(sources[i])*2 + parallel;
    if (!data.gate) {
      for (auto &old : c.notes) if (old.pitch >= 0 && old.tone == tone) {
        if (old.playing) emit(context,{frame,uint8_t(0x80|channel),uint8_t(old.pitch),0});
        old={};
      }
      continue;
    }
    const auto source=c.Ordered(sources[i]%c.count,mControls.sort);
    int velocity=mControls.velocity==129?data.velocity:mControls.velocity;
    if(velocity>=128)velocity=c.velocity[source];
    const int gate=mControls.gate==101?data.gate:mControls.gate;
    const double delay=std::ceil(step*480*std::abs(data.flam)*i/(100.*std::max(1u,count))) / 480.;
    const double start=origin+delay;
    const double on=start+((fixed&&all&&c.step==1)?2./480:0);
    const double off=gate==101 ? 1e100 : start+std::floor(std::max(0.,c.next-start)*480*std::clamp(gate,1,100)/100.+1e-9)/480.;
    auto slot=std::find_if(c.notes.begin(),c.notes.end(),[](const auto &n){return n.pitch<0;});
    if(slot==c.notes.end())continue; // Original active-note capacity is twenty.
    *slot={pitch,std::clamp(velocity,1,127),tone,false,gate==101,on,off};
    c.eventDue = std::min(c.eventDue, on);
    }
  }
}
} // namespace segrand
