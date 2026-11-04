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
  c.pattern = std::clamp(c.pattern, 0, 4);
  c.resolution = std::clamp(c.resolution, 0, 7);
  c.gate = std::clamp(c.gate, 1, 100);
  c.octaves = std::clamp(c.octaves, 1, 4);
  c.tempo = std::isfinite(c.tempo) ? std::clamp(c.tempo, 20., 300.) : 120.;
  if (c.enabled != mControls.enabled)
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
  mTransport = t;
  UpdateClock();
  if (mControls.hostSync && t.available) {
    if (!mTransportSeen || !hadHost || wasRunning != mClockRunning ||
        (t.running && std::abs(t.ppq - mBeat) > 4 * mIncrement)) {
      mBeat = t.ppq;
      mRestart = true;
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
