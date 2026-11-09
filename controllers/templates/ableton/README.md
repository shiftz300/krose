# Generic Ableton template

Copy `Krose_Generic_Template` to your Live User Library's `Remote Scripts` folder.
Change `CHANNEL` and the `(CC number, Krose parameter name)` pairs in `surface.py`,
restart Live, then select this control surface and the desired input port manually.
Load/select Krose; the template controls only the selected Krose device. It does
not claim transport buttons, open a MIDI device or send any MIDI/SysEx feedback.

This is an absolute-CC starting point. Use the standalone JSON template for
relative encoders, pickup, note buttons, CC14, NRPN or RPN without Python code.
The maintained KeyLab Essential mk3 adapter provides the richer device-specific
display/LED/encoder handling. Its protocol must not be sent to other keyboards.

Python remote scripts run inside Live and are executable code. Inspect third-party
changes before copying them into Live. Templates are not installed automatically.
