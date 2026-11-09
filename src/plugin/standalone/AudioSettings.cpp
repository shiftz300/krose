#include "../KrosePlugin.h"
#if defined(APP_API)
#include "IPlugAPP_host.h"
#endif
unsigned KrosePlugin::AudioBufferSize() const {
#if defined(APP_API)
  auto *host = static_cast<IPlugAPPHost *>(mStandaloneHost);
  return host ? host->AudioBufferSize() : 0;
#else
  return unsigned(std::max(0, GetBlockSize()));
#endif
}
bool KrosePlugin::SetAudioBufferSize(unsigned frames) {
#if defined(APP_API)
  auto *host = static_cast<IPlugAPPHost *>(mStandaloneHost);
  return host && host->SetAudioBufferSize(frames);
#else
  return false;
#endif
}

std::vector<std::string> KrosePlugin::AudioChoices(int kind) {
#if defined(APP_API)
  auto *host = static_cast<IPlugAPPHost *>(mStandaloneHost);
  try { return host ? host->AudioChoices(kind) : std::vector<std::string>{}; }
  catch (const std::exception &) { return {}; }
#else
  return {};
#endif
}
std::string KrosePlugin::AudioChoice(int kind) {
#if defined(APP_API)
  auto *host = static_cast<IPlugAPPHost *>(mStandaloneHost);
  return host ? host->AudioChoice(kind) : "Audio off";
#else
  return "Host / DAW";
#endif
}
bool KrosePlugin::SelectAudioChoice(int kind, const std::string &value) {
#if defined(APP_API)
  auto *host = static_cast<IPlugAPPHost *>(mStandaloneHost);
  try { return host && host->SelectAudioChoice(kind, value); }
  catch (const std::exception &) { return false; }
#else
  return false;
#endif
}
