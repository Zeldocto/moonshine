"""Run Dolphin's layout CARD journal through the real idle-worker dispatch."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
INVALID, CHANGED, EMPTY = 0x10001, 0x10002, 0x10003

FIXTURE = r'''
#define IS_EMULATOR 1
#include "susamune/layout_profile.h"
typedef unsigned char u8;typedef signed char s8;typedef unsigned short u16;
typedef unsigned int u32;typedef int s32;
#define API extern "C" __declspec(dllexport)
extern "C" void*memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void*memset(void*d,int v,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)v;return d;}
static const u32 kSectorSize=8192,kFileSize=16384;
enum{CARD_SLOTB=1,CARD_ERROR_READY=0,CARD_ERROR_BUSY=-1,CARD_ERROR_NOFILE=-4,CARD_ERROR_IOERROR=-5};
struct CARDFileInfo{int slot,mFileNo;};
struct CARDStat{u32 mLength,mCommentAddr;};
struct OSMutex{bool held;};
int mutexErrors,configWrites,cardReads,cardWrites,failRead,shortWrite,failClose,corruptReadback,failPublish;
bool badMount,managerLocked;
struct CardManager{OSMutex mMutex;unsigned char mCARDBlock[8192];void*mCardWorkArea;int mLastStatus;void unmount(){mLastStatus=-91;}}manager;
CardManager*gpCardManager=&manager;
struct State{OSMutex mutex;u32 requested,completed;s32 completedStatus;bool idleObserved;}state;
State*sState=&state;
enum{INIT_READY=1};int sInitResult=INIT_READY;
void OSLockMutex(OSMutex*m){if(m->held)mutexErrors++;m->held=true;}
void OSUnlockMutex(OSMutex*m){if(!m->held)mutexErrors++;m->held=false;}
bool OSTryLockMutex(OSMutex*m){if(managerLocked||m->held)return false;m->held=true;return true;}
s32 writeRecordLocked(){configWrites++;return 0;}
u32 errorCode(s32 r){return r<0?(u32)-r:(u32)r;}
bool newer(u32 a,u32 b){return (s32)(a-b)>0;}
s32 mount(void*){return badMount?CARD_ERROR_IOERROR:0;}
void unmount(){}
static unsigned char card[5][16384],stale[8192];static bool exists[5];static u32 comment[5];
static MoonshineLayoutMailbox testMailbox;
#undef MOONSHINE_LAYOUT_PPC_PTR
#define MOONSHINE_LAYOUT_PPC_PTR (&testMailbox)
int slotName(const char*n){unsigned i=0;while(n[i])i++;return n[i-1]-'1';}
s32 CARDOpen(int slot,const char*n,CARDFileInfo*f){
 if(slot!=CARD_SLOTB)mutexErrors++;int i=slotName(n);if(i<0||i>=5)return -5;
 if(!exists[i])return CARD_ERROR_NOFILE;f->slot=f->mFileNo=i;return 0;
}
s32 CARDCreate(int slot,const char*n,u32 bytes,CARDFileInfo*f){
 if(slot!=CARD_SLOTB||bytes!=16384)mutexErrors++;int i=slotName(n);if(i<0||i>=5)return -5;
 exists[i]=true;comment[i]=0xffffffffu;f->slot=f->mFileNo=i;memcpy(card[i],stale,8192);memcpy(card[i]+8192,stale,8192);return 0;
}
s32 CARDGetStatus(int slot,int file,CARDStat*status){if(slot!=CARD_SLOTB||file<0||file>=5)return -5;status->mLength=16384;status->mCommentAddr=comment[file];return 0;}
s32 CARDSetStatus(int slot,int file,CARDStat*status){if(slot!=CARD_SLOTB||file<0||file>=5||failPublish)return -5;comment[file]=status->mCommentAddr;return 0;}
s32 CARDRead(CARDFileInfo*f,void*out,u32 n,u32 offset){
 ++cardReads;if(!manager.mMutex.held)mutexErrors++;
 if(cardReads==failRead)return -5;
 if(n!=8192||offset>8192)return -5;
 memcpy(out,card[f->slot]+offset,n);
 if(corruptReadback&&cardWrites)((u8*)out)[100]^=1;return 0;
}
s32 CARDWrite(CARDFileInfo*f,void*in,u32 n,u32 offset){
 ++cardWrites;if(!manager.mMutex.held)mutexErrors++;
 if(n!=8192||offset>8192)return -5;
 if(shortWrite){memcpy(card[f->slot]+offset,in,128);return -5;}
 memcpy(card[f->slot]+offset,in,n);return 0;
}
s32 CARDClose(CARDFileInfo*){return failClose&&cardWrites?-5:0;}
'''

EXPORTS = r'''
#define mailbox testMailbox
API void reset(){
 memset(&state,0,sizeof(state));memset(&mailbox,0,sizeof(mailbox));memset(&manager,0,sizeof(manager));
 memset(exists,0,sizeof(exists));memset(card,0,sizeof(card));memset(stale,0,sizeof(stale));
 mailbox.magic=MOONSHINE_LAYOUT_MAILBOX_MAGIC;mailbox.version=MOONSHINE_LAYOUT_MAILBOX_VERSION;
 mutexErrors=configWrites=cardReads=cardWrites=failRead=shortWrite=failClose=corruptReadback=failPublish=0;badMount=managerLocked=false;
}
API void request(u32 op,u32 slot,u32 gen){mailbox.requestSeq++;mailbox.operation=op;mailbox.slot=slot;mailbox.expectedGeneration=gen;}
API void prepare(u32 value,const char*name){
 MoonshineLayoutFile*r=&mailbox.file;memset(r,0,sizeof(*r));r->magic=MOONSHINE_LAYOUT_MAGIC;r->version=MOONSHINE_LAYOUT_VERSION;r->bytes=sizeof(*r);
 r->generation=mailbox.expectedGeneration+1;if(!r->generation)r->generation=1;
 for(unsigned i=0;i<15&&name[i];i++)r->name[i]=name[i];memset(&r->layout,value,sizeof(r->layout));r->checksum=MoonshineLayoutChecksum(r);
}
API void pump(){service();}
API u32 status(){return mailbox.status;}
API u32 complete(){return mailbox.requestSeq==mailbox.ackSeq;}
API u32 generation(u32 i){return mailbox.generations[i];}
API const char*name(u32 i){return mailbox.names[i];}
API const void*payload(){return &mailbox.file.layout;}
API const void*disk(u32 i){return exists[i]?card[i]:0;}
API void corrupt(u32 i,u32 copy){card[i][copy*8192+100]^=1;}
API void recycle(){memcpy(stale,card[0],8192);MoonshineLayoutFile*r=(MoonshineLayoutFile*)stale;r->generation=999;r->checksum=MoonshineLayoutChecksum(r);}
API void reboot(){memset(&mailbox,0,sizeof(mailbox));mailbox.magic=MOONSHINE_LAYOUT_MAILBOX_MAGIC;mailbox.version=MOONSHINE_LAYOUT_MAILBOX_VERSION;state.idleObserved=false;}
API void faults(u32 rd,u32 wr,u32 close,u32 corrupt){cardReads=cardWrites=0;failRead=rd;shortWrite=wr;failClose=close;corruptReadback=corrupt;}
API void block(u32 status,u32 lock){manager.mLastStatus=(s32)status;managerLocked=lock;}
API s32 gameStatus(){return manager.mLastStatus;}
API u32 errors(){return mutexErrors;}
API u32 writes(){return cardWrites;}
API void queueConfig(){state.requested++;}
API u32 configs(){return configWrites;}
API void malformed(){mailbox.file.checksum^=1;}
API void wrongGeneration(){mailbox.file.generation++;mailbox.file.checksum=MoonshineLayoutChecksum(&mailbox.file);}
API void publicationFailure(u32 fail){failPublish=fail;}
API u32 bad(){return mailbox.badMask;}
API u32 present(){return mailbox.presentMask;}
API void interruptedCreate(u32 slot){CARDFileInfo file;char name[]="moonshine_layout_1";name[sizeof(name)-2]=(char)('1'+slot);CARDCreate(CARD_SLOTB,name,16384,&file);}
API void legacy(u32 slot,u32 generation){
 exists[slot]=true;comment[slot]=kSectorSize-64u;memset(card[slot],0xa5,16384);
 MoonshineLayoutFile*r=(MoonshineLayoutFile*)card[slot];memset(r,0,MOONSHINE_LAYOUT_V1_FILE_SIZE);
 r->magic=MOONSHINE_LAYOUT_MAGIC;r->version=1;r->bytes=MOONSHINE_LAYOUT_V1_FILE_SIZE;
 r->generation=generation;memcpy(r->name,"Old layout",11);r->layout.settings[0]=73;
 SusamuneWallkickStyleCfg &style=r->layout.wallkick;
 style.magic=SUSAMUNE_WALLKICK_STYLE_MAGIC;style.version=SUSAMUNE_WALLKICK_STYLE_VERSION;
 style.x=112;style.y=210;style.scale=155;style.textA=177;style.bgA=91;
 for(u32 i=0;i<sizeof(style.rgb);++i)((u8*)style.rgb)[i]=(u8)(30+i);
 r->checksum=MoonshineLayoutChecksum(r);
}
API u32 upgraded(){
 if(mailbox.file.version!=MOONSHINE_LAYOUT_VERSION||mailbox.file.bytes!=sizeof(mailbox.file)||
    !MoonshineLayoutValid(&mailbox.file)||mailbox.file.layout.settings[0]!=73)return 0;
 SusamunePracticeDisplayStyleCfg expected;
 SusamunePracticeDisplayStyleFromWallkick(&expected,&mailbox.file.layout.wallkick);
 for(u32 i=0;i<sizeof(expected);++i)
  if(((u8*)&expected)[i]!=((u8*)&mailbox.file.layout.practiceDisplays)[i])return 0;
 return 1;
}
API void legacyRequest(){mailbox.file.version=1;mailbox.file.bytes=MOONSHINE_LAYOUT_V1_FILE_SIZE;mailbox.file.checksum=MoonshineLayoutChecksum(&mailbox.file);}
API void oldMailbox(){mailbox.version=1;}
API void prepareStyles(){
 SusamunePracticeDisplayStyleInit(&mailbox.file.layout.practiceDisplays);
 for(u32 i=0;i<3;++i){auto &s=mailbox.file.layout.practiceDisplays.entries[i];s.x=90+i*100;s.y=40+i*35;s.rgb[6][2]=91+i;}
 mailbox.file.checksum=MoonshineLayoutChecksum(&mailbox.file);
}
API u32 styles(){
 const SusamunePracticeDisplayStyleCfg &cfg=mailbox.file.layout.practiceDisplays;
 if(cfg.magic!=SUSAMUNE_PRACTICE_DISPLAY_STYLE_MAGIC)return 0;
 for(u32 i=0;i<3;++i)if(cfg.entries[i].x!=90+i*100||cfg.entries[i].y!=40+i*35||cfg.entries[i].rgb[6][2]!=91+i)return 0;
 return 1;
}
'''


class LayoutProfileCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-layout-card-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = (ROOT / 'src/emulator_persistence.cpp').read_text()
        source = '\n'.join(function(source, name) for name in
                           ('layoutSlotLocked', 'layoutProfilesLocked', 'service'))
        (path / 'test.cpp').write_text(FIXTURE + source + EXPORTS)
        proc = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O1',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT / 'include'), str(path / 'test.cpp'), '-o', str(path / 'test.dll')],
            text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.prepare.argtypes = [C.c_uint, C.c_char_p]
        cls.lib.name.restype = C.c_char_p
        cls.lib.disk.restype = cls.lib.payload.restype = C.c_void_p

    def setUp(self):
        self.lib.reset()

    def finish(self):
        for _ in range(5):
            self.lib.pump()
            if self.lib.complete():
                self.assertEqual(self.lib.errors(), 0)
                return self.lib.status()
        self.fail('layout request did not finish')

    def command(self, op, slot=0, generation=None):
        if generation is None:
            generation = self.lib.generation(slot)
        self.lib.request(op, slot, generation)
        return self.finish()

    def save(self, slot=0, value=11, name=b'Practice'):
        self.lib.request(2, slot, self.lib.generation(slot))
        self.lib.prepare(value, name)
        return self.finish()

    def test_five_named_profiles_roundtrip_after_reboot(self):
        for i in range(5):
            self.assertEqual(self.save(i, i+1, f'Theme {i+1}'.encode()), 0)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        for i in range(5):
            self.assertEqual(self.lib.name(i), f'Theme {i+1}'.encode())
            self.assertEqual(self.command(3, i), 0)
            self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, i+1)

    def test_new_files_erase_recycled_other_journal_sector(self):
        self.assertEqual(self.save(value=11), 0)
        self.lib.recycle()
        self.assertEqual(self.save(1, value=22), 0)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.generation(1), 1)
        self.assertEqual(self.command(3, 1), 0)
        self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 22)

    def test_interrupted_first_save_never_adopts_recycled_profile(self):
        for failure in ('after_create', 'write', 'close', 'verify', 'publish'):
            with self.subTest(failure=failure):
                self.lib.reset()
                self.assertEqual(self.save(value=11), 0)
                self.lib.recycle()
                if failure == 'after_create':
                    self.lib.interruptedCreate(1)
                else:
                    if failure == 'write': self.lib.faults(0, 1, 0, 0)
                    if failure == 'close': self.lib.faults(0, 0, 1, 0)
                    if failure == 'verify': self.lib.faults(0, 0, 0, 1)
                    if failure == 'publish': self.lib.publicationFailure(1)
                    self.assertNotEqual(self.save(1, value=22), 0)
                self.lib.faults(0, 0, 0, 0)
                self.lib.publicationFailure(0)
                self.lib.reboot()
                self.assertEqual(self.command(1), 0)
                self.assertEqual(self.lib.present(), 1)
                self.assertEqual(self.lib.bad(), 2)
                self.assertEqual(self.lib.generation(1), 0)
                self.assertEqual(self.command(3, 1), INVALID)
                self.assertEqual(self.save(1, value=33), 0)
                self.lib.reboot()
                self.assertEqual(self.command(1), 0)
                self.assertEqual(self.lib.generation(1), 1)
                self.assertEqual(self.command(3, 1), 0)
                self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 33)

    def test_corrupt_latest_falls_back_and_stale_request_rejects(self):
        self.save(value=11)
        self.save(value=22)
        self.lib.corrupt(0, 1)
        self.assertEqual(self.command(3), CHANGED)
        self.assertEqual(self.lib.generation(0), 1)
        self.assertEqual(self.command(3), 0)
        self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 11)

    def test_save_errors_keep_previous_sector_and_do_not_report_success(self):
        for faults in ((0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1), (3, 0, 0, 0)):
            with self.subTest(faults=faults):
                self.lib.reset()
                self.save(value=11)
                old = C.string_at(self.lib.disk(0), 8192)
                self.lib.faults(*faults)
                self.assertNotEqual(self.save(value=22), 0)
                self.assertEqual(C.string_at(self.lib.disk(0), 8192), old)
                self.assertEqual(self.lib.generation(0), 1)

    def test_read_error_does_not_overwrite_either_sector(self):
        self.save()
        old = C.string_at(self.lib.disk(0), 16384)
        self.lib.faults(2, 0, 0, 0)
        self.assertNotEqual(self.save(value=33), 0)
        self.assertEqual(C.string_at(self.lib.disk(0), 16384), old)
        self.assertEqual(self.lib.writes(), 0)

    def test_worker_waits_for_idle_and_preserves_retail_status(self):
        self.lib.request(2, 0, 0)
        self.lib.prepare(11, b'Idle')
        self.lib.block(0xffffffff, 0)
        self.lib.pump()
        self.assertFalse(self.lib.complete())
        self.lib.block(7, 1)
        self.lib.pump()
        self.assertFalse(self.lib.complete())
        self.lib.block(7, 0)
        self.lib.pump()
        self.assertFalse(self.lib.complete())
        self.assertEqual(self.finish(), 0)
        self.assertEqual(self.lib.gameStatus(), 7)

    def test_settings_write_retains_priority_over_layout_request(self):
        self.lib.queueConfig()
        self.lib.request(2, 0, 0)
        self.lib.prepare(11, b'Priority')
        self.lib.pump()
        self.lib.pump()
        self.assertEqual(self.lib.configs(), 1)
        self.assertFalse(self.lib.complete())
        self.assertEqual(self.finish(), 0)

    def test_empty_invalid_and_malformed_requests_do_not_create_files(self):
        self.assertEqual(self.command(3), EMPTY)
        for corrupt in (self.lib.malformed, self.lib.wrongGeneration):
            self.lib.reset()
            self.lib.request(2, 0, 0)
            self.lib.prepare(11, b'Invalid')
            corrupt()
            self.assertEqual(self.finish(), INVALID)
            self.assertFalse(self.lib.disk(0))
        self.assertEqual(self.command(3, 5, 0), INVALID)

    def test_legacy_profile_upgrades_only_checked_transfer_copy_without_card_writes(self):
        self.lib.legacy(0, 12)
        original = C.string_at(self.lib.disk(0), 16384)
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.name(0), b'Old layout')
        self.assertEqual(self.lib.generation(0), 12)
        self.assertEqual(self.command(3), 0)
        self.assertEqual(self.lib.upgraded(), 1)
        self.assertEqual(C.string_at(self.lib.disk(0), 16384), original)
        self.assertEqual(self.lib.writes(), 0)

    def test_new_style_payload_roundtrips_and_old_sector_survives_replacement(self):
        self.lib.legacy(0, 12)
        old = C.string_at(self.lib.disk(0), 8192)
        self.assertEqual(self.command(1), 0)
        self.lib.request(2, 0, 12)
        self.lib.prepare(11, b'New styles')
        self.lib.prepareStyles()
        self.assertEqual(self.finish(), 0)
        self.assertEqual(C.string_at(self.lib.disk(0), 8192), old)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.generation(0), 13)
        self.assertEqual(self.command(3), 0)
        self.assertEqual(self.lib.styles(), 1)
        self.lib.corrupt(0, 1)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.generation(0), 12)
        self.assertEqual(self.command(3), 0)
        self.assertEqual(self.lib.upgraded(), 1)

    def test_legacy_file_can_be_read_but_not_submitted_as_a_new_save(self):
        self.lib.request(2, 0, 0)
        self.lib.prepare(11, b'Old request')
        self.lib.legacyRequest()
        self.assertEqual(self.finish(), INVALID)
        self.assertFalse(self.lib.disk(0))
        self.assertEqual(self.lib.writes(), 0)

    def test_old_mailbox_is_rejected_before_any_card_write(self):
        self.lib.oldMailbox()
        self.assertEqual(self.command(1), INVALID)
        self.assertEqual(self.lib.writes(), 0)


if __name__ == '__main__':
    unittest.main()
