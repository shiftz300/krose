#include "pluginterfaces/base/funknown.h"
#include "base/source/fstring.h"
#include "pluginterfaces/base/fvariant.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>

int main() {
  using namespace Steinberg;
  for (auto first : {0u, 0x80000000u, 0xF2AEE70Du, 0xFFFFFFFFu}) {
    FUID original(first, 0x00DE4F4E, 0x4C6F6349, 0x53654731);
    char text[33]{}, registry[40]{};
    original.toString(text);
    assert(std::strlen(text) == 32);
    FUID decoded;
    assert(decoded.fromString(text) && decoded == original);
    original.toRegistryString(registry);
    assert(std::strlen(registry) == 38);
    assert(decoded.fromRegistryString(registry) && decoded == original);
  }
  String number;
  const auto boundary = std::ldexp(1., 63);
  number.printFloat(boundary, 0);
  assert(std::strcmp(number.text8(), "9223372036854775808") == 0);
  number.printFloat(-boundary, 0);
  assert(std::strcmp(number.text8(), "-9223372036854775808") == 0);
  number.printFloat(std::nextafter(boundary, 0.), 0);
  assert(std::strcmp(number.text8(), "9223372036854774784") == 0);
  FVariant value;
  assert(value.type == FVariant::kEmpty && value.intValue == 0);
  value.setString8("copied value");
  FVariant copy(value);
  assert(std::strcmp(copy.getString8(), "copied value") == 0);
  copy.empty();
  assert(copy.type == FVariant::kEmpty && copy.intValue == 0);
  std::cout << "SDK UID round trips and signed numeric limits passed\n";
}
