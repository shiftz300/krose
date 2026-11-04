// The bridge is present only in the installed editor. All ABI indices are
// supplied by the plugin so that the panel never guesses a host parameter ID.
window.kroseNative = (() => {
  const send = message => window.IPlugSendMsg(message);
  const ids = new Map();
  const dragging = new Set();
  let apply;
  return {
    connect(receive) {
      apply = receive;
    },
    receive(name, id, value) {
      ids.set(name, id);
      if (apply && !dragging.has(name)) apply(name, value);
    },
    begin(name) {
      if (!ids.has(name) || dragging.has(name)) return;
      dragging.add(name);
      send({type: 'begin', id: ids.get(name)});
    },
    end(name) {
      if (dragging.delete(name)) send({type: 'end', id: ids.get(name)});
    },
    set(name, value) {
      if (!ids.has(name) || !Number.isFinite(value)) return;
      const id = ids.get(name), single = !dragging.has(name);
      if (single) send({type: 'begin', id});
      send({type: 'set', id, value});
      if (single) send({type: 'end', id});
    },
    midi(status, data1, data2) { send({type: 'midi', status, data1, data2}); }
  };
})();
