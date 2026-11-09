#include "UpdateCheck.h"
#include "json.hpp"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <mutex>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#include <winhttp.h>
#else
#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
#endif

namespace krose::updates {
std::string LatestReleaseVersion(const std::string &text) {
  if (text.size() > kMaxResponse) return {};
  try {
    const auto data = nlohmann::json::parse(text);
    if (!data.is_object() || data.value("draft", true) || data.value("prerelease", true)) return {};
    const auto tag = data.at("tag_name").get<std::string>();
    return Version(tag) ? tag : "";
  } catch (const std::exception &) { return {}; }
}
namespace {
#ifdef _WIN32
struct HttpHandle {
  HINTERNET value = nullptr;
  ~HttpHandle() { if (value) WinHttpCloseHandle(value); }
};
std::string Fetch(std::atomic<bool> &cancel) {
  HttpHandle session{WinHttpOpen(L"Krose update check", WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
                                 WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0)};
  // Automatic proxy discovery is only available starting with Windows 8.1.
  if (!session.value) {
    session.value = WinHttpOpen(L"Krose update check", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                                WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session.value) return {};
    // Win7 does not enable TLS 1.2 by default. Never fall back to obsolete TLS;
    // newer Windows keeps its system TLS defaults on the automatic-proxy path.
    DWORD protocols = WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2;
    if (!WinHttpSetOption(session.value, WINHTTP_OPTION_SECURE_PROTOCOLS, &protocols, sizeof(protocols))) return {};
  }
  if (!WinHttpSetTimeouts(session.value, 1500, 1500, 1500, 1500)) return {};
  HttpHandle connection{WinHttpConnect(session.value, L"api.github.com", INTERNET_DEFAULT_HTTPS_PORT, 0)};
  if (!connection.value || cancel.load()) return {};
  HttpHandle request{WinHttpOpenRequest(connection.value, L"GET",
      L"/repos/shiftz300/krose/releases/latest", nullptr, WINHTTP_NO_REFERER,
      WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE)};
  if (!request.value) return {};
  DWORD policy = WINHTTP_OPTION_REDIRECT_POLICY_NEVER;
  WinHttpSetOption(request.value, WINHTTP_OPTION_REDIRECT_POLICY, &policy, sizeof(policy));
  if (!WinHttpSendRequest(request.value, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                         WINHTTP_NO_REQUEST_DATA, 0, 0, 0) ||
      !WinHttpReceiveResponse(request.value, nullptr)) return {};
  DWORD status = 0, bytes = sizeof(status);
  if (!WinHttpQueryHeaders(request.value, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                           WINHTTP_HEADER_NAME_BY_INDEX, &status, &bytes, WINHTTP_NO_HEADER_INDEX) || status != 200)
    return {};
  std::string body;
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (!cancel.load() && std::chrono::steady_clock::now() < deadline) {
    char buffer[4096]; DWORD got = 0;
    if (!WinHttpReadData(request.value, buffer, sizeof(buffer), &got)) return {};
    if (!got) return body;
    if (body.size() + got > kMaxResponse) return {};
    body.append(buffer, got);
  }
  return {};
}
#else
// Use macOS's system HTTPS client with fixed arguments, without a shell or
// user-supplied URLs. Cancellation also reaps the child before module unload.
std::string Fetch(std::atomic<bool> &cancel) {
  int pipefd[2];
  if (pipe(pipefd)) return {};
  const int nullfd = open("/dev/null", O_WRONLY);
  if (nullfd < 0) { close(pipefd[0]); close(pipefd[1]); return {}; }
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, pipefd[1], STDOUT_FILENO);
  posix_spawn_file_actions_adddup2(&actions, nullfd, STDERR_FILENO);
  posix_spawn_file_actions_addclose(&actions, pipefd[0]);
  posix_spawn_file_actions_addclose(&actions, pipefd[1]);
  posix_spawn_file_actions_addclose(&actions, nullfd);
  const char *args[] = {"/usr/bin/curl", "--disable", "--fail", "--silent", "--proto", "=https",
      "--connect-timeout", "2", "--max-time", "4", "--max-filesize", "32768",
      "--user-agent", "Krose update check", "https://api.github.com/repos/shiftz300/krose/releases/latest", nullptr};
  pid_t pid = 0;
  const int error = posix_spawn(&pid, args[0], &actions, nullptr, const_cast<char **>(args), environ);
  posix_spawn_file_actions_destroy(&actions);
  close(pipefd[1]); close(nullfd);
  if (error) { close(pipefd[0]); return {}; }
  fcntl(pipefd[0], F_SETFL, O_NONBLOCK);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  std::string body;
  bool complete = false;
  while (!cancel.load() && std::chrono::steady_clock::now() < deadline) {
    pollfd descriptor{pipefd[0], POLLIN, 0};
    if (poll(&descriptor, 1, 50) < 0 && errno != EINTR) break;
    char buffer[4096]; const auto got = read(pipefd[0], buffer, sizeof(buffer));
    if (got == 0) { complete = true; break; }
    if (got < 0) { if (errno == EAGAIN || errno == EINTR) continue; break; }
    if (body.size() + size_t(got) > kMaxResponse) break;
    body.append(buffer, size_t(got));
  }
  close(pipefd[0]);
  if (!complete) kill(pid, SIGKILL);
  int status = 0;
  while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return {};
  return complete && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? body : "";
}
#endif
struct State {
  std::mutex mutex;
  std::thread worker;
  std::atomic<bool> cancel{false}, allowed{true}, done{false};
  bool attempted = false, notified = false;
  std::string latest;
  ~State() { cancel.store(true); if (worker.joinable()) worker.join(); }
};
State &Shared() { static State state; return state; }
}
bool AutomaticChecksAllowed() { return Shared().allowed.load(); }
void AllowAutomaticChecks(bool allowed) {
  auto &s = Shared();
  s.allowed.store(allowed);
  if (!allowed) s.cancel.store(true);
}
void StartAutomaticCheck() {
  if (std::getenv("KROSE_NO_UPDATE_CHECK")) return;
  auto &s = Shared();
  if (!s.allowed.load()) return;
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.attempted && s.done.load() && s.cancel.load()) {
    if (s.worker.joinable()) s.worker.join();
    s.attempted = false; s.done.store(false);
  }
  if (s.attempted) return;
  s.attempted = true; s.cancel.store(false);
  try {
    s.worker = std::thread([&s] {
      std::string latest;
      try { latest = LatestReleaseVersion(Fetch(s.cancel)); } catch (...) {}
      { std::lock_guard<std::mutex> lock(s.mutex); s.latest = std::move(latest); }
      s.done.store(true);
    });
  } catch (const std::exception &) { s.done.store(true); }
}
std::string TakeUpdateNotice(std::string_view current) {
  auto &s = Shared();
  if (!s.allowed.load() || !s.done.load()) return {};
  std::lock_guard<std::mutex> lock(s.mutex);
  if (s.notified || !Newer(s.latest, current)) return {};
  s.notified = true;
  return s.latest;
}
}
