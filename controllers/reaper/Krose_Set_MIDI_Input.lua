-- Set the MIDI input of one selected Krose instrument track.
local r = reaper
local function notify(message)
    r.ShowMessageBox(message, "Krose MIDI Input", 0)
end

local function krose_instance(track)
    local fx = r.TrackFX_GetInstrument(track)
    if fx < 0 then return end
    local ok, name = r.TrackFX_GetNamedConfigParm(track, fx, "fx_name")
    if not ok then return end
    name = name:gsub("^VST3i?:%s*", ""):gsub("%s+%([^()]*%)$", "")
    if name ~= "Krose" then return end
    local signature = {
        Program = true, ["Amp Attack"] = true, ["Arp Latch"] = true,
        ["IFX 1 Type"] = true, ["MFX 2 On"] = true,
    }
    for p = 0, math.min(r.TrackFX_GetNumParams(track, fx), 4096) - 1 do
        local found, label = r.TrackFX_GetParamName(track, fx, p, "")
        if found then signature[label] = nil end
        if next(signature) == nil then return r.TrackFX_GetFXGUID(track, fx) end
    end
end

if r.CountSelectedTracks(0) ~= 1 then
    return notify("Select exactly one track with Krose as its instrument.")
end
local track = r.GetSelectedTrack(0, 0)
local instance = krose_instance(track)
if not instance then
    return notify("The selected track must use Krose as its first instrument.")
end

-- 62 and 63 are REAPER's virtual keyboard and all-inputs selectors.
local ports, list = {}, {}
for id = 0, math.min(r.GetNumMIDIInputs(), 62) - 1 do
    local found, name = r.GetMIDIInputName(id, "")
    if found then
        ports[id] = name
        list[#list + 1] = id .. ": " .. name:gsub("[%c]", " ")
    end
end
if not next(ports) then return notify("Enable your keyboard's MIDI input in REAPER Preferences.") end
notify("Choose the keyboard's performance MIDI port.\n\n" .. table.concat(list, "\n"))
local accepted, text = r.GetUserInputs("Krose MIDI Input", 1, "Input port number", "")
if not accepted then return end
local id = #text <= 8 and tonumber(text:match("^%s*(%d+)%s*$"))
if not id or not ports[id] then return notify("Choose one of the listed port numbers.") end

local found, name = r.GetMIDIInputName(id, "")
if not found or name ~= ports[id] or r.CountSelectedTracks(0) ~= 1
    or r.GetSelectedTrack(0, 0) ~= track or krose_instance(track) ~= instance then
    return notify("The port or selected instrument changed. Run the action again.")
end
local input = 4096 + id * 32 -- MIDI, chosen physical port, all channels
if r.GetMediaTrackInfo_Value(track, "I_RECINPUT") == input then return end
if r.SetMediaTrackInfo_Value(track, "I_RECINPUT", input) then
    r.Undo_OnStateChangeEx("Set Krose track MIDI input", 1, -1)
else
    notify("REAPER could not set the track input.")
end
