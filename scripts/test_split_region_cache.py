"""Exercise the production one-region live cache and immutable full mailbox."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source
from test_split_stats_v9 import Payload

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/split_stats.cpp'

FIXTURE = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned int u32;typedef int s32;typedef unsigned short u16;typedef unsigned char u8;
extern "C" void*memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void*memset(void*d,int b,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)b;return d;}
static SusamuneCfg fixtureCfg;static SusamuneSplitStatsCfg mailbox;
#undef SUSAMUNE_CFG_PPC_PTR
#undef SUSAMUNE_SPLIT_STATS_PPC_PTR
#define SUSAMUNE_CFG_PPC_PTR (&fixtureCfg)
#define SUSAMUNE_SPLIT_STATS_PPC_PTR (&mailbox)
// This suite exercises the cache with its runtime already admitted. The memory
// suite separately runs the real launcher/map admission checks.
alignas(32) static u8 runtimeMemory[SUSAMUNE_SPLIT_STATS_RUNTIME_SIZE];
#undef SUSAMUNE_SPLIT_STATS_RUNTIME_PPC_BASE
#define SUSAMUNE_SPLIT_STATS_RUNTIME_PPC_BASE ((__UINTPTR_TYPE__)runtimeMemory)
static bool runtimeAvailable(){return true;}
static u32 published;
static void DCInvalidateRange(void*,u32){}
static void DCStoreRange(void*p,u32 n){if(p==&mailbox&&n==32)++published;}
static const u8 kRegion=HOST_REGION;
static const u32 kCheckpointFrames=1800,kRetryFrames=300,kSaveTimeoutFrames=450;
namespace SplitStats{struct Summary{enum{MAX_SEGMENTS=8};};void init();void update();}
struct Timer{u32 attemptSerial(){return 7;}}gQFTTimer;
static bool qfValid(u32 qf){return qf==0xffffffffu||qf<=0x7fffffffu;}
static void sampleAttemptTime(){}
'''

EXPORTS = r'''
extern "C" {
__declspec(dllexport) void reset(u32 available,u32 writable){
 memset(&fixtureCfg,0,sizeof(fixtureCfg));memset(&mailbox,0,sizeof(mailbox));
 fixtureCfg.magic=available?SUSAMUNE_CFG_MAGIC:0;fixtureCfg.version=SUSAMUNE_CFG_VERSION;fixtureCfg.flags=SUSAMUNE_CFG_FLAG_SPLIT_STATS_V9;
 mailbox.magic=SUSAMUNE_SPLIT_STATS_MAGIC;mailbox.version=SUSAMUNE_SPLIT_STATS_VERSION;
 mailbox.routeCount=SUSAMUNE_SPLIT_STATS_ROUTE_COUNT;mailbox.regionCount=3;mailbox.segmentCount=SUSAMUNE_SPLIT_STATS_SEGMENT_COUNT;
 mailbox.profileCount=SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;mailbox.payloadBytes=sizeof(mailbox.payload);
 mailbox.schemaHash=SUSAMUNE_SPLIT_STATS_SCHEMA_HASH;mailbox.flags=writable?SUSAMUNE_SPLIT_STATS_FLAG_WRITABLE:0;
 mailbox.saveSeq=mailbox.ackSeq=17;
 for(u32 r=0;r<3;++r){
  for(u32 i=0;i<SUSAMUNE_SPLIT_STATS_ROUTE_COUNT;++i){mailbox.payload.routeStats[r][i]={500+r*100+i,40+i,20+i};
   mailbox.payload.playedQf[r][i]=10000+r*1000+i;
   for(u32 p=0;p<SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;++p)mailbox.payload.pbIdentityQf[r][p][i]=20000+r*1000+p*200+i;}
  for(u32 i=0;i<SUSAMUNE_SPLIT_STATS_SEGMENT_COUNT;++i){mailbox.payload.bestQf[r][i]=30000+r*1000+i;
   for(u32 p=0;p<SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;++p)mailbox.payload.pbQf[r][p][i]=40000+r*1000+p*500+i;}}
 published=0;SplitStats::init();
}
__declspec(dllexport) void mailboxCopy(void*out){memcpy(out,&mailbox.payload,sizeof(mailbox.payload));}
__declspec(dllexport) void localCopy(void*out){memcpy(out,&sState->payload,sizeof(sState->payload));}
__declspec(dllexport) u32 localSize(){return sizeof(sState->payload);}
__declspec(dllexport) u32 runtimeSize(){return sizeof(Runtime);}
__declspec(dllexport) void change(u32 amount){
 for(u32 i=0;i<SUSAMUNE_SPLIT_STATS_ROUTE_COUNT;++i){sState->payload.routeStats[i].attempts+=amount;
 sState->payload.routeStats[i].finishes+=amount;sState->payload.routeStats[i].golds+=amount;sState->payload.playedQf[i]+=amount;
 for(u32 p=0;p<SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;++p)sState->payload.pbIdentityQf[p][i]+=amount;}
 for(u32 i=0;i<SUSAMUNE_SPLIT_STATS_SEGMENT_COUNT;++i){sState->payload.bestQf[i]+=amount;
 for(u32 p=0;p<SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;++p)sState->payload.pbQf[p][i]+=amount;}
 markDirty(true);
}
__declspec(dllexport) void tick(){SplitStats::update();}
__declspec(dllexport) void ack(u32 error){mailbox.ackSeq=mailbox.saveSeq;mailbox.status=error;}
__declspec(dllexport) u32 status(u32 key){switch(key){case 0:return published;case 1:return sState->flags;
case 2:return mailbox.saveSeq;case 3:return sState->lastError;case 4:return sState->waitFrames;}return 0;}
}
'''


class SplitRegionCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-region-cache-')
        cls.addClassCleanup(cls.temp.cleanup)
        production = SOURCE.read_text()
        source = FIXTURE
        source += production[production.index('enum RuntimeFlag {'):production.index('enum OverlayColor {')]
        source += production[production.index('struct RegionPayload {'):production.index('static_assert(SplitStats::ROUTE_COUNT')]
        for signature in ('bool payloadValid(', 'void resetPayload()', 'void clearOverlay()', 'void clearAttemptSamples(',
                'void markDirty(', 'bool validMailbox(', 'void readRegionPayload(',
                'void publishRegionPayload(', 'void beginSave()', 'void pollSave()'):
            source += function_source(SOURCE,signature)
        source += '\nnamespace SplitStats {\n' + function_source(SOURCE,'void init()') + function_source(SOURCE,'void update()') + '\n}\n' + EXPORTS
        path = Path(cls.temp.name) / 'test.cpp'
        path.write_text(source)
        cls.libs = []
        for region in range(3):
            library = path.with_name(f'region{region}.dll')
            proc = subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-shared','-O2',
                '-fno-builtin','-nostdlib','-fuse-ld=lld','-Wl,/noentry',f'-DHOST_REGION={region}','-DIS_EMULATOR=0',
                '-I',str(ROOT/'include'),str(path),'-o',str(library)],capture_output=True,text=True)
            if proc.returncode:raise RuntimeError(proc.stdout+proc.stderr)
            lib = C.CDLL(str(library))
            cls.addClassCleanup(lambda dll=lib:C.windll.kernel32.FreeLibrary(C.c_void_p(dll._handle)))
            lib.mailboxCopy.argtypes = lib.localCopy.argtypes = [C.c_void_p]
            lib.status.restype = C.c_uint
            cls.libs.append(lib)

    @staticmethod
    def mailbox(lib):
        payload = Payload()
        lib.mailboxCopy(C.byref(payload))
        return payload

    @staticmethod
    def region(payload,region):
        return b''.join(bytes(getattr(payload,name)[region]) for name in ('stats','played','best','identity','pb'))

    @staticmethod
    def local(lib):
        data = C.create_string_buffer(lib.localSize())
        lib.localCopy(data)
        return data.raw

    def test_cache_is_exact_current_region_and_saves_28248_bytes(self):
        for region,lib in enumerate(self.libs):
            lib.reset(1,1)
            self.assertEqual(lib.localSize(),C.sizeof(Payload)//3)
            self.assertEqual(lib.runtimeSize(),0x3790)
            self.assertEqual(0xA5E8-lib.runtimeSize(),28248)
            self.assertEqual(self.local(lib),self.region(self.mailbox(lib),region))
            self.assertEqual(lib.status(0),0)

    def test_publish_only_updates_current_region_and_retains_other_regions(self):
        for region,lib in enumerate(self.libs):
            lib.reset(1,1)
            original = self.mailbox(lib)
            lib.change(7);lib.tick()
            published = self.mailbox(lib)
            self.assertEqual(self.region(published,region),self.local(lib))
            self.assertEqual(lib.status(0),1)
            for other in range(3):
                if other!=region:self.assertEqual(self.region(published,other),self.region(original,other))

    def test_pending_and_timed_out_writes_keep_entire_request_immutable(self):
        for region,lib in enumerate(self.libs):
            lib.reset(1,1)
            lib.change(1);lib.tick()
            original = bytes(self.mailbox(lib))
            lib.change(4)
            for _ in range(500):lib.tick()
            self.assertEqual(bytes(self.mailbox(lib)),original)
            self.assertEqual(lib.status(0),1)
            self.assertEqual(lib.status(3),0xffffffff)
            lib.ack(0);lib.tick()
            self.assertEqual(lib.status(0),2)
            self.assertEqual(self.region(self.mailbox(lib),region),self.local(lib))

    def test_failed_write_retries_without_losing_other_regions(self):
        for region,lib in enumerate(self.libs):
            lib.reset(1,1)
            original = self.mailbox(lib)
            lib.change(2);lib.tick();lib.ack(5);lib.tick()
            self.assertEqual(lib.status(3),5)
            for _ in range(300):lib.tick()
            self.assertEqual(lib.status(0),2)
            published = self.mailbox(lib)
            self.assertEqual(self.region(published,region),self.local(lib))
            for other in range(3):
                if other!=region:self.assertEqual(self.region(published,other),self.region(original,other))

    def test_missing_or_read_only_backend_does_not_publish(self):
        for lib in self.libs:
            for available,writable in ((0,0),(1,0)):
                lib.reset(available,writable)
                original = bytes(self.mailbox(lib))
                lib.change(1);lib.tick()
                self.assertEqual(bytes(self.mailbox(lib)),original)
                self.assertEqual(lib.status(0),0)
                if not available:
                    local=self.local(lib)
                    # Route counts/time start at zero, all QF records at unset.
                    unset_start=132*(12+4)
                    self.assertEqual(local[:unset_start],b'\1\0\0\0'*(unset_start//4))


if __name__ == '__main__':unittest.main()
