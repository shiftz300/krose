// Local reference model for material/font exports. No plugin or host ABI.
window.kroseNative = {
  connect(receive) { this.apply = receive; },
  receive(name, _id, value) { this.apply?.(name, value); },
  begin() {},
  end() {},
  set() {},
  midi() {}
};
