"""Exercise the ARM layout journal worker with interrupted and stale requests."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INVALID, CHANGED, EMPTY = 0x10001, 0x10002, 0x10003

ADAPTER = r'''
#include "susamune/layout_profile.h"
typedef int FRESULT;
static struct MoonshineLayoutMailbox layoutMailbox;
#define LAYOUT_MAILBOX (&layoutMailbox)
static unsigned failReadAt, failCloseAfterWrite, corruptReadback;
static char failPath[128];
static int f_mkdir_char(const char*p){(void)p;return FR_EXIST;}
static int f_open_char(FIL*f,const char*p,u32 mode){
 if(failPath[0]&&!strcmp(p,failPath))return FR_DISK_ERR;
 return fixture_open(f,p,mode);
}
static int f_read(FIL*f,void*d,UINT n,UINT*got){
 if(readCalls>=failReadAt){*got=0;return FR_DISK_ERR;}
 int r=fixture_read(f,d,n,got);
 if(corruptReadback&&writeBytes&&*got)((u8*)d)[*got-1]^=1;
 return r;
}
static int f_close(FIL*f){return failCloseAfterWrite&&writeBytes?FR_DISK_ERR:fixture_close(f);}
'''
EXPORTS = r'''
#define API __declspec(dllexport)
API void reset(void){
 testCount=writeCount=readBytes=readCalls=writeBytes=0;failWriteAfter=0xffffffffu;
 failSync=false;failReadAt=0xffffffffu;failCloseAfterWrite=corruptReadback=0;failPath[0]=0;
 testStoragePrefix=MOONSHINE_DATA_ROOT;GAME_ID=0x474d534au;
 memset(testFiles,0,sizeof(testFiles));MoonshineLayoutInit();
}
API void reboot(void){MoonshineLayoutInit();}
API void region(u32 game){GAME_ID=game;MoonshineLayoutInit();}
API void volume(u32 second){testStoragePrefix=second?"1:" MOONSHINE_DATA_ROOT:MOONSHINE_DATA_ROOT;MoonshineLayoutInit();}
API void unavailable(void){Enabled=false;}
API u32 prepare(u32 value,const char*name){
 struct MoonshineLayoutFile*r=&layoutMailbox.file;
 memset(r,0,sizeof(*r));r->magic=MOONSHINE_LAYOUT_MAGIC;r->version=MOONSHINE_LAYOUT_VERSION;r->bytes=sizeof(*r);
 r->generation=layoutMailbox.generations[layoutMailbox.slot]+1u;if(!r->generation)r->generation=1;
 for(u32 i=0;i<15&&name[i];i++)r->name[i]=name[i];
 memset(&r->layout,value,sizeof(r->layout));r->checksum=MoonshineLayoutChecksum(r);return sizeof(*r);
}
API void request(u32 command,u32 slot,u32 generation){
 ++layoutMailbox.requestSeq;layoutMailbox.operation=command;layoutMailbox.slot=slot;
 layoutMailbox.expectedGeneration=generation;
}
API int run(void){
 for(u32 i=0;i<1000;i++){
  if(!MoonshineLayoutPending())return (int)layoutMailbox.status;
  u32 before=readBytes+writeBytes;MoonshineLayoutService();
  if(readBytes+writeBytes-before>sizeof(struct MoonshineLayoutFile))return -2;
 }return -1;
}
API u32 generation(u32 slot){return layoutMailbox.generations[slot];}
API u32 mask(void){return layoutMailbox.presentMask;}
API u32 bad(void){return layoutMailbox.badMask;}
API const char*name(u32 slot){return layoutMailbox.names[slot];}
API const void*payload(void){return &layoutMailbox.file.layout;}
API const void*file(const char*p,u32*bytes){int i=lookup(p);if(i<0){*bytes=0;return 0;}*bytes=testFiles[i].size;return testFiles[i].bytes;}
API void corrupt(const char*p,u32 offset){int i=lookup(p);if(i>=0&&offset<testFiles[i].size)((u8*)testFiles[i].bytes)[offset]^=1;}
API void drop(const char*p){fixture_unlink(p);}
API void legacy(const char*p){int i=lookup(p);if(i<0)return;
 struct MoonshineLayoutFile*r=(struct MoonshineLayoutFile*)testFiles[i].bytes;
 r->layout.wallkick.magic=SUSAMUNE_WALLKICK_STYLE_MAGIC;r->layout.wallkick.version=SUSAMUNE_WALLKICK_STYLE_VERSION;
 r->layout.wallkick.x=111;r->layout.wallkick.y=222;
 for(u32 c=0;c<7;c++)for(u32 b=0;b<3;b++)r->layout.wallkick.rgb[c][b]=c*10+b;
 r->version=1;r->bytes=MOONSHINE_LAYOUT_V1_FILE_SIZE;r->checksum=MoonshineLayoutChecksum(r);
 testFiles[i].size=r->bytes;
}
API u32 style(u32 i,u32 field){const struct SusamunePracticeDisplayStyle*s=&layoutMailbox.file.layout.practiceDisplays.entries[i];
 return field==0?s->x:field==1?s->y:s->rgb[field-2][0];}
API u32 loadedVersion(void){return layoutMailbox.file.version;}
API void faults(u32 shortAt,u32 sync,u32 close,u32 readAt,u32 corrupt){
 failWriteAfter=shortAt;failSync=sync;failCloseAfterWrite=close;failReadAt=readAt;corruptReadback=corrupt;
 readBytes=readCalls=writeBytes=0;
}
API void openFailure(const char*p){copystr(failPath,p);}
API void malformed(void){layoutMailbox.file.checksum^=1;}
API void wrongGeneration(void){layoutMailbox.file.generation+=1;layoutMailbox.file.checksum=MoonshineLayoutChecksum(&layoutMailbox.file);}
API u32 writes(void){return writeBytes;}
'''


class LayoutProfileKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-layout-kernel-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        fixture = (ROOT / 'scripts/ghost_kernel_fixture.h').read_text()
        fixture = fixture.replace('#define FIXTURE_FILES 60000', '#define FIXTURE_FILES 40')
        fixture = fixture.replace('#define FIXTURE_WRITES 80', '#define FIXTURE_WRITES 40')
        fixture = fixture.replace('#define FIXTURE_FILE_BYTES 1400000', '#define FIXTURE_FILE_BYTES 4096')
        for name in ('open_char', 'read', 'close', 'unlink_char'):
            fixture = fixture.replace('f_' + name + '(', 'fixture_' + name.replace('_char', '') + '(')
        source = (ROOT / 'launcher/kernel/MoonshineLayout.c').read_text()
        source = re.sub(r'^#include .*$', '', source, flags=re.M)
        (path / 'test.c').write_text(fixture + ADAPTER + source + EXPORTS)
        proc = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O1',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT / 'include'), str(path / 'test.c'), '-o', str(path / 'test.dll')],
            text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.prepare.argtypes = [C.c_uint, C.c_char_p]
        cls.lib.name.restype = C.c_char_p
        cls.lib.payload.restype = C.c_void_p
        cls.lib.file.argtypes = [C.c_char_p, C.POINTER(C.c_uint)]
        cls.lib.file.restype = C.c_void_p
        cls.lib.corrupt.argtypes = [C.c_char_p, C.c_uint]
        cls.lib.drop.argtypes = cls.lib.openFailure.argtypes = [C.c_char_p]
        cls.lib.legacy.argtypes = [C.c_char_p]

    def setUp(self):
        self.lib.reset()

    def command(self, operation, slot=0, generation=None):
        if generation is None:
            generation = self.lib.generation(slot)
        self.lib.request(operation, slot, generation)
        return self.lib.run()

    def save(self, slot=0, value=12, name=b'Practice'):
        self.lib.request(2, slot, self.lib.generation(slot))
        self.lib.prepare(value, name)
        return self.lib.run()

    def path(self, slot=0, copy='a', region='jp', volume=''):
        return f'{volume}/Moonshine data/layouts/layout_{region}_{slot + 1}_{copy}.bin'.encode()

    def file(self, path):
        size = C.c_uint()
        pointer = self.lib.file(path, C.byref(size))
        return C.string_at(pointer, size.value) if pointer else None

    def clear_faults(self):
        self.lib.faults(0xffffffff, 0, 0, 0xffffffff, 0)
        self.lib.openFailure(b'')

    def test_all_five_named_profiles_survive_reboot(self):
        for slot in range(5):
            self.assertEqual(self.save(slot, slot + 10, f'Layout {slot+1}'.encode()), 0)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.mask(), 31)
        for slot in range(5):
            self.assertEqual(self.lib.name(slot), f'Layout {slot+1}'.encode())
            self.assertEqual(self.command(3, slot), 0)
            self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, slot + 10)

    def test_each_region_and_second_volume_have_separate_profiles(self):
        self.assertEqual(self.save(value=11), 0)
        self.lib.region(0x474d5350)
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.mask(), 0)
        self.assertEqual(self.save(value=22), 0)
        self.assertIsNotNone(self.file(self.path(region='pal')))
        self.lib.volume(1)
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.mask(), 0)
        self.assertEqual(self.save(value=33), 0)
        self.assertIsNotNone(self.file(self.path(region='pal', volume='1:')))
        self.assertIsNotNone(self.file(self.path()))

    def test_replacement_uses_inactive_copy_and_latest_name(self):
        self.assertEqual(self.save(name=b'Old'), 0)
        old = self.file(self.path())
        self.assertEqual(self.save(value=99, name=b'New'), 0)
        self.assertEqual(self.file(self.path()), old)
        self.assertEqual(self.lib.generation(0), 2)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.name(0), b'New')
        self.assertEqual(self.command(3), 0)
        self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 99)

    def test_v1_profiles_upgrade_in_memory_and_keep_old_journal_until_explicit_save(self):
        self.assertEqual(self.save(value=33, name=b'Existing E8A'), 0)
        self.lib.legacy(self.path())
        old = self.file(self.path())
        self.assertEqual(len(old), 2256)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.name(0), b'Existing E8A')
        self.assertEqual(self.command(3), 0)
        self.assertEqual(self.lib.loadedVersion(), 2)
        self.assertEqual(self.lib.generation(0), 1)
        self.assertEqual(self.file(self.path()), old)
        self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 33)
        for style in range(3):
            self.assertEqual([self.lib.style(style, f) for f in range(2)], [111, 222])
        self.assertEqual([self.lib.style(0, c+2) for c in range(4)], [10, 0, 60, 60])
        self.assertEqual([self.lib.style(1, c+2) for c in range(7)], list(range(0, 70, 10)))
        self.assertEqual([self.lib.style(2, c+2) for c in range(2)], [0, 10])
        self.assertEqual(self.save(value=77), 0)
        self.assertEqual(self.file(self.path()), old)
        self.assertEqual(len(self.file(self.path(copy='b'))), 2384)

    def test_corrupt_latest_copy_falls_back_to_complete_previous(self):
        self.save(value=11)
        self.save(value=22)
        self.lib.corrupt(self.path(copy='b'), 500)
        self.lib.reboot()
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.generation(0), 1)
        self.assertEqual(self.lib.bad(), 0)
        self.assertEqual(self.command(3), 0)
        self.assertEqual(C.c_ubyte.from_address(self.lib.payload()).value, 11)

    def test_failed_saves_preserve_previous_copy_and_report_failure(self):
        for failure in ((200, 0, 0, 0xffffffff, 0), (0xffffffff, 1, 0, 0xffffffff, 0),
                        (0xffffffff, 0, 1, 0xffffffff, 0), (0xffffffff, 0, 0, 0xffffffff, 1)):
            with self.subTest(failure=failure):
                self.lib.reset()
                self.save(value=11)
                old = self.file(self.path())
                self.lib.faults(*failure)
                self.assertNotEqual(self.save(value=22), 0)
                self.assertEqual(self.file(self.path()), old)
                self.assertEqual(self.lib.generation(0), 1)

    def test_nonmissing_open_or_read_failure_never_writes(self):
        self.save()
        self.clear_faults()
        self.lib.openFailure(self.path(copy='b'))
        self.assertNotEqual(self.save(value=44), 0)
        self.assertEqual(self.lib.writes(), 0)
        self.clear_faults()
        self.lib.faults(0xffffffff, 0, 0, 0, 0)
        self.assertNotEqual(self.save(value=55), 0)
        self.assertEqual(self.lib.writes(), 0)

    def test_stale_selection_after_disk_change_is_rejected(self):
        self.save()
        self.save(value=22)
        self.lib.drop(self.path(copy='b'))
        self.clear_faults()
        self.assertEqual(self.command(3), CHANGED)
        self.assertEqual(self.lib.generation(0), 1)
        self.assertEqual(self.command(3, generation=2), CHANGED)
        self.assertEqual(self.lib.writes(), 0)

    def test_empty_and_invalid_slots_are_distinguishable(self):
        self.assertEqual(self.command(3), EMPTY)
        self.save()
        self.lib.corrupt(self.path(), 500)
        self.assertEqual(self.command(1), 0)
        self.assertEqual(self.lib.mask(), 0)
        self.assertEqual(self.lib.bad(), 1)
        self.assertEqual(self.command(3), INVALID)

    def test_malformed_save_and_generation_do_not_create_file(self):
        for corrupt in (self.lib.malformed, self.lib.wrongGeneration):
            self.lib.reset()
            self.lib.request(2, 0, 0)
            self.lib.prepare(12, b'Invalid')
            corrupt()
            self.assertEqual(self.lib.run(), INVALID)
            self.assertIsNone(self.file(self.path()))

    def test_invalid_slot_or_operation_do_not_write(self):
        for operation, slot in ((0, 0), (4, 0), (2, 5), (3, 99)):
            self.assertEqual(self.command(operation, slot, 0), INVALID)
        self.assertEqual(self.lib.writes(), 0)

    def test_unavailable_storage_acknowledges_instead_of_hanging(self):
        self.lib.unavailable()
        self.assertNotEqual(self.command(1), 0)
        self.assertEqual(self.lib.writes(), 0)


if __name__ == '__main__':
    unittest.main()
