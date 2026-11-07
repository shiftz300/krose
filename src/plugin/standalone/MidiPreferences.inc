// Included in the APP preferences translation unit, where dialog IDs exist.
void IPlugAPPHost::RefreshMidiPreferences() {
  if (!mMidiListDirty || !mMidiPreferences || !IsWindow(mMidiPreferences)) return;
#ifdef OS_WIN
  if (SendDlgItemMessage(mMidiPreferences, IDC_COMBO_MIDI_IN_DEV, CB_GETDROPPEDSTATE, 0, 0) ||
      SendDlgItemMessage(mMidiPreferences, IDC_COMBO_MIDI_OUT_DEV, CB_GETDROPPEDSTATE, 0, 0)) return;
#endif
  PopulateMidiDialogs(mMidiPreferences);
  mMidiListDirty = false;
}
