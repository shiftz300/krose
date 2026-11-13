loadAPI(1);
host.defineController("maincore", "Krose MIDI", "1.0", "9dc816be-1d3f-4d8f-a79a-481b3f47c273", "maincore");
host.defineMidiPorts(1, 0);

function init() {
    // Pass channel voice messages to the track. Krose interprets its own CC map.
    host.getMidiInPort(0).createNoteInput("Krose MIDI",
        "8?????", "9?????", "A?????", "B?????", "C?????", "D?????", "E?????");
}

function flush() {}
function exit() {}
