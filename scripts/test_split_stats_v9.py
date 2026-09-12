"""Exercise the production V9 journal and semantic V8 migration on the host."""
import ctypes as C
from itertools import accumulate
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import split_checkpoint_schema as schema
from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
UNSET = 0xFFFFFFFF
ROUTES = len(schema.ROUTE_ENTRIES)
SEGMENTS = sum(len(points) + 1 for points in schema.CHECKPOINTS)


class RouteStats(C.Structure):
    _fields_ = [('attempts', C.c_uint), ('finishes', C.c_uint), ('golds', C.c_uint)]


def payload_type(segments):
    class Payload(C.Structure):
        _fields_ = [('stats', (RouteStats * ROUTES) * 3),
                    ('played', (C.c_uint * ROUTES) * 3),
                    ('best', (C.c_uint * segments) * 3),
                    ('identity', ((C.c_uint * ROUTES) * 4) * 3),
                    ('pb', ((C.c_uint * segments) * 4) * 3)]
    return Payload


OldPayload = payload_type(285)
Payload = payload_type(SEGMENTS)


class SplitStatsV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != 'win32':
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-split-v9-')
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        kernel = (ROOT / 'launcher/kernel/SusamuneCfg.c').read_text()
        cls.kernel = kernel
        declarations = kernel[kernel.index('static u32 SplitStatsAckSeq'):kernel.index('// "[settings_jp]')]
        routines = kernel[kernel.index('static const u16 SplitV8RouteFirst'):kernel.index('// ---------------------------------------------------------------------\n// Parsing')]
        code = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned char u8; typedef unsigned short u16;
typedef unsigned int u32; typedef int s32; typedef _Bool bool;
typedef u32 UINT;
#define true 1
#define false 0
#define SUSAMUNE_PB_FILE_COUNT 2
#define SUSAMUNE_PB_PATH_SIZE 64
#define FR_OK 0
#define FR_NO_FILE 4
#define FR_NO_PATH 5
#define FR_DISK_ERR 1
#define FR_INVALID_PARAMETER 19
#define FA_READ 1
#define FA_WRITE 2
#define FA_OPEN_EXISTING 0
#define FA_CREATE_ALWAYS 8
#define dbgprintf(...) ((void)0)
static void *memset(void *p, int b, unsigned long long size) {
    u8 *out=p; while(size--) *out++=b; return p;
}
static void *memcpy(void *p,const void *q,unsigned long long size) {
    u8 *out=p; const u8 *in=q; while(size--) *out++=*in++; return p;
}
static int memcmp(const void *p,const void *q,unsigned long long size) {
    const u8 *a=p,*b=q; while(size--){if(*a!=*b)return *a-*b;a++;b++;}return 0;
}
static int contains(const char *s,const char *part) {
    for(;*s;s++){const char*a=s,*b=part;while(*a&&*a==*b){a++;b++;}if(!*b)return 1;}return 0;
}
static int _sprintf(char *out,const char *format,const char *prefix) {
    int n=0;format+=2;while(*prefix)out[n++]=*prefix++;while(*format)out[n++]=*format++;out[n]=0;return n;
}
static const char *SusamuneCfgStoragePrefix(void){return "1:/Moonshine data";}
struct TestFile { u32 size; u8 data[sizeof(struct SusamuneSplitStatsFile)]; };
static struct TestFile disk[4];
static int readFailure=-1, writeFailure=-1, legacyWrites;
typedef struct { int index; u32 position; } FIL;
static int f_open_char(FIL *f,const char *path,int mode) {
    int index=contains(path,"v9_a")?0:contains(path,"v9_b")?1:
              contains(path,"v8_a")?2:contains(path,"v8_b")?3:-1;
    if(index<0)return FR_NO_FILE;
    if(mode&FA_WRITE){if(index>=2)legacyWrites++;disk[index].size=0;}
    else if(!disk[index].size)return FR_NO_FILE;
    f->index=index;f->position=0;return FR_OK;
}
static u32 f_size(FIL *f){return disk[f->index].size;}
static int f_read(FIL *f,void *out,u32 size,UINT *got) {
    if(f->index==readFailure)return FR_DISK_ERR;
    if(size>disk[f->index].size-f->position)size=disk[f->index].size-f->position;
    memcpy(out,disk[f->index].data+f->position,size);f->position+=size;*got=size;return FR_OK;
}
static int f_write(FIL*f,const void*data,u32 size,UINT*wrote) {
    if(f->index==writeFailure)return FR_DISK_ERR;
    memcpy(disk[f->index].data,data,size);disk[f->index].size=size;*wrote=size;return FR_OK;
}
static int f_close(FIL*f){return FR_OK;}
static int f_sync(FIL*f){return FR_OK;}
static struct SusamuneSplitStatsCfgV8 legacyMailbox;
static struct SusamuneSplitStatsCfg mailbox;
#undef SUSAMUNE_SPLIT_STATS_V8_PHYS_PTR
#define SUSAMUNE_SPLIT_STATS_V8_PHYS_PTR (&legacyMailbox)
''' + declarations + function(kernel, 'PbHashWord') + function(kernel, 'PbGenerationIsNewer') + routines + r'''
__declspec(dllexport) void reset(void) {
    memset(disk,0,sizeof(disk));readFailure=writeFailure=-1;legacyWrites=0;
}
__declspec(dllexport) void seed_v8(int slot,u32 generation,int previous) {
    struct SusamuneSplitStatsFileV8 *file=(void*)disk[slot+2].data;
    memset(file,0,sizeof(*file));file->magic=SUSAMUNE_SPLIT_STATS_FILE_MAGIC;
    file->version=8;file->routeCount=132;file->regionCount=3;file->segmentCount=285;
    file->profileCount=4;file->payloadBytes=sizeof(file->payload);
    file->schemaHash=previous?SUSAMUNE_SPLIT_STATS_V8_PREVIOUS_SCHEMA_HASH:SUSAMUNE_SPLIT_STATS_V8_SCHEMA_HASH;
    file->generation=generation;
    for(u32 region=0;region<3;region++){
        for(u32 route=0;route<132;route++){
            file->payload.routeStats[region][route].attempts=1000+route;
            file->payload.routeStats[region][route].finishes=100+route;
            file->payload.routeStats[region][route].golds=route+1;
            file->payload.playedQf[region][route]=10000+region*1000+route+generation;
            for(u32 profile=0;profile<4;profile++)
                file->payload.pbIdentityQf[region][profile][route]=20000+region*1000+profile*200+route;
        }
        for(u32 segment=0;segment<285;segment++){
            file->payload.bestQf[region][segment]=30000+region*1000+segment;
            for(u32 profile=0;profile<4;profile++)
                file->payload.pbQf[region][profile][segment]=40000+region*1000+profile*300+segment;
        }
    }
    file->checksum=SplitStatsV8Checksum(file);disk[slot+2].size=sizeof(*file);
}
__declspec(dllexport) int boot(void){return InitSplitStatsFiles(&mailbox);}
__declspec(dllexport) int save(void){return SplitStatsReady?WriteSplitStatsFile(&mailbox):FR_INVALID_PARAMETER;}
__declspec(dllexport) void payload(void*out){memcpy(out,&mailbox.payload,sizeof(mailbox.payload));}
__declspec(dllexport) void old_payload(int slot,void*out){memcpy(out,disk[slot+2].data+32,sizeof(struct SusamuneSplitStatsPayloadV8));}
__declspec(dllexport) u32 flags(void){return mailbox.flags;}
__declspec(dllexport) u32 generation(void){return SplitStatsGeneration;}
__declspec(dllexport) int active(void){return SplitStatsActiveFile;}
__declspec(dllexport) u32 file_size(int slot){return disk[slot].size;}
__declspec(dllexport) void file_copy(int slot,void*out){memcpy(out,disk[slot].data,disk[slot].size);}
__declspec(dllexport) int legacy_writes(void){return legacyWrites;}
__declspec(dllexport) void fail_read(int slot){readFailure=slot;}
__declspec(dllexport) void fail_write(int slot){writeFailure=slot;}
__declspec(dllexport) void change_file(int slot,int change) {
    struct SusamuneSplitStatsFile *file=(void*)disk[slot].data;
    if(change==0)file->version++;
    if(change==1)file->schemaHash^=1;
    if(change==2)file->checksum^=1;
    if(change==3)file->tailPad[0]=1;
    if(change==4){file->payload.playedQf[0][0]++;file->checksum=SplitStatsChecksum(file);}
    if(change==5)file->generation--;
    if(change==5)file->checksum=SplitStatsChecksum(file);
}
__declspec(dllexport) u32 shape(int which) {
    switch(which){case 0:return sizeof(mailbox.payload);case 1:return sizeof(mailbox);
    case 2:return sizeof(struct SusamuneSplitStatsFile);case 3:return SUSAMUNE_SPLIT_STATS_MAILBOX_SIZE;
    case 4:return SUSAMUNE_SPLIT_STATS_MAILBOX_OFFSET;case 5:return SUSAMUNE_CFG_FLAG_SPLIT_STATS_V9;}
    return 0;
}
'''
        source = work / 'journal.c'
        source.write_text(code)
        dll = work / 'journal.dll'
        result = subprocess.run([str(ROOT / 'toolchain/clang.exe'), '--target=x86_64-pc-windows-msvc',
                                 '-shared', '-nostdlib', '-fno-builtin', '-fuse-ld=lld', '-Xlinker', '/noentry',
                                 '-O2', '-I', str(ROOT / 'include'), str(source), '-o', str(dll)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        cls.dll = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.dll._handle)))
        cls.dll.payload.argtypes = [C.c_void_p]
        cls.dll.old_payload.argtypes = [C.c_int, C.c_void_p]
        cls.dll.file_copy.argtypes = [C.c_int, C.c_void_p]
        cls.dll.seed_v8.argtypes = [C.c_int, C.c_uint, C.c_int]
        cls.dll.generation.restype = C.c_uint

    def setUp(self):
        self.dll.reset()

    def current(self):
        data = Payload()
        self.dll.payload(C.byref(data))
        return data

    def old(self, slot=0):
        data = OldPayload()
        self.dll.old_payload(slot, C.byref(data))
        return data

    def file(self, slot):
        data = C.create_string_buffer(self.dll.file_size(slot))
        self.dll.file_copy(slot, data)
        return data.raw

    def test_current_layout_schema_and_both_endpoint_migration_map(self):
        self.assertEqual([self.dll.shape(i) for i in range(6)],
                         [0xA584, 0xA5E0, 0xA5C0, 0xB000, 0x5F000, 0x200000])
        self.assertEqual(C.sizeof(Payload), 0xA584)
        self.assertEqual(schema.schema_hash(), schema.EXPECTED_SCHEMA_HASH)
        self.assertEqual(schema.schema_hash(schema.V8_CHECKPOINTS), schema.EXPECTED_V8_SCHEMA_HASH)
        expected = []
        first = 0
        for points in schema.CHECKPOINTS:
            expected.append(first)
            first += len(points) + 1
        self.assertEqual(first, SEGMENTS)
        for name, values in [('SplitRouteFirst', expected), ('SplitRouteCount', [len(p)+1 for p in schema.CHECKPOINTS])]:
            body = re.search(r'\b'+name+r'\[[^]]+\] = \{([^}]+)', self.kernel).group(1)
            self.assertEqual([int(x) for x in re.findall(r'\d+', body)], values)
        source = (ROOT / 'src/split_stats.cpp').read_text()
        for first, entry, points in zip(expected, schema.ROUTE_ENTRIES, schema.CHECKPOINTS):
            self.assertIn(f'{{{first}, {entry}, {len(points)}}}', source)
        self.assertEqual(max(map(len, schema.CHECKPOINTS)) + 1, 8)

    def test_v8_migration_preserves_stats_and_only_identical_segment_pairs(self):
        self.dll.seed_v8(0, 13, 0)
        original = self.file(2)
        previous = self.old()
        self.assertEqual(self.dll.boot(), 1)
        current = self.current()
        old_first = new_first = 0
        for route, (old_points, new_points) in enumerate(zip(schema.V8_CHECKPOINTS, schema.CHECKPOINTS)):
            old_pairs = list(zip(('START',)+old_points, old_points+('FINISH',)))
            new_pairs = list(zip(('START',)+new_points, new_points+('FINISH',)))
            for region in range(3):
                self.assertEqual(current.stats[region][route].attempts, previous.stats[region][route].attempts)
                self.assertEqual(current.stats[region][route].finishes, previous.stats[region][route].finishes)
                self.assertEqual(current.played[region][route], previous.played[region][route])
                self.assertEqual(current.stats[region][route].golds,
                                 previous.stats[region][route].golds if old_points == new_points else 0)
                for profile in range(4):
                    self.assertEqual(current.identity[region][profile][route], previous.identity[region][profile][route])
                for local, pair in enumerate(new_pairs):
                    old_index = old_first + old_pairs.index(pair) if pair in old_pairs else None
                    self.assertEqual(current.best[region][new_first+local],
                                     previous.best[region][old_index] if old_index is not None else UNSET)
                    for profile in range(4):
                        self.assertEqual(current.pb[region][profile][new_first+local],
                                         previous.pb[region][profile][old_index] if old_index is not None else UNSET)
            old_first += len(old_pairs)
            new_first += len(new_pairs)
        self.assertEqual(self.dll.flags(), 3)
        self.assertEqual(self.file(2), original)

    def test_newest_legacy_journal_migrates_once_and_new_ab_files_preserve_it(self):
        self.dll.seed_v8(0, 10, 0)
        self.dll.seed_v8(1, 11, 0)
        original = [self.file(2), self.file(3)]
        self.assertEqual(self.dll.boot(), 1)
        self.assertEqual(self.dll.generation(), 11)
        expected = bytes(self.current())
        self.assertEqual(self.dll.save(), 0)
        self.assertEqual(self.dll.active(), 0)
        self.assertEqual(self.dll.generation(), 12)
        self.assertEqual(self.dll.boot(), 1)
        self.assertEqual(self.dll.flags(), 1)
        self.assertEqual(bytes(self.current()), expected)
        self.assertEqual(self.dll.save(), 0)
        self.assertEqual((self.dll.active(), self.dll.generation()), (1, 13))
        self.assertEqual([self.file(2), self.file(3)], original)
        self.assertEqual(self.dll.legacy_writes(), 0)

    def test_future_schema_and_io_failure_block_fallback_without_writing(self):
        for change in (0, 1, 'read'):
            with self.subTest(change=change):
                self.dll.reset(); self.dll.seed_v8(0, 5, 0)
                self.assertEqual(self.dll.boot(), 1); self.assertEqual(self.dll.save(), 0)
                if change == 'read': self.dll.fail_read(0)
                else: self.dll.change_file(0, change)
                original = [self.file(i) for i in range(4)]
                self.assertEqual(self.dll.boot(), 0)
                self.assertEqual(self.dll.flags(), 0)
                self.assertNotEqual(self.dll.save(), 0)
                self.assertEqual([self.file(i) for i in range(4)], original)

    def test_damaged_newer_file_falls_back_to_healthy_generation(self):
        for change in (2, 3):
            self.dll.reset(); self.dll.seed_v8(0, 7, 0)
            self.assertEqual(self.dll.boot(), 1)
            self.assertEqual(self.dll.save(), 0)
            self.assertEqual(self.dll.save(), 0)
            self.dll.change_file(1, change)
            self.assertEqual(self.dll.boot(), 1)
            self.assertEqual((self.dll.active(), self.dll.generation()), (0, 8))

    def test_conflicting_same_generation_disables_journal_and_failed_save_keeps_previous(self):
        self.dll.seed_v8(0, 7, 0); self.assertEqual(self.dll.boot(), 1)
        self.assertEqual(self.dll.save(), 0)
        healthy = self.file(0)
        self.dll.fail_write(1)
        self.assertNotEqual(self.dll.save(), 0)
        self.assertEqual((self.dll.active(), self.dll.generation()), (0, 8))
        self.assertEqual(self.file(0), healthy)
        self.dll.fail_write(-1); self.assertEqual(self.dll.save(), 0)
        self.dll.change_file(1, 4); self.dll.change_file(1, 5)
        self.assertEqual(self.dll.boot(), 0)

    def test_previous_v8_bianco_schema_is_normalized_before_v9_migration(self):
        self.dll.seed_v8(0, 7, 1)
        old = self.old()
        self.assertEqual(self.dll.boot(), 1)
        data = self.current()
        old_first = sum(len(p)+1 for p in schema.V8_CHECKPOINTS[:13])
        first = sum(len(p)+1 for p in schema.CHECKPOINTS[:13])
        for region in range(3):
            self.assertEqual(data.stats[region][13].golds, 0)
            self.assertEqual(data.best[region][first+1], UNSET)
            self.assertEqual(data.best[region][first+2], UNSET)
            self.assertEqual(data.best[region][first+3], old.best[region][old_first+2])
        self.assertEqual(self.dll.flags(), 3)


if __name__ == '__main__':
    unittest.main()
