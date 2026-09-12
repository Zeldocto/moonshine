"""Run the ARM crash writer against a fault-injecting in-memory FatFS."""

import ctypes as C
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "1:/Moonshine data/crashes"


class File(C.Structure):
    _fields_ = [("size", C.c_uint), ("handle", C.c_uint), ("position", C.c_uint)]


class Directory(C.Structure):
    _fields_ = [("handle", C.c_uint)]


class Info(C.Structure):
    _fields_ = [("attributes", C.c_ubyte), ("name", C.c_ushort * 256)]


class CrashHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if sys.platform != "win32" or not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-crash-history-")
        cls.addClassCleanup(cls.temp.cleanup)
        production = (ROOT / "launcher/kernel/SusamuneCrash.c").read_text()
        production = "\n".join(line for line in production.splitlines()
                               if not line.startswith("#include"))
        start = production.index("static bool ValidStagedMod(")
        end = production.index("void SusamuneCrashInit(", start)
        production = production[:start] + "static bool ValidStagedMod(const void *p) { return false; }\n" + production[end:]
        common = (ROOT / "launcher/kernel/common.c").read_text()
        header = (ROOT / "launcher/kernel/common.h").read_text()
        crc = header[header.index("extern const u32 SusamuneCrcNibbleTable"):
                     header.index("#define SEEK_CUR")]
        crc += common[common.index("const u32 SusamuneCrcNibbleTable"):
                      common.index("void BootStatus(")]
        source = Path(cls.temp.name) / "history.c"
        source.write_text(r'''
typedef __builtin_va_list va_list;
#define va_start __builtin_va_start
#define va_end __builtin_va_end
typedef unsigned int u32; typedef int s32; typedef unsigned char u8;
typedef _Bool bool;
#define true 1
#define false 0
#define FR_OK 0
#define FR_DISK_ERR 1
#define FR_NO_FILE 4
#define FR_EXIST 8
#define FR_INVALID_OBJECT 9
#define FA_READ 1
#define FA_WRITE 2
#define FA_OPEN_EXISTING 0
#define FA_CREATE_ALWAYS 8
#define AM_DIR 16
#define HW_TIMER 0
typedef u32 UINT;
typedef struct { struct { u32 objsize; } obj; u32 handle,position; } FIL;
typedef struct { u32 handle; } DIR;
typedef struct { u8 fattrib; unsigned short fname[256]; } FILINFO;
#include "susamune/crash_report.h"
#include "susamune/mod_bin.h"
#include "susamune/data_paths.h"
static struct SusamuneCrashReport Mailbox;
static struct SusamuneCrashCore Core;
static struct SusamuneCrashAck Ack;
#undef SUSAMUNE_CRASH_PHYS_PTR
#undef SUSAMUNE_CRASH_CORE_PHYS_PTR
#undef SUSAMUNE_CRASH_ACK_PHYS_PTR
#define SUSAMUNE_CRASH_PHYS_PTR (&Mailbox)
#define SUSAMUNE_CRASH_CORE_PHYS_PTR (&Core)
#define SUSAMUNE_CRASH_ACK_PHYS_PTR (&Ack)
static void *Io[12];
void *memcpy(void *d,const void *s,__SIZE_TYPE__ n){u8*a=d;const u8*b=s;while(n--)*a++=*b++;return d;}
void *memset(void *d,int v,__SIZE_TYPE__ n){u8*a=d;while(n--)*a++=(u8)v;return d;}
int memcmp(const void *a,const void *b,__SIZE_TYPE__ n){const u8*x=a,*y=b;while(n--){if(*x!=*y)return *x-*y;++x;++y;}return 0;}
__SIZE_TYPE__ strlen(const char*s){__SIZE_TYPE__ n=0;while(s[n])++n;return n;}
int strncmp(const char*a,const char*b,__SIZE_TYPE__ n){while(n--){if(*a!=*b)return (u8)*a-(u8)*b;if(!*a)return 0;++a;++b;}return 0;}
int strcmp(const char*a,const char*b){return strncmp(a,b,(__SIZE_TYPE__)-1);}
int _sprintf(char*out,const char*fmt,...){va_list ap;va_start(ap,fmt);int n=((int(*)(char*,const char*,va_list))Io[11])(out,fmt,ap);va_end(ap);return n;}
int dbgprintf(const char *fmt,...) { return 0; }
int f_open_char(FIL*f,const char*p,u32 m){return ((int(*)(FIL*,const char*,u32))Io[0])(f,p,m);}
int f_read(FIL*f,void*p,u32 n,u32*g){return ((int(*)(FIL*,void*,u32,u32*))Io[1])(f,p,n,g);}
int f_write(FIL*f,const void*p,u32 n,u32*g){return ((int(*)(FIL*,const void*,u32,u32*))Io[2])(f,p,n,g);}
int f_close(FIL*f){return ((int(*)(FIL*))Io[3])(f);}
int f_sync(FIL*f){return ((int(*)(FIL*))Io[4])(f);}
int f_mkdir_char(const char*p){return ((int(*)(const char*))Io[5])(p);}
int f_stat_char(const char*p,FILINFO*i){return ((int(*)(const char*,FILINFO*))Io[6])(p,i);}
int f_opendir_char(DIR*d,const char*p){return ((int(*)(DIR*,const char*))Io[7])(d,p);}
int f_readdir(DIR*d,FILINFO*i){return ((int(*)(DIR*,FILINFO*))Io[8])(d,i);}
int f_closedir(DIR*d){return ((int(*)(DIR*))Io[9])(d);}
int f_unlink_char(const char*p){return ((int(*)(const char*))Io[10])(p);}
u32 GAME_ID=0x474d534a;
static void sync_before_read(void*p,u32 n){}
static void sync_after_write(void*p,u32 n){}
static u32 read32(u32 a){return 1000000;}
static u32 TimerDiffTicks(u32 a){return 1000000;}
static bool SusamuneCfgStorageAvailable(void){return true;}
static const char *SusamuneCfgStoragePrefix(void){return "1:/Moonshine data";}
''' + crc + production + r'''
__declspec(dllexport) void callbacks(void **p){memcpy(Io,p,sizeof(Io));}
__declspec(dllexport) u32 boot(void){SusamuneCrashInit();return Mailbox.captureSeq;}
__declspec(dllexport) void capture(u32 sequence,u32 core,u32 full){
 memset(&Core,0,sizeof(Core));memset(&Mailbox,0,sizeof(Mailbox));
 if(core){Core.magic=SUSAMUNE_CRASH_CORE_MAGIC;Core.version=SUSAMUNE_CRASH_CORE_VERSION;
 Core.reportSize=sizeof(Core);Core.state=SUSAMUNE_CRASH_STATE_READY;Core.captureSeq=sequence;
 Core.gameId=GAME_ID;Core.contextValid=1;memcpy(Core.build,"Moonshine test",15);
 Core.checksum=ReportChecksum(&Core,sizeof(Core));}
 if(full){Mailbox.magic=SUSAMUNE_CRASH_MAGIC;Mailbox.version=SUSAMUNE_CRASH_VERSION;
 Mailbox.reportSize=sizeof(Mailbox);Mailbox.state=SUSAMUNE_CRASH_STATE_READY;
 Mailbox.captureSeq=sequence;Mailbox.gameId=GAME_ID;Mailbox.checksum=CrashChecksum(&Mailbox);}
}
__declspec(dllexport) void service(void){SusamuneCrashService();}
__declspec(dllexport) const void *blob(u32 core){return core?(const void*)&Core:(const void*)&Mailbox;}
__declspec(dllexport) u32 ackStatus(void){return Ack.status;}
__declspec(dllexport) u32 ackFlags(void){return Ack.savedFlags;}
__declspec(dllexport) u32 enabled(void){return CrashEnabled;}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        build = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc",
            "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
            "-O2", "-I", str(ROOT / "include"), str(source), "-o", str(library)],
            capture_output=True, text=True)
        if build.returncode:
            raise RuntimeError(build.stdout + build.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.blob.restype = C.c_void_p
        specs = [
            ("open", C.POINTER(File), C.c_char_p, C.c_uint),
            ("read", C.POINTER(File), C.c_void_p, C.c_uint, C.POINTER(C.c_uint)),
            ("write", C.POINTER(File), C.c_void_p, C.c_uint, C.POINTER(C.c_uint)),
            ("close", C.POINTER(File)), ("sync", C.POINTER(File)),
            ("mkdir", C.c_char_p), ("stat", C.c_char_p, C.POINTER(Info)),
            ("opendir", C.POINTER(Directory), C.c_char_p),
            ("readdir", C.POINTER(Directory), C.POINTER(Info)),
            ("closedir", C.POINTER(Directory)), ("unlink", C.c_char_p)]
        cls.callbacks = [C.CFUNCTYPE(C.c_int, *types)(
            lambda *args, name=name: getattr(cls.active, "fs_" + name)(*args))
            for name, *types in specs]
        cls.crt = C.CDLL("msvcrt")
        addresses = (C.c_void_p * 12)(*[C.cast(fn, C.c_void_p).value for fn in cls.callbacks],
                                      C.cast(cls.crt.vsprintf, C.c_void_p).value)
        cls.lib.callbacks(addresses)

    def setUp(self):
        type(self).active = self
        self.files, self.handles, self.directories = {}, {}, {}
        self.folders = {"1:/Moonshine data"}
        self.failure = None
        self.assertEqual(self.lib.boot(), 1)

    def fail(self, operation, path=""):
        return self.failure == (operation, "") or self.failure == (operation, path)

    def fs_open(self, file, path, mode):
        path = path.decode()
        path = next((name for name in self.files if name.casefold() == path.casefold()), path)
        if self.fail("open", path): return 1
        if mode & 2:
            if path.rsplit("/", 1)[0] not in self.folders: return 4
            self.files[path] = b""
        if path not in self.files: return 4
        handle = max(self.handles, default=0) + 1
        self.handles[handle] = path
        file.contents.handle, file.contents.position = handle, 0
        file.contents.size = len(self.files[path])
        return 0

    def fs_read(self, file, output, count, got):
        path = self.handles[file.contents.handle]
        got[0] = 0
        if self.fail("read", path): return 1
        data = self.files[path][file.contents.position:file.contents.position + count]
        if self.fail("short-read", path): data = data[:-1]
        if self.fail("corrupt-read", path) and data: data = bytes([data[0] ^ 1]) + data[1:]
        C.memmove(output, data, len(data))
        got[0] = len(data)
        file.contents.position += len(data)
        return 0

    def fs_write(self, file, data, count, wrote):
        path = self.handles[file.contents.handle]
        wrote[0] = 0
        if self.fail("write", path): return 1
        if self.fail("short-write", path): count -= 1
        self.files[path] += C.string_at(data, count)
        file.contents.position += count
        file.contents.size = len(self.files[path])
        wrote[0] = count
        return 0

    def fs_close(self, file):
        path = self.handles.pop(file.contents.handle)
        return 1 if self.fail("close", path) else 0

    def fs_sync(self, file):
        return 1 if self.fail("sync", self.handles[file.contents.handle]) else 0

    def fs_mkdir(self, path):
        path = path.decode()
        if self.fail("mkdir", path): return 1
        if path in self.folders or path in self.files: return 8
        self.folders.add(path)
        return 0

    def fs_stat(self, path, info):
        path = path.decode()
        if self.fail("stat", path): return 1
        info.contents.attributes = 16 if path in self.folders else 0
        return 0 if path in self.folders or path in self.files else 4

    def fs_opendir(self, directory, path):
        path = path.decode()
        if self.fail("opendir", path): return 1
        if path not in self.folders: return 4
        handle = max(self.directories, default=0) + 1
        self.directories[handle] = iter([name for name in self.files if name.rsplit("/", 1)[0] == path])
        directory.contents.handle = handle
        return 0

    def fs_readdir(self, directory, info):
        if self.fail("readdir"): return 1
        C.memset(info, 0, C.sizeof(Info))
        for path in self.directories[directory.contents.handle]:
            if path in self.files:
                for index, char in enumerate(path.rsplit("/", 1)[1]):
                    info.contents.name[index] = ord(char)
                break
        return 0

    def fs_closedir(self, directory):
        self.directories.pop(directory.contents.handle)
        return 1 if self.fail("closedir") else 0

    def fs_unlink(self, path):
        path = path.decode()
        path = next((name for name in self.files if name.casefold() == path.casefold()), path)
        if self.fail("unlink", path): return 1
        return 0 if self.files.pop(path, None) is not None else 4

    def report(self, sequence, core=True):
        self.lib.capture(sequence, 1, 1)
        return C.string_at(self.lib.blob(core), 512 if core else 2048)

    @staticmethod
    def path(sequence, extension="core"):
        return f"{DIRECTORY}/moonshine_crash_{sequence:08X}.{extension}"

    def seed(self, sequences):
        for sequence in sequences:
            self.files[self.path(sequence)] = self.report(sequence)
            self.files[self.path(sequence, "bin")] = self.report(sequence, False)
            self.files[self.path(sequence, "txt")] = f"report {sequence}".encode()
        return self.lib.boot()

    def test_keeps_sixteen_reports_and_matching_files(self):
        self.assertEqual(self.seed(range(1, 17)), 17)
        self.lib.capture(17, 1, 1)
        self.lib.service()
        self.assertEqual(self.lib.ackStatus(), 3)
        self.assertEqual(set(self.files), {self.path(n, ext)
            for n in range(2, 18) for ext in ("core", "bin", "txt")})
        self.assertEqual(self.lib.boot(), 18)

    def test_every_binary_write_failure_preserves_all_previous_reports(self):
        for operation in ("open", "write", "short-write", "sync", "close",
                          "read", "short-read", "corrupt-read"):
            for extension in ("core", "bin", "txt"):
                if extension == "txt" and "read" in operation: continue
                with self.subTest(operation=operation, extension=extension):
                    self.files.clear()
                    self.failure = None
                    self.seed(range(1, 17))
                    previous = dict(self.files)
                    self.failure = operation, self.path(17, extension)
                    self.lib.capture(17, 1, 1)
                    self.lib.service()
                    for path, content in previous.items():
                        self.assertEqual(self.files.get(path), content)
                    self.assertNotEqual(self.lib.ackStatus(), 3)

    def test_failed_write_retries_same_generation_then_retires_oldest(self):
        self.seed(range(1, 17))
        self.failure = "short-write", self.path(17, "bin")
        self.lib.capture(17, 1, 1)
        self.lib.service()
        self.assertIn(self.path(1), self.files)
        self.failure = None
        self.lib.service()
        self.assertEqual(self.lib.ackStatus(), 3)
        self.assertNotIn(self.path(1), self.files)
        self.assertEqual(len(self.files), 48)

    def test_legacy_files_survive_and_seed_the_next_generation(self):
        for ext in ("core", "bin"):
            self.files[f"{DIRECTORY}/moonshine_crash_b.{ext}"] = self.report(90, ext == "core")
        legacy = dict(self.files)
        self.assertEqual(self.seed(range(1, 17)), 91)
        self.lib.capture(91, 1, 1)
        self.lib.service()
        for path, content in legacy.items(): self.assertEqual(self.files[path], content)

    def test_partial_names_and_text_only_files_are_not_reused_after_reboot(self):
        self.seed([2, 4])
        self.files[self.path(7)] = b"partial"
        self.files[self.path(9, "txt")] = b"text only"
        self.assertEqual(self.lib.boot(), 10)
        self.lib.capture(10, 1, 1)
        self.lib.service()
        self.assertEqual(self.files[self.path(7)], b"partial")

    def test_sequence_wrap_keeps_newest_sixteen(self):
        self.seed(range(0xFFFFFFF0, 0x100000000))
        self.assertEqual(self.lib.boot(), 1)
        self.lib.capture(1, 1, 1)
        self.lib.service()
        self.assertNotIn(self.path(0xFFFFFFF0), self.files)
        self.assertIn(self.path(1), self.files)
        self.assertEqual(self.lib.boot(), 2)

    def test_only_core_is_still_a_valid_history_report(self):
        self.seed(range(1, 17))
        self.lib.capture(17, 1, 0)
        self.lib.service()
        self.assertEqual(self.lib.ackStatus(), 5)
        self.assertIn(self.path(17), self.files)
        self.assertNotIn(self.path(1), self.files)

    def test_full_capture_can_arrive_after_core_without_new_history_entry(self):
        self.seed(range(1, 17))
        self.lib.capture(17, 1, 0)
        self.lib.service()
        self.lib.capture(17, 1, 1)
        self.lib.service()
        self.assertEqual(self.lib.ackStatus(), 3)
        self.assertEqual(len(self.files), 48)
        self.assertIn(b"Moonshine crash report", self.files[self.path(17, "txt")])

    def test_unreadable_directory_and_file_in_its_place_disable_writing(self):
        for operation in ("opendir", "readdir", "closedir"):
            self.failure = operation, ""
            self.lib.boot()
            self.assertFalse(self.lib.enabled())
            self.assertEqual(self.lib.ackStatus(), 1)
        self.failure = None
        self.folders.remove(DIRECTORY)
        self.files[DIRECTORY] = b"user file"
        self.lib.boot()
        self.assertFalse(self.lib.enabled())
        self.assertEqual(self.files[DIRECTORY], b"user file")

    def test_cleanup_failure_is_safe_and_retried_after_next_success(self):
        self.seed(range(1, 17))
        self.failure = "unlink", ""
        self.lib.capture(17, 1, 1)
        self.lib.service()
        self.assertEqual(len(self.files), 51)
        self.failure = None
        self.assertEqual(self.lib.boot(), 18)
        self.lib.capture(18, 1, 1)
        self.lib.service()
        self.assertEqual(len(self.files), 48)

    def test_corrupt_or_mismatched_files_do_not_count_toward_retention(self):
        self.seed(range(1, 17))
        self.files[self.path(20)] = b"truncated"
        self.files[self.path(21)] = self.report(19)
        self.files[f"{DIRECTORY}/keep_me.core"] = b"unrelated"
        self.assertEqual(self.lib.boot(), 22)
        self.lib.capture(22, 1, 1)
        self.lib.service()
        self.assertNotIn(self.path(1), self.files)
        for number in range(2, 17): self.assertIn(self.path(number), self.files)
        self.assertEqual(self.files[f"{DIRECTORY}/keep_me.core"], b"unrelated")

    def test_fat_case_aliases_reserve_the_same_generation(self):
        path = f"{DIRECTORY}/MOONSHINE_CRASH_000000ab.CORE"
        content = self.report(0xAB)
        self.files[path] = content
        self.assertEqual(self.lib.boot(), 0xAC)
        self.lib.capture(0xAC, 1, 1)
        self.lib.service()
        self.assertEqual(self.files[path], content)


if __name__ == "__main__":
    unittest.main()
