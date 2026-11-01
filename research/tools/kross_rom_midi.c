/* macOS research capture client. Fixed stage-B commands only, no installer.
 * Raw captures are validated separately by parse_rom_midi.py before use.
 */
#include <CoreMIDI/CoreMIDI.h>
#include <CoreFoundation/CoreFoundation.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <fcntl.h>
#include <unistd.h>

#define CAPACITY (1024u*1024u)
typedef struct {
  uint8_t current[512],wire[CAPACITY];
  size_t used,length;
  int channel,mode;
  atomic_int done,frames,overflow,active;
} Capture;
static void feed(Capture *c,uint8_t byte) {
  if(atomic_load(&c->done) || atomic_load(&c->overflow) || byte>=0xf8) return;
  if(byte==0xf0) c->used=0;
  else if(!c->used) return;
  else if((byte&0x80) && byte!=0xf7) { atomic_store(&c->overflow,1);return; }
  if(c->used==sizeof(c->current)) { atomic_store(&c->overflow,1);return; }
  c->current[c->used++]=byte;
  if(byte!=0xf7) return;
  if(c->length+c->used>CAPACITY) { atomic_store(&c->overflow,1);return; }
  memcpy(c->wire+c->length,c->current,c->used);c->length+=c->used;
  atomic_fetch_add(&c->frames,1);
  const uint8_t prefix[]={0xf0,0x42,(uint8_t)(0x30+c->channel-1),0,1,0x49,0x7d,0x4b,0x52,0x4f,0x53,0x45,3};
  if(c->used>=16 && !memcmp(c->current,prefix,sizeof(prefix))) {
    uint8_t kind=c->current[13];
    if(kind==0x13 || (c->mode==1 && kind==0x14) || (c->mode==2 && kind==0x12) || (c->mode==3 && kind==0x15))
      atomic_store(&c->done,1);
  }
  c->used=0;
}
static void receive(const MIDIPacketList *list,void *context,void *connection) {
  (void)connection;Capture *c=context;const MIDIPacket *p=&list->packet[0];
  if(atomic_fetch_add(&c->active,1)) { atomic_store(&c->overflow,1);atomic_fetch_sub(&c->active,1);return; }
  for(UInt32 n=0;n<list->numPackets;n++) {
    for(UInt16 i=0;i<p->length;i++) feed(c,p->data[i]);
    p=MIDIPacketNext(p);
  }
  atomic_fetch_sub(&c->active,1);
}
static int ok(OSStatus status,const char *op) {
  if(!status)return 1;fprintf(stderr,"%s failed: %d\n",op,(int)status);return 0;
}
static int number(const char *s,int32_t lo,int32_t hi,int32_t *out) {
  char *end;errno=0;long n=strtol(s,&end,10);
  if(errno || end==s || *end || n<lo || n>hi)return 0;*out=(int32_t)n;return 1;
}
static MIDIEndpointRef endpoint(int32_t uid,MIDIObjectType expected) {
  MIDIObjectRef object=0;MIDIObjectType type=0;
  if(!ok(MIDIObjectFindByUniqueID(uid,&object,&type),"MIDIObjectFindByUniqueID") || type!=expected)return 0;
  return object;
}
static int selftest(void) {
  Capture *c=calloc(1,sizeof(*c));if(!c)return 1;c->channel=1;c->mode=1;
  atomic_init(&c->done,0);atomic_init(&c->frames,0);atomic_init(&c->overflow,0);
  const uint8_t sample[]={0xf0,0x42,0x30,0,1,0x49,0x7d,0x4b,0x52,0x4f,0x53,0x45,3,0x14,0,1,0xf7};
  for(size_t i=0;i<sizeof(sample);i++){feed(c,sample[i]);feed(c,0xf8);}
  int pass=atomic_load(&c->done)==1 && atomic_load(&c->frames)==1 && c->length==sizeof(sample) && !memcmp(c->wire,sample,sizeof(sample));
  c->used=0;c->length=0;atomic_store(&c->done,0);atomic_store(&c->frames,0);atomic_init(&c->active,0);
  MIDIPacketList packets;MIDIPacket *p=MIDIPacketListInit(&packets);
  p=MIDIPacketListAdd(&packets,sizeof(packets),p,0,6,sample);
  if(p)p=MIDIPacketListAdd(&packets,sizeof(packets),p,0,sizeof(sample)-6,sample+6);
  if(!p){free(c);return 1;}
  receive(&packets,c,NULL);
  pass=pass && atomic_load(&c->done)==1 && atomic_load(&c->frames)==1 && !atomic_load(&c->active) && c->length==sizeof(sample);
  atomic_store(&c->done,0);c->used=0;feed(c,0xf0);
  for(int i=0;i<513;i++)feed(c,0);
  pass=pass && atomic_load(&c->overflow);free(c);
  puts(pass?"PASS: fragmented callback, realtime filtering and size guard; no devices accessed":"FAIL");return pass?0:1;
}
static int usage(void) {
  fprintf(stderr,"Usage: kross-rom-midi self-test\n"
          "  kross-rom-midi --source UID --destination UID --channel 1 --mode 1|2|3 --block 255 --capture NEWFILE --experimental-stage-b\n");return 2;
}
int main(int argc,char **argv) {
  if(argc==2 && !strcmp(argv[1],"self-test"))return selftest();
  int32_t source_uid=0,destination_uid=0,channel=1,mode=0,block=0;int acknowledged=0;
  const char *file=NULL;
  for(int i=1;i<argc;i++) {
    if(!strcmp(argv[i],"--experimental-stage-b")){acknowledged=1;continue;}
    if(i+1>=argc)return usage();const char *flag=argv[i++];
    if(!strcmp(flag,"--capture"))file=argv[i];
    else if(!strcmp(flag,"--source")){if(!number(argv[i],INT32_MIN,INT32_MAX,&source_uid))return usage();}
    else if(!strcmp(flag,"--destination")){if(!number(argv[i],INT32_MIN,INT32_MAX,&destination_uid))return usage();}
    else if(!strcmp(flag,"--channel")){if(!number(argv[i],1,16,&channel))return usage();}
    else if(!strcmp(flag,"--mode")){if(!number(argv[i],1,3,&mode))return usage();}
    else if(!strcmp(flag,"--block")){if(!number(argv[i],0,255,&block))return usage();}
    else return usage();
  }
  if(!acknowledged || !source_uid || !destination_uid || !mode || !file || (mode!=2 && block))return usage();
  /* No truncation, symlink following, existing file or device-node writes. */
  int fd=open(file,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
  if(fd<0){perror("capture open");return 1;}
  Capture *c=calloc(1,sizeof(*c));if(!c){close(fd);return 1;}
  c->channel=channel;c->mode=mode;atomic_init(&c->done,0);atomic_init(&c->frames,0);atomic_init(&c->overflow,0);atomic_init(&c->active,0);
  MIDIClientRef client=0;MIDIPortRef input=0,output=0;MIDIEndpointRef source=0,destination=0;int result=1;
  if(!ok(MIDIClientCreate(CFSTR("Krose ROM stage B"),NULL,NULL,&client),"MIDIClientCreate"))goto cleanup;
  source=endpoint(source_uid,kMIDIObjectType_Source);destination=endpoint(destination_uid,kMIDIObjectType_Destination);
  if(!source || !destination)goto cleanup;
  if(!ok(MIDIInputPortCreate(client,CFSTR("Bounded ROM capture"),receive,c,&input),"MIDIInputPortCreate"))goto cleanup;
  if(!ok(MIDIPortConnectSource(input,source,NULL),"MIDIPortConnectSource"))goto cleanup;
  if(!ok(MIDIOutputPortCreate(client,CFSTR("Bounded ROM request"),&output),"MIDIOutputPortCreate"))goto cleanup;
  uint8_t request[]={0xf0,0x42,(uint8_t)(0x30+channel-1),0,1,0x49,0x72,0x18,(uint8_t)mode,(uint8_t)(block>>7),(uint8_t)(block&127),0xf7};
  MIDIPacketList packets;MIDIPacket *packet=MIDIPacketListInit(&packets);
  if(!MIDIPacketListAdd(&packets,sizeof(packets),packet,0,sizeof(request),request))goto cleanup;
  if(!ok(MIDISend(output,destination,&packets),"MIDISend"))goto cleanup;
  printf("TX stage B mode=%d block=%d channel=%d; waiting at most 60 seconds\n",(int)mode,(int)block,(int)channel);fflush(stdout);
  CFAbsoluteTime start=CFAbsoluteTimeGetCurrent(),last=start;
  while(!atomic_load(&c->done) && !atomic_load(&c->overflow) && CFAbsoluteTimeGetCurrent()-start<60) {
    (void)CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.05,false);
    if(CFAbsoluteTimeGetCurrent()-last>=5){printf("RX frames=%d\n",atomic_load(&c->frames));fflush(stdout);last=CFAbsoluteTimeGetCurrent();}
  }
  result=atomic_load(&c->done) && !atomic_load(&c->overflow)?0:1;
cleanup:
  if(input){MIDIPortDisconnectSource(input,source);MIDIPortDispose(input);}
  if(output)MIDIPortDispose(output);if(client)MIDIClientDispose(client);
  /* No new callbacks after disposal; allow an in-flight callback to finish. */
  for(int n=0;n<1000 && atomic_load(&c->active);n++)usleep(1000);
  if(atomic_load(&c->active)){fprintf(stderr,"Callback did not finish; capture withheld\n");close(fd);return 1;}
  if(!atomic_load(&c->done) && c->used && c->length+c->used<=CAPACITY){memcpy(c->wire+c->length,c->current,c->used);c->length+=c->used;}
  size_t offset=0;
  while(offset<c->length){ssize_t n=write(fd,c->wire+offset,c->length-offset);if(n<=0){perror("capture write");result=1;break;}offset+=(size_t)n;}
  if(fsync(fd)){perror("capture fsync");result=1;}close(fd);
  printf("Capture bytes=%zu frames=%d complete=%d overflow=%d; CRC validation is separate\n",c->length,atomic_load(&c->frames),atomic_load(&c->done),atomic_load(&c->overflow));
  free(c);return result;
}
