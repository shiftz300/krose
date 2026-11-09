#pragma once
// Exercise the SDK's Windows GUID formatting branch on the macOS test host.
// All translation units in this isolated executable use the same byte order.
#include "pluginterfaces/base/fplatform.h"
#undef COM_COMPATIBLE
#define COM_COMPATIBLE 1
