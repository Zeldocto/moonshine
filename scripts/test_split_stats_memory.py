"""Run all production split APIs against guarded metadata and old handoffs."""

import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TAIL_SIZE = 0xD100
OFFSET = 0x8720
USED = 0x3790


class SplitStatsMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-split-memory-")
        cls.addClassCleanup(cls.temp.cleanup)
        production = (ROOT / "src/split_stats.cpp").read_text()
        production = re.sub(r'^#include[^\n]+\n', '', production, flags=re.M)
        fixture = r'''
#include "susamune/split_stats.hxx"
#include "susamune/susamune_cfg.h"
#include "susamune/ghost_storage.h"
extern "C" void *memset(void*d,int v,__SIZE_TYPE__ n){u8*p=(u8*)d;while(n--)*p++=(u8)v;return d;}
extern "C" void *memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*p=(u8*)d;const u8*q=(const u8*)s;while(n--)*p++=*q++;return d;}
extern "C" int snprintf(char*d,__SIZE_TYPE__ n,const char*,...){if(n)*d=0;return 0;}
extern "C" char *strncpy(char*d,const char*s,__SIZE_TYPE__ n){char*p=d;while(n--){*p++=*s;if(*s)++s;}return d;}
static_assert(SUSAMUNE_CONSOLE_SPLIT_STATS_RUNTIME_PPC_BASE==0x91C1A620u,"console address");
static_assert(SUSAMUNE_DOLPHIN_SPLIT_STATS_RUNTIME_PPC_BASE==0x712DB620u,"emulator address");
static_assert(SUSAMUNE_SPLIT_STATS_RUNTIME_OFFSET>=SUSAMUNE_STATE_LIVE_PROFILE_OFFSET+SUSAMUNE_STATE_LIVE_PROFILE_SIZE,"profile separate");
static_assert(SUSAMUNE_SPLIT_STATS_RUNTIME_OFFSET+SUSAMUNE_SPLIT_STATS_RUNTIME_SIZE<=SUSAMUNE_STATE_METADATA_RUNTIME_SIZE,"bank contained");
static_assert(SUSAMUNE_STATE_METADATA_OFFSET==SUSAMUNE_GHOST_INPUT_MAX_COUNT*sizeof(SusamuneGhostInputSample),"recording preserved");
alignas(32) static u8 memory[SUSAMUNE_STATE_METADATA_RUNTIME_SIZE+64];
static SusamuneCfg config;
static SusamuneGhostStorageMailbox ghost;
static SusamuneSplitStatsCfg testStats;
static u32 invalidations,stores;static bool badInvalidate;
static void DCInvalidateRange(void*p,u32 n){++invalidations;
  badInvalidate|=!((p==&config&&n==32)||(p==&ghost.response&&n==32)||
    (p==&testStats&&n==sizeof(testStats))||(p==&testStats.ackSeq&&n==32));}
static void DCStoreRange(void*,u32){++stores;}
#undef SUSAMUNE_CFG_PPC_PTR
#define SUSAMUNE_CFG_PPC_PTR (&config)
#undef SUSAMUNE_GHOST_STORAGE_PPC_PTR
#define SUSAMUNE_GHOST_STORAGE_PPC_PTR (&ghost)
#undef SUSAMUNE_SPLIT_STATS_PPC_PTR
#define SUSAMUNE_SPLIT_STATS_PPC_PTR (&testStats)
#undef SUSAMUNE_SPLIT_STATS_RUNTIME_PPC_BASE
#define SUSAMUNE_SPLIT_STATS_RUNTIME_PPC_BASE ((__UINTPTR_TYPE__)(memory+32+SUSAMUNE_SPLIT_STATS_RUNTIME_OFFSET))
struct Timer{u32 serial;s32 qf;u32 attemptSerial(){return serial;}bool currentQf(s32*out){*out=qf;return true;}}gQFTTimer;
namespace StageLoader{bool activeRouteMatches(int,int){return false;}}
namespace ILing{int pbProfile(){return 0;}s32 pbQf(int){return -1;}const char*label(int){return "route";}}
namespace Ghost{bool comparisonDelta(u16,u8,s32,s32*){return false;}void captureSplit(u16,u8,s32){}}
enum{SETTING_SPLIT_COMPARISON,SETTING_TIMER_FREEZE_DURATION,SETTING_LEVEL_SPLITS};
struct Settings{u8 get(int){return 0;}bool getBool(int){return true;}}gSettings;
namespace JUtility{struct TColor{TColor(u8,u8,u8,u8){}};}
struct CreationStyle{s16 x,y;u8 scale,padding,bgR,bgG,bgB,bgA,textBrightness,textA;};
class Menu{public:void fillBox(int,int,int,int,JUtility::TColor){}
void drawText(const char*,int,int,int,int,JUtility::TColor){}
static int textWidth(const char*,int){return 0;}};
namespace Creation{int textWidth(const char*,int){return 0;}
void drawTextBox(Menu*,const CreationStyle&,const u8(*)[3],int,const char*,bool){}}
struct QftDisplay{bool leadingZero(){return false;}bool adjacentStyle(const char*,const char*,CreationStyle*){return false;}
bool hasAnchor(const char*){return false;}void draw(Menu*,const char*){}}gQftDisplay;
''' + production + r'''
#define API extern "C" __declspec(dllexport)
API void setup(u32 fault,u32 persistent){
  memset(memory,0xa5,sizeof(memory));memset(&config,0,sizeof(config));
  memset(&ghost,0,sizeof(ghost));memset(&testStats,0,sizeof(testStats));
  config.magic=SUSAMUNE_CFG_MAGIC;config.version=SUSAMUNE_CFG_VERSION;
  config.flags=SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION|SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED;
  if(persistent)config.flags|=SUSAMUNE_CFG_FLAG_SPLIT_STATS_V9;
  ghost.response.responseMagic=SUSAMUNE_GHOST_STORAGE_MAGIC;
  ghost.response.protocolVersion=SUSAMUNE_GHOST_STORAGE_VERSION;
  testStats.magic=SUSAMUNE_SPLIT_STATS_MAGIC;testStats.version=SUSAMUNE_SPLIT_STATS_VERSION;
  testStats.routeCount=SUSAMUNE_SPLIT_STATS_ROUTE_COUNT;testStats.regionCount=SUSAMUNE_SPLIT_STATS_REGION_COUNT;
  testStats.segmentCount=SUSAMUNE_SPLIT_STATS_SEGMENT_COUNT;testStats.profileCount=SUSAMUNE_SPLIT_STATS_PROFILE_COUNT;
  testStats.payloadBytes=sizeof(testStats.payload);testStats.schemaHash=SUSAMUNE_SPLIT_STATS_SCHEMA_HASH;
  testStats.flags=SUSAMUNE_SPLIT_STATS_FLAG_WRITABLE;
  for(u32 region=0;region<3;region++){
    for(u32 route=0;route<132;route++){
      testStats.payload.routeStats[region][route].attempts=10+region;
      testStats.payload.routeStats[region][route].finishes=region;
      testStats.payload.playedQf[region][route]=100+region;
      for(u32 p=0;p<4;p++)testStats.payload.pbIdentityQf[region][p][route]=0xffffffffu;
    }
    for(u32 segment=0;segment<495;segment++){
      testStats.payload.bestQf[region][segment]=120+region;
      for(u32 p=0;p<4;p++)testStats.payload.pbQf[region][p][segment]=0xffffffffu;
    }
  }
  if(fault==1)config.magic=0;if(fault==2)++config.version;
  if(fault==3)config.flags&=~SUSAMUNE_CFG_FLAG_STATE_POOL_EXPANSION;
  if(fault==4)config.flags&=~SUSAMUNE_CFG_FLAG_STATE_CODEC_RELOCATED;
  if(fault==5)ghost.response.responseMagic=0;
  if(fault==6)--ghost.response.protocolVersion;if(fault==7)++ghost.response.protocolVersion;
  gQFTTimer.serial=1;gQFTTimer.qf=0;invalidations=stores=0;badInvalidate=false;
  sState=nullptr;SplitStats::init();
}
API void every_api(){
  SplitStats::beginFrame();SplitStats::update();SplitStats::onStageSetup();
  SplitStats::onILAttemptStarted(5,true);SplitStats::onILAttemptEnded();
  SplitStats::invalidateAttempt();SplitStats::onILResult(5,480);
  SplitStats::onPBDeleted(5,0);SplitStats::onSavestateLoaded();
  SplitStats::onRouteEvent(0,0,120);SplitStats::routeActive(0);
  SplitStats::supportsEntry(5);SplitStats::Summary summary;SplitStats::summary(5,&summary);
  SplitStats::deleteGold(5,0);SplitStats::storageState();Menu menu;SplitStats::draw(&menu);
}
API void finish_attempt(){
  SplitStats::onILAttemptStarted(5,true);
  for(u8 event=0;event<3;event++)SplitStats::onRouteEvent(0,event,120*(event+1));
  gQFTTimer.qf=480;SplitStats::onILResult(5,480);SplitStats::onILAttemptEnded();
}
API void load_state(){SplitStats::onSavestateLoaded();}
API void delete_gold(){SplitStats::deleteGold(5,0);SplitStats::update();}
API void bad_handoff(){config.magic=0;ghost.response.protocolVersion=0;}
API u32 get(u32 key){SplitStats::Summary result={};SplitStats::summary(5,&result);
 switch(key){case 0:return sState!=nullptr;case 1:return SplitStats::storageState();
 case 2:return invalidations;case 3:return badInvalidate;case 4:return result.attempts;
 case 5:return result.finishes;case 6:return result.golds;case 7:return result.playedQf;
 case 8:return result.segments[0].goldQf;case 9:return result.segments[0].pbSegmentQf;
 case 10:return stores;case 11:return testStats.payload.bestQf[0][0];
 case 12:return testStats.payload.bestQf[1][0];case 13:return testStats.payload.bestQf[2][0];
 case 14:return SplitStats::supportsEntry(5);case 15:return SplitStats::routeActive(0);}
 return 0;}
API const void*bytes(){return memory;}
'''
        cls.libs = []
        for emulator in (0, 1):
            source = Path(cls.temp.name) / f"split{emulator}.cpp"
            source.write_text(fixture)
            library = source.with_suffix(".dll")
            proc = subprocess.run([
                str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                "-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                "-fno-builtin", "-mno-stack-arg-probe", f"-DIS_EMULATOR={emulator}",
                "-DSUSAMUNE_VERSION_US=1", "-I", str(ROOT / "include"),
                str(source), "-o", str(library)], capture_output=True, text=True)
            if proc.returncode:
                raise RuntimeError(proc.stdout + proc.stderr)
            lib = C.CDLL(str(library)); cls.libs.append(lib)
            lib.bytes.restype = C.c_void_p
            lib.get.restype = C.c_uint
            cls.addClassCleanup(lambda h=lib._handle: C.windll.kernel32.FreeLibrary(C.c_void_p(h)))

    def assert_untouched_neighbors(self, lib):
        data = C.string_at(lib.bytes(), TAIL_SIZE + 64)
        self.assertEqual(data[:32 + OFFSET], bytes([0xa5]) * (32 + OFFSET))
        self.assertEqual(data[32 + OFFSET + USED:], bytes([0xa5]) * (TAIL_SIZE + 32 - OFFSET - USED))

    def test_unsupported_handoffs_leave_the_entire_bank_untouched_for_every_api(self):
        lib = self.libs[0]
        for fault in range(1, 8):
            with self.subTest(fault=fault):
                lib.setup(fault, 1); lib.every_api()
                self.assertEqual([lib.get(i) for i in (0, 1, 3, 10, 14, 15)], [0, 3, 0, 0, 0, 0])
                self.assertEqual(lib.get(2), 1 + int(fault >= 5))
                self.assertEqual(C.string_at(lib.bytes(), TAIL_SIZE + 64), bytes([0xa5]) * (TAIL_SIZE + 64))

    def test_current_console_and_fixed_dolphin_layout_admit_only_the_owned_window(self):
        for emulator, lib in enumerate(self.libs):
            for fault in (range(8) if emulator else (0,)):
                with self.subTest(emulator=emulator, fault=fault):
                    lib.setup(fault, 0)
                    self.assertEqual([lib.get(i) for i in (0, 1, 3, 14)], [1, 0, 0, 1])
                    self.assert_untouched_neighbors(lib)

    def test_stats_and_gold_publication_survive_relocation_and_state_load(self):
        for lib in self.libs:
            lib.setup(0, 0); lib.finish_attempt()
            expected = [1, 1, 4, 480, 120, 120]
            self.assertEqual([lib.get(i) for i in range(4, 10)], expected)
            lib.load_state()
            self.assertEqual([lib.get(i) for i in range(4, 10)], expected)
            self.assertEqual(lib.get(15), 0)
            self.assert_untouched_neighbors(lib)

    def test_admission_is_latched_and_not_rechecked_against_live_mailbox_traffic(self):
        lib = self.libs[0]
        lib.setup(0, 0); count = lib.get(2); lib.bad_handoff(); lib.finish_attempt()
        self.assertEqual([lib.get(i) for i in (0, 4, 5, 2)], [1, 1, 1, count])
        self.assert_untouched_neighbors(lib)

    def test_sd_payload_load_and_save_keep_other_regions_unchanged(self):
        lib = self.libs[0]
        lib.setup(0, 1)
        self.assertEqual([lib.get(i) for i in (1, 4, 5, 7, 8)], [4, 11, 1, 101, 121])
        lib.delete_gold()
        self.assertEqual([lib.get(i) for i in (1, 10, 11, 12, 13)], [2, 2, 120, 0xffffffff, 122])
        self.assert_untouched_neighbors(lib)


if __name__ == "__main__":
    unittest.main()
