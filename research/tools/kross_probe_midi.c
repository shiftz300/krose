/* macOS stage-A identity probe. No firmware installation or ROM read command.
 * Build: clang -std=c11 -O2 -Wall -Wextra -Werror -Wno-deprecated-declarations
 *   tools/kross_probe_midi.c -framework CoreMIDI -framework CoreFoundation
 *   -o build/kross-probe-midi
 */
#include <CoreMIDI/CoreMIDI.h>
#include <CoreFoundation/CoreFoundation.h>
#include <errno.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  uint8_t message[128], expected[14];
  size_t used;
  atomic_int received;
  struct { uint8_t bytes[128]; size_t length; } replies[8];
  atomic_int reply_count;
  int expect_inquiry;
} Probe;

static void feed(Probe *p, uint8_t byte) {
  if (byte >= 0xf8) return; /* Interleaved MIDI real-time bytes. */
  if (byte == 0xf0) p->used = 0;
  else if (!p->used) return;
  else if ((byte & 0x80) && byte != 0xf7) { p->used = 0; return; }
  if (p->used == sizeof(p->message)) { p->used = 0; return; }
  p->message[p->used++] = byte;
  if (byte == 0xf7) {
    int count = atomic_load(&p->reply_count);
    if (count < 8) {
      memcpy(p->replies[count].bytes, p->message, p->used);
      p->replies[count].length = p->used;
      atomic_store(&p->reply_count, count+1);
    }
    if (p->expect_inquiry == 0 && p->used == sizeof(p->expected) && !memcmp(p->message, p->expected, p->used))
      atomic_store(&p->received, 1);
    if (p->expect_inquiry == 1 && p->used == 15 && p->message[0] == 0xf0 &&
        p->message[1] == 0x7e && p->message[2] < 16 && p->message[3] == 6 &&
        p->message[4] == 2 && p->message[5] == 0x42)
      atomic_store(&p->received, 1);
    if (p->expect_inquiry == 2 && p->used == 13 && p->message[0] == 0xf0 &&
        p->message[1] == 0x42 && p->message[2] == p->expected[2] &&
        p->message[3] == 0 && p->message[4] == 1 && p->message[5] == 0x49 &&
        p->message[6] == 0x42)
      atomic_store(&p->received, 1);
    if (p->expect_inquiry == 3 && p->used == 45 && p->message[0] == 0xf0 &&
        p->message[1] == 0x42 && p->message[2] == p->expected[2] &&
        p->message[3] == 0 && p->message[4] == 1 && p->message[5] == 0x49 &&
        p->message[6] == 0x73 && p->message[7] == 0x15)
      atomic_store(&p->received, 1);
    p->used = 0;
  }
}

static void read_midi(const MIDIPacketList *list, void *context, void *connection) {
  (void)connection;
  Probe *probe = context;
  const MIDIPacket *packet = &list->packet[0];
  for (UInt32 n = 0; n < list->numPackets; ++n) {
    for (UInt16 j = 0; j < packet->length; ++j) feed(probe, packet->data[j]);
    packet = MIDIPacketNext(packet);
  }
}

static int check(OSStatus status, const char *operation) {
  if (!status) return 1;
  fprintf(stderr, "%s failed: %d\n", operation, (int)status);
  return 0;
}

static void endpoint_name(MIDIEndpointRef endpoint, char *target, size_t capacity) {
  CFStringRef name = NULL;
  target[0] = '\0';
  if (MIDIObjectGetStringProperty(endpoint, kMIDIPropertyDisplayName, &name))
    (void)MIDIObjectGetStringProperty(endpoint, kMIDIPropertyName, &name);
  if (name) {
    (void)CFStringGetCString(name, target, (CFIndex)capacity, kCFStringEncodingUTF8);
    CFRelease(name);
  }
}

static void list_endpoints(void) {
  for (int direction = 0; direction < 2; ++direction) {
    ItemCount count = direction ? MIDIGetNumberOfDestinations() : MIDIGetNumberOfSources();
    for (ItemCount i = 0; i < count; ++i) {
      MIDIEndpointRef endpoint = direction ? MIDIGetDestination(i) : MIDIGetSource(i);
      SInt32 uid = 0;
      char name[512];
      if (MIDIObjectGetIntegerProperty(endpoint, kMIDIPropertyUniqueID, &uid)) continue;
      endpoint_name(endpoint, name, sizeof(name));
      printf("%s UID=%d  %s\n", direction ? "destination" : "source", (int)uid, name);
    }
  }
}

static int number(const char *input, int32_t minimum, int32_t maximum, int32_t *result) {
  char *end;
  errno = 0;
  long value = strtol(input, &end, 10);
  if (errno || end == input || *end || value < minimum || value > maximum) return 0;
  *result = (int32_t)value;
  return 1;
}

static MIDIEndpointRef find_endpoint(int32_t uid, MIDIObjectType expected) {
  MIDIObjectRef object = 0;
  MIDIObjectType type = 0;
  if (!check(MIDIObjectFindByUniqueID(uid, &object, &type), "MIDIObjectFindByUniqueID")) return 0;
  if (type != expected) { fprintf(stderr, "UID has wrong endpoint direction\n"); return 0; }
  return object;
}

static void initialize(Probe *probe, int channel) {
  memset(probe, 0, sizeof(*probe));
  atomic_init(&probe->received, 0);
  atomic_init(&probe->reply_count, 0);
  const uint8_t expected[] = {0xf0,0x42,0x30,0,1,0x49,0x7d,0x4b,0x52,0x4f,0x53,0x45,1,0xf7};
  memcpy(probe->expected, expected, sizeof(expected));
  probe->expected[2] = (uint8_t)(0x30+channel-1);
}

static int self_test(void) {
  for (int channel = 1; channel <= 16; ++channel) {
    Probe probe;
    initialize(&probe, channel);
    for (size_t i = 0; i < sizeof(probe.expected)-1; ++i) {
      feed(&probe, probe.expected[i]);
      feed(&probe, 0xf8);
    }
    if (atomic_load(&probe.received)) return 1;
    feed(&probe, 0xf7);
    if (!atomic_load(&probe.received)) return 1;
    initialize(&probe, channel);
    probe.expected[12] = 2;
    for (size_t i = 0; i < sizeof(probe.expected); ++i) feed(&probe, probe.expected[i]);
    if (!atomic_load(&probe.received)) return 1;
    initialize(&probe, channel);
    probe.expected[12] = 2;
    for (size_t i = 0; i < sizeof(probe.expected); ++i)
      feed(&probe, i == 12 ? 1 : probe.expected[i]);
    if (atomic_load(&probe.received)) return 1;
    initialize(&probe, channel);
    for (size_t i = 0; i < sizeof(probe.expected); ++i) feed(&probe, probe.expected[i]);
    if (atomic_load(&probe.reply_count) != 1 || probe.replies[0].length != 14 ||
        memcmp(probe.replies[0].bytes, probe.expected, 14)) return 1;
    initialize(&probe, channel);
    for (size_t i = 0; i < sizeof(probe.expected); ++i)
      feed(&probe, i == 2 ? (uint8_t)(0x30+(channel%16)) : probe.expected[i]);
    if (atomic_load(&probe.received)) return 1;
    if (atomic_load(&probe.reply_count) != 1) return 1;
    for (int i = 0; i < 256; ++i) feed(&probe, 0x7f);
    feed(&probe, 0xf0);
    for (int i = 0; i < 256; ++i) feed(&probe, 0x7f);
    feed(&probe, 0xf7);
    if (atomic_load(&probe.received)) return 1;
    if (atomic_load(&probe.reply_count) != 1) return 1;
    for (size_t i = 0; i < sizeof(probe.expected); ++i) feed(&probe, probe.expected[i]);
    if (!atomic_load(&probe.received)) return 1;
    if (atomic_load(&probe.reply_count) != 2) return 1;
    for (int n = 0; n < 12; ++n)
      for (size_t i = 0; i < sizeof(probe.expected); ++i) feed(&probe, probe.expected[i]);
    if (atomic_load(&probe.reply_count) != 8) return 1;
    initialize(&probe, channel);
    probe.expect_inquiry = 1;
    const uint8_t identity[] = {0xf0,0x7e,(uint8_t)(channel-1),6,2,0x42,0x49,1,5,0,1,2,4,0,0xf7};
    for (size_t i = 0; i < sizeof(identity); ++i) feed(&probe, identity[i]);
    if (!atomic_load(&probe.received) || atomic_load(&probe.reply_count) != 1) return 1;
    initialize(&probe, channel);
    for (size_t i = 0; i < sizeof(identity); ++i) feed(&probe, identity[i]);
    if (atomic_load(&probe.received)) return 1; /* Inquiry is not stage-A success. */
    initialize(&probe, channel);
    probe.expect_inquiry = 2;
    const uint8_t mode[] = {0xf0,0x42,(uint8_t)(0x30+channel-1),0,1,0x49,0x42,0,0,0,0,0,0xf7};
    for (size_t i = 0; i < sizeof(mode); ++i) feed(&probe, mode[i]);
    if (!atomic_load(&probe.received)) return 1;
    initialize(&probe, channel);
    probe.expect_inquiry = 1;
    for (size_t i = 0; i < sizeof(probe.expected); ++i) feed(&probe, probe.expected[i]);
    if (atomic_load(&probe.received)) return 1;
    initialize(&probe, channel);
    probe.expect_inquiry = 3;
    uint8_t name[45] = {0xf0,0x42,(uint8_t)(0x30+channel-1),0,1,0x49,0x73,0x15};
    name[44] = 0xf7;
    for (size_t i = 0; i < sizeof(name); ++i) feed(&probe, name[i]);
    if (!atomic_load(&probe.received)) return 1;
  }
  puts("PASS: reply parser, 16 channels, real-time interleaving, wrong channel and oversized input; no MIDI APIs called");
  return 0;
}

static int usage(void) {
  fprintf(stderr, "Usage:\n  kross-probe-midi list\n  kross-probe-midi self-test\n"
          "  kross-probe-midi inquiry --source UID --destination UID\n"
          "  kross-probe-midi mode-query --source UID --destination UID --channel 1\n"
          "  kross-probe-midi name-query --source UID --destination UID --channel 1\n"
          "  kross-probe-midi probe --source UID --destination UID --channel 1 --revision 1|2|3 --experimental-stage-a\n"
          "inquiry is the standard read-only Universal Device Inquiry.\n"
          "Only use probe after installing the documented stage-A candidate. Select KROSS endpoints.\n");
  return 2;
}

int main(int argc, char **argv) {
  if (argc == 2 && !strcmp(argv[1], "self-test")) return self_test();
  int list_only = argc == 2 && !strcmp(argv[1], "list");
  int inquiry = argc > 1 && !strcmp(argv[1], "inquiry");
  int mode_query = argc > 1 && !strcmp(argv[1], "mode-query");
  int name_query = argc > 1 && !strcmp(argv[1], "name-query");
  int32_t source_uid = 0, destination_uid = 0, channel = 1, revision = 1;
  int source_given = 0, destination_given = 0, acknowledged = 0;
  if (!list_only) {
    if (argc < 2 || (!inquiry && !mode_query && !name_query && strcmp(argv[1], "probe"))) return usage();
    for (int i = 2; i < argc; ++i) {
      if (!strcmp(argv[i], "--experimental-stage-a") || !strcmp(argv[i], "--experimental-stage-b")) { acknowledged = 1; continue; }
      if (i+1 >= argc) return usage();
      const char *flag = argv[i++];
      if (!strcmp(flag, "--source")) {
        if (source_given++ || !number(argv[i], INT32_MIN, INT32_MAX, &source_uid)) return usage();
      } else if (!strcmp(flag, "--destination")) {
        if (destination_given++ || !number(argv[i], INT32_MIN, INT32_MAX, &destination_uid)) return usage();
      } else if (!strcmp(flag, "--channel")) {
        if (!number(argv[i], 1, 16, &channel)) return usage();
      } else if (!strcmp(flag, "--revision")) {
        if (!number(argv[i], 1, 3, &revision)) return usage();
      } else return usage();
    }
    if ((!inquiry && !mode_query && !name_query && !acknowledged) || !source_given || !destination_given || !source_uid || !destination_uid) return usage();
  }
  MIDIClientRef client = 0;
  if (!check(MIDIClientCreate(CFSTR("Krose experimental identity probe"), NULL, NULL, &client), "MIDIClientCreate")) return 1;
  if (list_only) { list_endpoints(); MIDIClientDispose(client); return 0; }
  MIDIEndpointRef source = find_endpoint(source_uid, kMIDIObjectType_Source);
  MIDIEndpointRef destination = find_endpoint(destination_uid, kMIDIObjectType_Destination);
  if (!source || !destination) { MIDIClientDispose(client); return 1; }
  char source_name[512], destination_name[512];
  endpoint_name(source, source_name, sizeof(source_name));
  endpoint_name(destination, destination_name, sizeof(destination_name));
  printf("Probe: %s [%d] -> instrument -> %s [%d], channel %d\n",
         destination_name, (int)destination_uid, source_name, (int)source_uid, (int)channel);
  Probe probe;
  initialize(&probe, channel);
  probe.expected[12] = (uint8_t)revision;
  probe.expect_inquiry = inquiry ? 1 : mode_query ? 2 : name_query ? 3 : 0;
  MIDIPortRef input = 0, output = 0;
  int result = 1;
  if (!check(MIDIInputPortCreate(client, CFSTR("Identity reply"), read_midi, &probe, &input), "MIDIInputPortCreate")) goto cleanup;
  if (!check(MIDIPortConnectSource(input, source, NULL), "MIDIPortConnectSource")) goto cleanup;
  if (!check(MIDIOutputPortCreate(client, CFSTR("Identity request"), &output), "MIDIOutputPortCreate")) goto cleanup;
  uint8_t request[] = {0xf0,0x42,0x30,0,1,0x49,0x72,0x18,0,0,0,0xf7};
  const uint8_t inquiry_request[] = {0xf0,0x7e,0x7f,6,1,0xf7};
  uint8_t mode_request[] = {0xf0,0x42,(uint8_t)(0x30+channel-1),0,1,0x49,0x12,0xf7};
  request[2] = (uint8_t)(0x30+channel-1);
  if (name_query) request[7] = 0x15; /* Fixed bank 0, index 0; name only. */
  MIDIPacketList packets;
  MIDIPacket *packet = MIDIPacketListInit(&packets);
  if (!MIDIPacketListAdd(&packets, sizeof(packets), packet, 0,
                        inquiry ? sizeof(inquiry_request) : mode_query ? sizeof(mode_request) : sizeof(request),
                        inquiry ? inquiry_request : mode_query ? mode_request : request)) goto cleanup;
  if (!check(MIDISend(output, destination, &packets), "MIDISend")) goto cleanup;
  CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent()+5;
  while (!atomic_load(&probe.received) && CFAbsoluteTimeGetCurrent() < deadline)
    (void)CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, false);
  int replies = atomic_load(&probe.reply_count);
  printf("RX complete SysEx replies: %d (capture limited to 8 messages, 128 bytes each)\n", replies);
  for (int n = 0; n < replies; ++n) {
    printf("RX:");
    for (size_t i = 0; i < probe.replies[n].length; ++i) printf(" %02X", probe.replies[n].bytes[i]);
    putchar('\n');
  }
  if (atomic_load(&probe.received)) {
    puts(inquiry ? "PASS: standard KORG device inquiry reply received. This does not verify the injected handler."
                 : mode_query ? "PASS: original KORG mode-query reply received. This does not verify the injected handler."
                 : name_query ? "PASS: original KORG name-query reply received. This does not verify the injected handler."
                 : revision == 3 ? "PASS: KROSE stage-B revision 03 identity reply received."
                 : "PASS: KROSE stage-A identity reply received. ROM export is NOT installed.");
    result = 0;
  } else fprintf(stderr, "%s\n", inquiry ? "TIMEOUT: no standard KORG device inquiry reply."
                 : mode_query ? "TIMEOUT: no original KORG mode-query reply."
                 : name_query ? "TIMEOUT: no original KORG name-query reply."
                 : "TIMEOUT: no stage-A reply. Check endpoints/channel/Enable Exclusive; this does not diagnose boot or ROM.");
cleanup:
  if (input) { MIDIPortDisconnectSource(input, source); MIDIPortDispose(input); }
  if (output) MIDIPortDispose(output);
  MIDIClientDispose(client);
  return result;
}
