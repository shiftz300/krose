#include "storage/UpdateCheck.h"
#include <cassert>
#include <iostream>
using namespace krose::updates;
int main() {
  assert(Newer("v0.4.4","0.4.3"));
  assert(Newer("v0.10.0","0.9.99"));
  assert(!Newer("v0.4.3","0.4.3") && !Newer("v0.4.2","0.4.3"));
  for (const char *bad : {"", "1.2", "1.2.3.4", "01.2.3", "v1.2.3-rc1", "v1.2.3+4", "1.-2.3",
                          "999999999.1.2", "https://example.org", "1.2.3/../../x"}) {
    assert(!Version(bad));
    assert(!Newer(bad,"0.4.3"));
  }
  const auto stable = R"({"tag_name":"v0.4.4","draft":false,"prerelease":false})";
  assert(LatestReleaseVersion(stable)=="v0.4.4");
  for (const auto &bad : {std::string("[]"),std::string("not json"),std::string("{}"),
       std::string(R"({"tag_name":"v0.4.4","draft":true,"prerelease":false})"),
       std::string(R"({"tag_name":"v0.4.4","draft":false,"prerelease":true})"),
       std::string(R"({"tag_name":"file:///tmp/evil","draft":false,"prerelease":false})"),
       std::string(R"({"tag_name":42,"draft":false,"prerelease":false})"),
       std::string(kMaxResponse+1,' ')}) assert(LatestReleaseVersion(bad).empty());
  AllowAutomaticChecks(false);
  StartAutomaticCheck();
  assert(!AutomaticChecksAllowed() && TakeUpdateNotice("0.0.0").empty());
  std::cout << "PASS numeric version comparison, stable release validation, response bounds and disabled check\n";
}
