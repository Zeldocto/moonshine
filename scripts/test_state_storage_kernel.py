"""Run the production archive worker against bounded RAM and memory-backed FatFS."""
import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
POOL = STAGING = EXPANDED = None  # Filled from the compiled worker's shared map.
EXPORT, IMPORT, CATALOG, CANCEL, RENAME, DELETE = 1, 2, 3, 4, 5, 6
WINDOW = 7
OK, IO, BAD, FULL, CANCELLED, STALE, CONFIG = 0, 2, 3, 4, 6, 7, 8


class Header(C.Structure):
    _fields_ = [(n, C.c_uint) for n in (
        'magic', 'version', 'headerSize', 'metadataSize', 'packedSize', 'rawSize',
        'gameId', 'buildCrc', 'snapshotVersion', 'configId', 'metadataCrc', 'payloadCrc',
        'headerCrc', 'sceneKey', 'reserved0', 'reserved1')] + [('name', C.c_char * 32)]


class NameRecord(C.Structure):
    _fields_ = [(n, C.c_uint) for n in ('magic','version','archiveId','generation')] + [
        ('name',C.c_char*32)] + [(n,C.c_uint) for n in ('checksum','archiveChecksum','reserved0','reserved1')]


ADAPTER = r'''
#include "susamune/state_storage.h"
typedef int FRESULT;
static struct SusamuneStateStorageMailbox stateMailbox;
static u8 statePool[SUSAMUNE_STATE_POOL_SIZE + 64], stateStaging[SUSAMUNE_STATE_STAGING_SIZE + 64];
static u8 stateExtra[SUSAMUNE_STATE_POOL_EXTRA_SIZE + 64];
#define STATE_MAILBOX (&stateMailbox)
#define STATE_POOL (statePool + 32)
#define STATE_POOL_EXTRA (stateExtra + 32)
#define STATE_STAGING (stateStaging + 32)
static int f_mkdir_char(const char *p) {
 if(lookup(p)>=0)return FR_EXIST;
 if(testCount>=FIXTURE_FILES)return FR_DENIED;
 struct TestFile *v=&testFiles[testCount++];copystr(v->path,p);
 v->live=1;v->directory=1;return FR_OK;
}
static bool failRename;
static u32 failReadAfter = 0xffffffffu;
static int f_read(FIL *file,void *out,UINT amount,UINT *done) {
 if(readBytes>=failReadAfter){*done=0;return FR_DISK_ERR;}
 return fixture_read(file,out,amount,done);
}
static bool failUnlink;
static char failOpenPath[128];
static int f_open_char(FIL *file,const char *path,u32 flags) {
 if(failOpenPath[0] && !strcmp(path,failOpenPath))return FR_DISK_ERR;
 return fixture_open(file,path,flags);
}
static int f_unlink_char(const char *path) {return failUnlink?FR_DISK_ERR:fixture_unlink(path);}
static int f_rename_char(const char *from,const char *to) {
 if(failRename) return FR_DISK_ERR;
 int index=lookup(from); if(index<0) return FR_NO_FILE;
 if(lookup(to)>=0) return FR_EXIST;
 copystr(testFiles[index].path,to); return FR_OK;
}
'''

EXPORTS = r'''
__declspec(dllexport) void reset(void) {
 testStoragePrefix=MOONSHINE_DATA_ROOT;
 testCount=writeCount=readBytes=readCalls=dirCalls=maxRead=writeBytes=0;
 failWriteAfter=0xFFFFFFFFu; failSync=failRename=failUnlink=false; failOpenPath[0]=0; directoryResult=FR_OK;
 failReadAfter=0xffffffffu;
 memset(testFiles,0,sizeof(testFiles)); memset(statePool,0x5A,sizeof(statePool));
 memset(stateStaging,0xA5,sizeof(stateStaging)); memset(stateExtra,0xC3,sizeof(stateExtra)); SusamuneStateStorageInit();
}
__declspec(dllexport) void volume(u32 usb) {
 testStoragePrefix=usb?"1:" MOONSHINE_DATA_ROOT:MOONSHINE_DATA_ROOT;
 SusamuneStateStorageInit();
}
__declspec(dllexport) const char *maximumPath(void) {
 TasDirectory(0xffffffffu);Paths(0xffffffffu);return Path;
}
__declspec(dllexport) void submit(u32 command,u32 id,u32 offset,u32 size,u32 crc,u32 session) {
 struct SusamuneStateRequest *r=&stateMailbox.request;
 ++r->seq; r->command=command; r->id=id; r->session=session;
 r->poolOffset=offset; r->packedSize=size; r->expectedHeaderCrc=crc; r->reserved=0;
}
__declspec(dllexport) void windowSize(u32 size) {stateMailbox.request.reserved=size;}
__declspec(dllexport) void readFailure(u32 after) {failReadAfter=after;}
__declspec(dllexport) int run(u32 limit) {
 for(u32 i=0;i<limit;++i) {
  u32 reads=readBytes,writes=writeBytes,dirs=dirCalls;
  if(!SusamuneStateStoragePending()) return (int)i;
  SusamuneStateStorageService();
  if(readBytes-reads>SUSAMUNE_STATE_CHUNK_SIZE || writeBytes-writes>SUSAMUNE_STATE_CHUNK_SIZE || dirCalls-dirs>16) return -2;
 }
 return SusamuneStateStoragePending()?-1:0;
}
__declspec(dllexport) void prepare(const void *data,u32 size,u32 offset,const void *meta,u32 metaSize) {
 struct SusamuneStateArchiveHeader *h=&stateMailbox.header;
 memset(h,0,sizeof(*h)); h->magic=SUSAMUNE_STATE_ARCHIVE_MAGIC; h->version=1;
 h->headerSize=sizeof(*h); h->metadataSize=metaSize; h->packedSize=size;
 h->rawSize=size*2; h->gameId=GAME_ID; h->buildCrc=123; h->snapshotVersion=15;
 h->configId=ConfigId; h->metadataCrc=SusamuneStateCrc(meta,metaSize);
 h->sceneKey=0x10203; memcpy(h->name,"Bianco 3",9);
 h->headerCrc=SusamuneStateHeaderCrc(h);
 memcpy(stateMailbox.metadata,meta,metaSize);
 u32 written=0;while(written<size){u32 piece=size-written;u8*target=PoolPiece(offset+written,&piece);
 memcpy(target,(const u8*)data+written,piece);written+=piece;}
}
__declspec(dllexport) int add(const char *path,const u8 *bytes,u32 size) {
 int i=lookup(path); if(i<0) i=(int)testCount++;
 if(i>=FIXTURE_FILES) return -1;
 copystr(testFiles[i].path,path); testFiles[i].bytes=bytes;
 testFiles[i].size=size; testFiles[i].live=1; testFiles[i].writable=0; return i;
}
__declspec(dllexport) const void *file(const char *p,u32 *size) {
 int i=lookup(p); if(i<0) {*size=0; return 0;} *size=testFiles[i].size; return testFiles[i].bytes;
}
__declspec(dllexport) const void *mailbox(void) {return &stateMailbox;}
__declspec(dllexport) const void *pool(void) {return STATE_POOL;}
__declspec(dllexport) const void *staging(void) {return STATE_STAGING;}
__declspec(dllexport) const void *extra(void) {return STATE_POOL_EXTRA;}
__declspec(dllexport) u32 poolSize(void) {return SUSAMUNE_STATE_POOL_SIZE;}
__declspec(dllexport) u32 stagingSize(void) {return SUSAMUNE_STATE_STAGING_SIZE;}
__declspec(dllexport) u32 expandedSize(void) {return SUSAMUNE_STATE_POOL_EXPANDED_SIZE;}
__declspec(dllexport) void reboot(void) {SusamuneStateStorageInit();}
__declspec(dllexport) void requestName(const char *name) {memset(stateMailbox.requestName,0,32);for(u32 i=0;i<32&&name[i];++i)stateMailbox.requestName[i]=name[i];}
__declspec(dllexport) void unlinkFailure(u32 value) {failUnlink=value;}
__declspec(dllexport) void openFailure(const char *name) {copystr(failOpenPath,name);}
__declspec(dllexport) void clearIo(void) {readBytes=writeBytes=0;}
__declspec(dllexport) u32 reads(void) {return readBytes;}
__declspec(dllexport) u32 writes(void) {return writeBytes;}
__declspec(dllexport) void failures(u32 after,u32 sync,u32 rename) {
 failWriteAfter=after; failSync=sync; failRename=rename;
}
__declspec(dllexport) u32 guards(void) {
 for(u32 i=0;i<32;++i) if(statePool[i]!=0x5A || statePool[32+SUSAMUNE_STATE_POOL_SIZE+i]!=0x5A ||
   stateStaging[i]!=0xA5 || stateStaging[32+SUSAMUNE_STATE_STAGING_SIZE+i]!=0xA5 ||
   stateExtra[i]!=0xC3 || stateExtra[32+SUSAMUNE_STATE_POOL_EXTRA_SIZE+i]!=0xC3) return 0;
 return 1;
}
'''


class StateStorageKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-state-files-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        fixture = (ROOT / 'scripts/ghost_kernel_fixture.h').read_text()
        fixture = fixture.replace('#define FIXTURE_FILES 60000', '#define FIXTURE_FILES 100')
        fixture = fixture.replace('#define FIXTURE_WRITES 80', '#define FIXTURE_WRITES 16')
        fixture = fixture.replace('#define FIXTURE_FILE_BYTES 1400000', '#define FIXTURE_FILE_BYTES 6000000')
        fixture = fixture.replace('f_open_char(', 'fixture_open(').replace('f_unlink_char(', 'fixture_unlink(')
        fixture = fixture.replace('f_read(', 'fixture_read(')
        fixture = fixture.replace('int live; int writable;', 'int live; int writable; int directory;')
        fixture = fixture.replace('info->fsize=testFiles[i].size; return FR_OK;',
                                  'info->fsize=testFiles[i].size; info->fattrib=testFiles[i].directory?AM_DIR:0; return FR_OK;')
        fixture = fixture.replace('info->fsize=v->size; return FR_OK;',
                                  'info->fsize=v->size; info->fattrib=v->directory?AM_DIR:0; return FR_OK;')
        source = (ROOT / 'launcher/kernel/SusamuneStateStorage.c').read_text()
        source = source.replace('#include "SusamuneTasStorage.inc"',
                                (ROOT / 'launcher/kernel/SusamuneTasStorage.inc').read_text())
        source = re.sub(r'^#include .*$', '', source, flags=re.M)
        start = source.index('static u32 BootConfigId(void)')
        end = source.index('\nstatic void Paths(', start)
        source = source[:start] + 'static u32 BootConfigId(void) {return 6789u;}\n' + source[end:]
        (path / 'test.c').write_text(fixture + ADAPTER + source + EXPORTS)
        proc = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-shared', '-O1',
            '-fno-builtin', '-nostdlib', '-fuse-ld=lld', '-Xlinker', '/noentry',
            '-I', str(ROOT / 'include'), str(path / 'test.c'), '-o', str(path / 'test.dll')],
            text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        cls.lib = C.CDLL(str(path / 'test.dll'))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.submit.argtypes = [C.c_uint] * 6
        cls.lib.prepare.argtypes = [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p, C.c_uint]
        cls.lib.add.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]
        cls.lib.file.argtypes = [C.c_char_p, C.POINTER(C.c_uint)]
        cls.lib.requestName.argtypes = [C.c_char_p]
        cls.lib.openFailure.argtypes = [C.c_char_p]
        cls.lib.maximumPath.restype = C.c_char_p
        for name in ('mailbox', 'pool', 'staging', 'extra', 'file'):
            getattr(cls.lib, name).restype = C.c_void_p
        global POOL, STAGING, EXPANDED
        POOL,STAGING,EXPANDED=cls.lib.poolSize(),cls.lib.stagingSize(),cls.lib.expandedSize()

    def setUp(self):
        self.lib.reset()
        self.buffers = []

    def test_project_component_paths_fit_both_volume_prefixes_with_wide_ids(self):
        for volume in (0, 1):
            self.lib.volume(volume)
            expected = ('1:' if volume else '') + '/Moonshine data/tas/tas_4294967295/state_4294967295.mss'
            self.assertEqual(self.lib.maximumPath().decode(), expected)
            self.assertLess(len(expected), 96)

    def buffer(self, data):
        out = C.create_string_buffer(data)
        self.buffers.append(out)
        return out

    def command(self, command, id=0, offset=0, size=0, crc=0, session=11):
        self.lib.submit(command, id, offset, size, crc, session)

    def finish(self):
        self.assertGreaterEqual(self.lib.run(5000), 0)
        self.assertEqual(self.lib.guards(), 1)
        return C.c_uint.from_address(self.lib.mailbox() + 44).value

    def file(self, id=1, suffix='mss'):
        size = C.c_uint()
        pointer = self.lib.file(f'/Moonshine data/states/state_{id:08d}.{suffix}'.encode(), C.byref(size))
        return C.string_at(pointer, size.value) if pointer else None

    def add(self, id, data, suffix='mss'):
        self.lib.add(f'/Moonshine data/states/state_{id:08d}.{suffix}'.encode(), self.buffer(data), len(data))

    def export(self, data=b'opaque compressed payload' * 900, meta=b'owned game and profile metadata', offset=32):
        self.lib.prepare(self.buffer(data), len(data), offset, self.buffer(meta), len(meta))
        self.command(EXPORT, offset=offset, size=len(data))
        self.assertEqual(self.finish(), OK)
        return self.file(), data, meta

    def rename(self, crc, name=b'Renamed', id=1):
        self.lib.requestName(name)
        self.command(RENAME,id,crc=crc)
        return self.finish()

    def catalog(self):
        self.command(CATALOG)
        self.assertEqual(self.finish(),OK)
        m=self.lib.mailbox()
        count=C.c_uint.from_address(m+192).value
        return [(C.c_uint.from_address(m+224+64*i).value,
                 C.string_at(m+256+64*i,32).split(b'\0')[0]) for i in range(count)]

    def window(self, header, offset, size):
        self.command(WINDOW,1,offset,header.packedSize,header.headerCrc)
        self.lib.windowSize(size)
        return self.finish()

    def test_windows_read_requested_file_bytes_without_touching_three_slot_pool(self):
        data=bytes(range(251))*23000
        archive,data,meta=self.export(data=data)
        h=Header.from_buffer_copy(archive)
        pool=C.string_at(self.lib.pool(),POOL)
        extra=C.string_at(self.lib.extra(),EXPANDED-POOL)
        for offset,size in ((0,STAGING),(STAGING,len(data)-STAGING),(123,70001),(len(data)-1,1)):
            with self.subTest(offset=offset,size=size):
                self.lib.clearIo()
                self.assertEqual(self.window(h,offset,size),OK)
                self.assertEqual(C.string_at(self.lib.staging(),size),data[offset:offset+size])
                receipt=(C.c_uint*8).from_address(self.lib.mailbox()+7968)
                self.assertEqual(list(receipt),[offset,size,zlib.crc32(data[offset:offset+size]),0,0,0,0,0])
                self.assertLessEqual(self.lib.reads(),size+96+len(meta)+224)
        self.assertEqual(C.string_at(self.lib.pool(),POOL),pool)
        self.assertEqual(C.string_at(self.lib.extra(),EXPANDED-POOL),extra)

    def test_window_refuses_bad_bounds_identity_and_metadata_before_payload(self):
        archive,data,meta=self.export()
        h=Header.from_buffer_copy(archive)
        for offset,size in ((0,0),(0,STAGING+1),(len(data),1),(0xffffffff,1)):
            self.assertEqual(self.window(h,offset,size),9)
        self.command(WINDOW,1,0,h.packedSize,h.headerCrc^1);self.lib.windowSize(20)
        self.assertEqual(self.finish(),STALE)
        changed=bytearray(archive);changed[96]^=1;self.add(1,bytes(changed))
        self.assertEqual(self.window(h,0,20),BAD)
        self.assertEqual(C.string_at(self.lib.staging(),20),b'\xA5'*20)

    def test_window_read_failure_and_cancellation_do_not_publish_success(self):
        archive,data,meta=self.export(data=b'a'*200000)
        h=Header.from_buffer_copy(archive)
        self.lib.clearIo();self.lib.readFailure(96+len(meta)+32768)
        self.assertEqual(self.window(h,0,len(data)),IO)
        self.lib.readFailure(0xffffffff)
        self.command(WINDOW,1,0,h.packedSize,h.headerCrc);self.lib.windowSize(len(data))
        self.assertEqual(self.lib.run(6),-1)
        self.command(CANCEL)
        self.assertEqual(self.finish(),CANCELLED)
        self.assertEqual(self.window(h,100,1234),OK)

    def test_changed_window_returns_new_checksum_for_the_restore_validator(self):
        archive,data,meta=self.export()
        h=Header.from_buffer_copy(archive)
        self.assertEqual(self.window(h,0,2000),OK)
        before=C.c_uint.from_address(self.lib.mailbox()+7976).value
        changed=bytearray(archive);changed[96+len(meta)+10]^=1
        self.add(1,bytes(changed))
        self.assertEqual(self.window(h,0,2000),OK)
        self.assertNotEqual(C.c_uint.from_address(self.lib.mailbox()+7976).value,before)

    def test_names_survive_reboot_without_rewriting_archive_or_changing_identity(self):
        archive,_,_=self.export()
        h=Header.from_buffer_copy(archive)
        self.lib.clearIo()
        self.assertEqual(self.rename(h.headerCrc,b'Bianco practice'),OK)
        self.assertEqual(self.lib.writes(),64)
        self.assertLessEqual(self.lib.reads(),224)
        self.assertEqual(self.file(),archive)
        self.assertEqual(C.string_at(self.lib.mailbox()+7936,32).split(b'\0')[0],b'Bianco practice')
        record=NameRecord.from_buffer_copy(self.file(suffix='name0'))
        self.assertEqual((record.generation,record.archiveChecksum),(1,h.headerCrc))
        self.lib.reboot()
        self.assertEqual(self.catalog(),[(1,b'Bianco practice')])
        self.assertEqual(self.rename(h.headerCrc,b'Second name'),OK)
        self.lib.reboot()
        self.assertEqual(self.catalog(),[(1,b'Second name')])
        self.command(IMPORT,1,0,h.packedSize,h.headerCrc)
        self.assertEqual(self.finish(),OK)
        restored=Header.from_buffer_copy(C.string_at(self.lib.mailbox()+96,96))
        self.assertEqual(restored.headerCrc,h.headerCrc)
        self.assertEqual(restored.name,b'Bianco 3')
        self.assertEqual(C.string_at(self.lib.mailbox()+7936,32).split(b'\0')[0],b'Second name')

    def test_rename_failures_keep_active_generation_and_unchanged_payload(self):
        archive,_,_=self.export()
        crc=Header.from_buffer_copy(archive).headerCrc
        self.assertEqual(self.rename(crc,b'First'),OK)
        self.assertEqual(self.rename(crc,b'Current'),OK)
        copies=[self.file(suffix=f'name{i}') for i in range(2)]
        for fault in ('short','sync','rename','unlink','read'):
            with self.subTest(fault=fault):
                self.lib.reset();self.buffers=[];self.add(1,archive)
                for i,data in enumerate(copies):self.add(1,data,f'name{i}')
                if fault=='short':self.lib.failures(63,0,0)
                if fault=='sync':self.lib.failures(0xFFFFFFFF,1,0)
                if fault=='rename':self.lib.failures(0xFFFFFFFF,0,1)
                if fault=='unlink':self.lib.unlinkFailure(1)
                if fault=='read':self.lib.openFailure(b'/Moonshine data/states/state_00000001.name0')
                self.assertEqual(self.rename(crc,b'New'),IO)
                self.lib.failures(0xFFFFFFFF,0,0);self.lib.unlinkFailure(0);self.lib.openFailure(b'')
                self.lib.reboot()
                self.assertEqual(self.catalog(),[(1,b'Current')])
                self.assertEqual(self.file(),archive)

    def test_torn_or_other_archive_names_are_ignored_and_future_names_are_not_overwritten(self):
        archive,_,_=self.export();crc=Header.from_buffer_copy(archive).headerCrc
        self.assertEqual(self.rename(crc,b'First'),OK)
        self.assertEqual(self.rename(crc,b'Second'),OK)
        first=self.file(suffix='name0');second=self.file(suffix='name1')
        for fault in ('crc','truncated','identity','future','generation'):
            with self.subTest(fault=fault):
                changed=bytearray(second)
                r=NameRecord.from_buffer(changed)
                if fault=='crc':r.checksum^=1
                elif fault=='identity':r.archiveChecksum^=1
                elif fault=='future':r.version=2
                elif fault=='generation':r.generation=0xFFFFFFFF
                if fault not in ('crc','truncated'):
                    r.checksum=0;r.checksum=zlib.crc32(changed)
                if fault=='truncated':changed=changed[:-1]
                self.lib.reset();self.buffers=[];self.add(1,archive);self.add(1,first,'name0');self.add(1,bytes(changed),'name1')
                self.assertEqual(self.catalog(),[(1,b'Second' if fault=='generation' else b'First')])
                if fault in ('future','generation'):
                    self.assertEqual(self.rename(crc,b'New'),IO if fault=='future' else FULL)
                    self.assertEqual(self.file(suffix='name1'),changed)

    def test_mutations_pin_archive_identity_and_never_touch_payload_or_old_slots(self):
        archive,_,_=self.export();crc=Header.from_buffer_copy(archive).headerCrc
        for command in (RENAME,DELETE):
            self.lib.requestName(b'Name')
            self.command(command,1,crc=crc^1)
            self.assertEqual(self.finish(),STALE)
            self.assertEqual(self.file(),archive)
            self.command(command,2,crc=crc)
            self.assertEqual(self.finish(),5)
            self.assertEqual(self.file(),archive)
        for name in (b'',b'x'*32,b'a\nb'):
            self.lib.requestName(name)
            self.command(RENAME,1,crc=crc)
            self.assertEqual(self.finish(),9)
        self.assertEqual(C.string_at(self.lib.staging(),64),b'\xA5'*64)

    def test_delete_reserves_id_removes_only_selected_file_and_reuses_no_payload_space(self):
        archive,data,meta=self.export();crc=Header.from_buffer_copy(archive).headerCrc
        self.add(7,archive)
        self.assertEqual(self.rename(crc,b'Delete this'),OK)
        self.lib.clearIo();self.command(DELETE,1,crc=crc)
        self.assertEqual(self.finish(),OK)
        self.assertEqual(self.lib.writes(),96)
        self.assertIsNone(self.file());self.assertIsNone(self.file(suffix='name0'))
        self.assertEqual(self.file(7),archive)
        self.assertEqual(len(self.file(suffix='used')),96)
        self.lib.reboot();self.assertEqual(self.catalog(),[(7,b'Bianco 3')])
        self.lib.prepare(self.buffer(data),len(data),32,self.buffer(meta),len(meta))
        self.command(EXPORT,offset=32,size=len(data))
        self.assertEqual(self.finish(),OK)
        self.assertIsNone(self.file());self.assertEqual(self.file(2),archive)

    def test_delete_failures_preserve_archive_and_cancel_before_commit_has_no_mutation(self):
        archive,_,_=self.export();crc=Header.from_buffer_copy(archive).headerCrc
        for fault in ('short','sync','unlink'):
            with self.subTest(fault=fault):
                self.lib.reset();self.buffers=[];self.add(1,archive)
                if fault=='short':self.lib.failures(20,0,0)
                if fault=='sync':self.lib.failures(0xFFFFFFFF,1,0)
                if fault=='unlink':self.lib.unlinkFailure(1)
                self.command(DELETE,1,crc=crc);self.assertEqual(self.finish(),IO)
                self.assertEqual(self.file(),archive)
                self.lib.failures(0xFFFFFFFF,0,0);self.lib.unlinkFailure(0);self.lib.clearIo()
                self.command(DELETE,1,crc=crc);self.assertEqual(self.finish(),OK)
                self.assertEqual(self.lib.writes(),96)
                self.assertEqual(self.file(suffix='used'),archive[:96])
        for command in (RENAME,DELETE):
            self.lib.reset();self.buffers=[];self.add(1,archive);self.lib.requestName(b'Changed')
            self.command(command,1,crc=crc)
            self.assertEqual(self.lib.run(3),-1)
            self.command(CANCEL,session=22)
            self.assertEqual(self.finish(),CANCELLED)
            self.assertEqual(self.file(),archive)
            self.assertIsNone(self.file(suffix='name0'))
            self.assertIsNone(self.file(suffix='used'))

    def test_atomic_export_crc_and_roundtrip_across_two_bounded_segments(self):
        data = (bytes(range(256)) * ((STAGING + 12345) // 256 + 1))[:STAGING + 12345]
        archive, data, meta = self.export(data)
        h = Header.from_buffer_copy(archive)
        self.assertEqual(h.payloadCrc, zlib.crc32(data))
        self.assertEqual(h.metadataCrc, zlib.crc32(meta))
        check = bytearray(archive[:96]); check[48:52] = b'\0' * 4
        self.assertEqual(h.headerCrc, zlib.crc32(check))
        self.assertEqual(archive[96:], meta + data)
        self.assertIsNone(self.file(suffix='tmp'))
        self.lib.reset(); self.buffers = []; self.add(1, archive)
        self.command(IMPORT, 1, 0x200001, h.packedSize, h.headerCrc)
        self.assertEqual(self.finish(), OK)
        self.assertEqual(C.string_at(self.lib.staging(), STAGING), data[:STAGING])
        self.assertEqual(C.string_at(self.lib.pool() + 0x200001, len(data) - STAGING), data[STAGING:])
        self.assertEqual(C.string_at(self.lib.pool(), 0x200001), b'Z' * 0x200001)

    def test_short_write_sync_and_rename_failure_preserve_existing_archive(self):
        archive, data, meta = self.export()
        for after, sync, rename in ((100, 0, 0), (0xFFFFFFFF, 1, 0), (0xFFFFFFFF, 0, 1)):
            with self.subTest(after=after, sync=sync, rename=rename):
                self.lib.reset(); self.buffers = []; self.add(1, archive)
                self.lib.prepare(self.buffer(data), len(data), 32, self.buffer(meta), len(meta))
                self.lib.failures(after, sync, rename)
                self.command(EXPORT, offset=32, size=len(data))
                self.assertNotEqual(self.finish(), OK)
                self.assertEqual(self.file(1), archive)
                self.assertIsNone(self.file(2))
                self.assertIsNotNone(self.file(2, 'tmp'))

    def test_corrupt_truncated_extended_wrong_config_and_stale_files_refuse(self):
        archive, _, _ = self.export()
        h = Header.from_buffer_copy(archive)
        damaged = bytearray(archive); damaged[-1] ^= 0x80
        metadata = bytearray(archive); metadata[96] ^= 1
        wrong = bytearray(archive); changed = Header.from_buffer(wrong); changed.configId ^= 1
        changed.headerCrc = 0; changed.headerCrc = zlib.crc32(wrong[:96])
        for contents, crc, expected in ((archive[:-1], h.headerCrc, BAD), (archive+b'x', h.headerCrc, BAD),
                (damaged, h.headerCrc, BAD), (metadata, h.headerCrc, BAD),
                (archive, h.headerCrc ^ 1, STALE), (wrong, changed.headerCrc, CONFIG)):
            with self.subTest(expected=expected, size=len(contents)):
                self.lib.reset(); self.buffers = []; self.add(1, bytes(contents))
                self.command(IMPORT, 1, 0x200000, h.packedSize, crc)
                self.assertEqual(self.finish(), expected)
                self.assertEqual(C.string_at(self.lib.pool(), 0x200000), b'Z' * 0x200000)

    def test_capacity_rejects_before_any_staging_write(self):
        for offset, size in ((EXPANDED + 32, 10), (EXPANDED, STAGING + 1), (0, EXPANDED + 1), (0, 0)):
            self.command(IMPORT, 1, offset, size, 123)
            self.assertEqual(self.finish(), FULL)
            self.assertEqual(C.string_at(self.lib.staging(), 64), b'\xA5' * 64)

    def test_cancel_ack_retires_previous_writer_before_new_receipt(self):
        archive, _, _ = self.export(b'compressed bytes' * 30000)
        h = Header.from_buffer_copy(archive)
        self.lib.reset(); self.buffers=[]; self.add(1, archive)
        self.command(IMPORT, 1, 0, h.packedSize, h.headerCrc, 11)
        self.assertEqual(self.lib.run(6), -1)
        old_seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.command(CANCEL, session=22)
        new_seq = C.c_uint.from_address(self.lib.mailbox()).value
        self.assertEqual(self.lib.run(1), -1)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+40).value, old_seq)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+64).value, 11)
        self.assertEqual(self.finish(), CANCELLED)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+40).value, new_seq)
        self.assertEqual(C.c_uint.from_address(self.lib.mailbox()+64).value, 22)
        before=C.string_at(self.lib.staging(), h.packedSize)
        self.assertGreaterEqual(self.lib.run(20), 0)
        self.assertEqual(C.string_at(self.lib.staging(), h.packedSize), before)

    def test_catalog_pages_sorted_ids_ignore_partial_and_bad_headers(self):
        archive, _, _ = self.export()
        self.lib.reset(); self.buffers=[]
        for id in (25, 7, 9, 4, 2, 22, 24, 6, 8, 3, 1, 5): self.add(id, archive)
        self.add(10, archive, 'tmp'); self.add(11, b'bad')
        self.command(CATALOG)
        self.assertEqual(self.finish(), OK)
        c = self.lib.mailbox()+192
        self.assertEqual([C.c_uint.from_address(c+i*4).value for i in range(4)], [8,0,8,1])
        self.assertEqual([C.c_uint.from_address(c+32+i*64).value for i in range(8)], list(range(1,9)))
        self.command(CATALOG, 8)
        self.assertEqual(self.finish(), OK)
        self.assertEqual([C.c_uint.from_address(c+i*4).value for i in range(4)], [4,8,25,0])
        self.assertEqual([C.c_uint.from_address(c+32+i*64).value for i in range(4)], [9,22,24,25])

    def test_export_and_import_split_exactly_at_noncontiguous_bank_boundary(self):
        archive, data, meta = self.export(b'bank-crossing-state' * 12000, offset=POOL-123)
        self.assertEqual(archive[96:], meta+data)
        data = (b'archive-tail-crosses-the-bank' * 200000)[:STAGING+45678]
        self.lib.reset(); self.buffers=[]
        archive,data,_ = self.export(data)
        h=Header.from_buffer_copy(archive)
        self.lib.reset();self.buffers=[];self.add(1,archive)
        self.command(IMPORT,1,POOL-123,h.packedSize,h.headerCrc)
        self.assertEqual(self.finish(),OK)
        self.assertEqual(C.string_at(self.lib.pool(),POOL-123),b'Z'*(POOL-123))
        self.assertEqual(C.string_at(self.lib.pool()+POOL-123,123),data[STAGING:STAGING+123])
        self.assertEqual(C.string_at(self.lib.extra(),len(data)-STAGING-123),data[STAGING+123:])

    def test_tail_memory_ownership_keeps_maximum_ghost_file(self):
        text = (ROOT / 'include/susamune/mem2_map.h').read_text()
        self.assertIn('0x0013E000u', text)
        self.assertGreaterEqual(0x13E000, 1297992)
        self.assertEqual(0x91CFF000 + 0x13E000, 0x91E3D000)
        self.assertEqual(0x91E3D000 + 8192, 0x91E3F000)
        self.assertEqual(0x713C0000 + 0x13E000 + 8192, 0x71500000)


if __name__ == '__main__':
    unittest.main()
