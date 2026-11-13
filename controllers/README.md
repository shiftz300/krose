# Controller support kit

This directory is the project's fixed home for maintained adapters and extension
templates. Default app and VST3 builds include a copy in `Resources/Controllers`.
Native device-protocol implementations remain in `src/plugin/midi` and
`src/plugin/standalone`; user JSON profiles reuse that compiled MIDI engine.
On macOS this is inside the bundle's `Contents/Resources`. Do not edit the signed
bundle: copy the desired template to a user directory first.

- `ableton/Remote Scripts/Krose_KeyLab_Essential`: maintained mk3 adapter.
- `ableton/Defaults`: Krose parameter configuration for Live.
- `fl-studio/Krose_KeyLab_Essential`: maintained mk3 adapter for FL Studio.
- `shared/keylab-essential-mk3`: source of the protocol and preset catalog modules staged into both host adapters.
- `reaper`: action to select the MIDI input on one Krose track.
- `bitwig`: one input-only controller script that passes MIDI to the instrument track.
- `profiles/builtin`: data-only mappings for standalone and VST3 hosts.
- `templates/standalone/generic-keyboard.json`: editable mapping template.
- `templates/ableton`: a minimal input-only Python control-surface template.
- `schema.json`: editor schema for profiles.

Krose: **LCD > CTRL > INPUT > PROFILES** lists built-in and user mappings. It also
exports the current mapping, opens the user profile folder, and opens this kit.
Copy a standalone JSON template into the user folder, edit its name and bindings,
then reopen PROFILES and choose it. Confirm replacement; use STORE to retain it
in a USER slot. Invalid files appear as INVALID and cannot replace the current map. Export creates a new file, leaving existing user files untouched.
Turn off the native Arturia adapter before replacing its fixed hardware mapping.

The profile folder is `Krose/Controllers/Profiles` under iPlug's per-user application
support directory (on macOS: `~/Library/Application Support`). Krose opens it for
you; it is outside installed bundles and is not removed by installer updates.
Mappings are loaded explicitly, never by scanning scripts on startup. Unknown
fields/targets, invalid ranges and oversized or deeply nested JSON are rejected
before the active mapping changes. The format supports no code, shell commands,
network URLs, file paths or outbound MIDI/SysEx instructions.

Ableton: copy `ableton/Remote Scripts/Krose_KeyLab_Essential` into your Live User
Library's `Remote Scripts`, and merge `ableton/Defaults` into its `Defaults`.
Alternatively, run the included `install_ableton_controller.py --user-library PATH`
with Python 3; it preserves custom configuration and backs up replaced scripts.
Restart Live and choose the surface/ports once. See `CONTROLLERS.md` in the built
kit for device-specific setup. The repository installer is also available under
`tools/install_ableton_controller.py`.

FL Studio: copy the built `fl-studio/Krose_KeyLab_Essential` folder into the
FL Studio user data folder under `Settings/Hardware`. Select
**Krose KeyLab Essential mk3 (user)** for the keyboard's MIDI input and assign
the same port number to the matching MIDI output. See the FL Studio section of
`CONTROLLERS.md` in the built kit.

DAWs run the scripts you select or launch with host permissions. REAPER and
Bitwig use the shared Krose mapping engine via the instrument track's MIDI input.
Only the dedicated KeyLab adapters send controller feedback. See
`CONTROLLERS.md` for keyboard modes, CC assignments and host setup.

Disable distribution of the kit with `-DKROSE_BUNDLE_CONTROLLERS=OFF` if desired;
the existing native MIDI engine and compiled KeyLab adapter remain available.
