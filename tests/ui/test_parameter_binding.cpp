#include "editor/ParameterBinding.h"
#include <cassert>
#include <iostream>
#include <string>
#include <vector>
struct Parameter {
  double value = .55;
  double GetMin() const { return .05; }
  double GetMax() const { return 1.05; }
  double GetStep() const { return .1; }
  double Value() const { return value; }
  double ToNormalized(double v) const { return v - GetMin(); }
};
struct Delegate {
  Parameter parameters[2];
  std::vector<std::string> calls;
  Parameter *GetParam(int id) { return &parameters[id]; }
  void BeginInformHostOfParamChangeFromUI(int id) { calls.push_back("begin" + std::to_string(id)); }
  void EndInformHostOfParamChangeFromUI(int id) { calls.push_back("end" + std::to_string(id)); }
  void SendParameterValueFromUI(int id, double normalized) {
    calls.push_back("set" + std::to_string(id));
    parameters[id].value = parameters[id].GetMin() + normalized;
  }
};
int main() {
  krose::ui::ParameterBinding<2> bindings;
  Delegate delegate;
  assert(bindings.Changed(delegate) && !bindings.Changed(delegate));
  assert(!bindings.Set(delegate, 0, .55) && delegate.calls.empty());
  assert(bindings.Set(delegate, 0, .24)); // Snap relative to the parameter minimum.
  assert(std::abs(delegate.parameters[0].value - .25) < 1e-12);
  assert((delegate.calls == std::vector<std::string>{"begin0", "set0", "end0"}));
  delegate.calls.clear();
  bindings.Begin(delegate, 1);
  bindings.Begin(delegate, 1);
  bindings.Set(delegate, 1, .75, false);
  bindings.Set(delegate, 1, .85, false);
  bindings.End(delegate);
  bindings.End(delegate);
  assert((delegate.calls == std::vector<std::string>{"begin1", "set1", "set1", "end1"}));
  // Host automation/state restoration is read from the delegate, including
  // during a drag. A new discrete gesture closes an interrupted drag once.
  bindings.Changed(delegate);
  delegate.parameters[1].value = .15;
  assert(bindings.Changed(delegate) && !bindings.Changed(delegate));
  bindings.Begin(delegate, 0);
  delegate.calls.clear();
  bindings.Set(delegate, 1, 999);
  assert((delegate.calls == std::vector<std::string>{"end0", "begin1", "set1", "end1"}));
  assert(delegate.parameters[1].value == 1.05);
  delegate.calls.clear();
  assert(!bindings.Set(delegate, -1, .5) && !bindings.Set(delegate, 2, .5));
  assert(!bindings.Set(delegate, 0, NAN) && delegate.calls.empty());
  std::cout << "PASS parameter snapping, no-op writes, balanced gestures, cancellation and host restoration\n";
}
