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
