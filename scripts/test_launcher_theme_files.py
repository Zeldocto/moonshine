"""Exercise the sole root theme path for both assets and both launcher devices."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class LauncherThemeFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-theme-files-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / "paths.c"
        production = (ROOT / "launcher/loader/source/SusamuneThemeFiles.c").read_text()
        code = r'''
typedef __SIZE_TYPE__ size_t;typedef int FRESULT;typedef struct {unsigned fsize;unsigned char fattrib;}FILINFO;
#define NULL ((void*)0)
#define FR_INVALID_NAME 6
#define FR_OK 0
#define FR_NO_FILE 4
#define FR_NO_PATH 5
#define FR_EXIST 8
#define AM_DIR 16
int strcmp(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a-*b;}
int snprintf(char*out,size_t n,const char*fmt,...){
 unsigned written=0;__builtin_va_list ap;__builtin_va_start(ap,fmt);
 while(*fmt){const char*s=fmt;unsigned count=1;if(*fmt=='%'&&fmt[1]=='s'){s=__builtin_va_arg(ap,const char*);fmt+=2;count=0;while(s[count])count++;}else fmt++;
 for(unsigned i=0;i<count;i++){if(written+1<n)out[written]=s[i];written++;}}
 __builtin_va_end(ap);if(n)out[written<n?written:n-1]=0;return written;
}
static int markerReady=1,status,calls,ensureMode,attributes,secondStatus,secondAttributes,mkdirStatus,mkdirCalls;
static char recorded[512],created[512];
int f_stat_char(const char*path,FILINFO*info){unsigned i=0;do{recorded[i]=path[i];}while(path[i++]);calls++;info->fsize=123;
 if(!ensureMode){const char*s=path;while(*s)s++;if(s-path>=10&&strcmp(s-10,".layout-v1")==0)return markerReady?0:4;}
 info->fattrib=ensureMode&&calls>1?secondAttributes:attributes;return ensureMode&&calls>1?secondStatus:status;}
int f_mkdir_char(const char*path){unsigned i=0;do{created[i]=path[i];}while(path[i++]);mkdirCalls++;return mkdirStatus;}
'''
        code += (ROOT / "include/susamune/data_paths.h").read_text()
        code += function(production, "SusamuneThemeFindFile")
        code += function(production, "SusamuneThemeEnsureDirectory")
        code += r'''
__declspec(dllexport) int locate(const char*device,const char*leaf,unsigned capacity,int error){
 static char out[512];FILINFO info;ensureMode=0;calls=0;status=error;recorded[0]=0;
 return SusamuneThemeFindFile(out,capacity,device,leaf,&info);
}
__declspec(dllexport) int ensure(const char*device,int initial,int attr,int createResult,int after,int afterAttr){
 ensureMode=1;status=initial;attributes=attr;secondStatus=after;secondAttributes=afterAttr;mkdirStatus=createResult;
 calls=mkdirCalls=0;recorded[0]=created[0]=0;return SusamuneThemeEnsureDirectory(device);
}
__declspec(dllexport) void migrated(int ready){markerReady=ready;}
__declspec(dllexport) int creations(void){return mkdirCalls;}
__declspec(dllexport) const char*createdPath(void){return created;}
__declspec(dllexport) const char*path(void){return recorded;}
__declspec(dllexport) int count(void){return calls;}
'''
        source.write_text(code, encoding="ascii")
        library = source.with_suffix(".dll")
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                                 "-nostdlib", "-fno-builtin", "-O2", "-fuse-ld=lld", "-Wl,/noentry",
                                 str(source), "-o", str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.locate.argtypes = [C.c_char_p, C.c_char_p, C.c_uint, C.c_int]
        cls.lib.path.restype = C.c_char_p
        cls.lib.createdPath.restype = C.c_char_p
        cls.lib.ensure.argtypes = [C.c_char_p] + [C.c_int] * 5

    def test_both_assets_read_exact_root_on_launcher_device(self):
        for device in (b"sd", b"usb"):
            for leaf in (b"background.png", b"bgm.mp3"):
                with self.subTest(device=device, leaf=leaf):
                    self.assertEqual(self.lib.locate(device, leaf, 512, 0), 0)
                    self.assertEqual(self.lib.path(), device + b":/Moonshine data/theme/" + leaf)
                    self.assertEqual(self.lib.count(), 1)

    def test_missing_or_broken_root_asset_never_searches_old_folder(self):
        for error in (1, 4, 5, 7):
            self.assertEqual(self.lib.locate(b"sd", b"bgm.mp3", 512, error), error)
            self.assertEqual(self.lib.path(), b"sd:/Moonshine data/.layout-v1" if error in (4, 5) else b"sd:/Moonshine data/theme/bgm.mp3")
            self.assertEqual(self.lib.count(), 2 if error in (4, 5) else 1)

    def test_invalid_device_leaf_and_short_buffer_do_not_access_storage(self):
        for device, leaf, capacity in ((None, b"bgm.mp3", 512), (b"usb:/", b"bgm.mp3", 512),
                (b"sd", None, 512), (b"sd", b"../bgm.mp3", 512), (b"sd", b"theme.mp3", 512),
                (b"sd", b"bgm.mp3", 0), (b"sd", b"bgm.mp3", 26)):
            self.assertEqual(self.lib.locate(device, leaf, capacity, 0), 6)
            self.assertEqual(self.lib.count(), 0)

    def test_existing_theme_directory_needs_no_write(self):
        for device in (b"sd", b"usb"):
            self.assertEqual(self.lib.ensure(device, 0, 16, 7, 0, 16), 0)
            self.assertEqual(self.lib.path(), device + b":/Moonshine data/theme")
            self.assertEqual(self.lib.count(), 1)
            self.assertEqual(self.lib.creations(), 0)

    def test_missing_theme_directory_is_created_at_root(self):
        for device in (b"sd", b"usb"):
            for missing in (4, 5):
                self.assertEqual(self.lib.ensure(device, missing, 0, 0, 0, 16), 0)
                self.assertEqual(self.lib.createdPath(), device + b":/Moonshine data/theme")
                self.assertEqual(self.lib.count(), 1)
                self.assertEqual(self.lib.creations(), 1)

    def test_optional_creation_propagates_errors_and_never_replaces_a_file(self):
        self.assertEqual(self.lib.ensure(b"sd", 0, 0, 0, 0, 16), 8)
        self.assertEqual(self.lib.creations(), 0)
        for error in (1, 3, 7, 10, 13):
            self.assertEqual(self.lib.ensure(b"sd", error, 0, 0, 0, 16), error)
            self.assertEqual(self.lib.creations(), 0)
            self.assertEqual(self.lib.ensure(b"sd", 4, 0, error, 0, 16), error)
            self.assertEqual(self.lib.creations(), 1)

    def test_directory_appearing_during_create_must_be_a_directory(self):
        self.assertEqual(self.lib.ensure(b"sd", 4, 0, 8, 0, 16), 0)
        self.assertEqual(self.lib.count(), 2)
        self.assertEqual(self.lib.ensure(b"sd", 4, 0, 8, 0, 0), 8)
        self.assertEqual(self.lib.ensure(b"sd", 4, 0, 8, 1, 0), 1)

    def test_first_boot_can_read_old_theme_before_migration_without_creating_it(self):
        self.lib.migrated(0)
        try:
            self.assertEqual(self.lib.locate(b"sd", b"background.png", 512, 4), 4)
            self.assertEqual(self.lib.path(), b"sd:/Moonshine_Theme/background.png")
            self.assertEqual(self.lib.count(), 3)
            self.assertEqual(self.lib.locate(b"usb", b"bgm.mp3", 512, 0), 0)
            self.assertEqual(self.lib.path(), b"usb:/Moonshine data/theme/bgm.mp3")
            self.assertEqual(self.lib.count(), 1)
        finally:
            self.lib.migrated(1)

    def test_invalid_creation_device_never_touches_storage(self):
        for device in (None, b"", b"SD", b"usb:/", b"../sd"):
            self.assertEqual(self.lib.ensure(device, 4, 0, 0, 0, 16), 6)
            self.assertEqual(self.lib.count(), 0)
            self.assertEqual(self.lib.creations(), 0)

    def test_folder_creation_only_follows_final_mount_and_cannot_block_boot(self):
        main = (ROOT / "launcher/loader/source/main.c").read_text()
        preload = function(main, "PreloadLauncherTheme")
        self.assertNotIn("SusamuneThemeEnsureDirectory", preload)
        self.assertEqual(main.count("SusamuneThemeEnsureDirectory("), 1)
        mounted = main.index('if (!devices[DEV_SD] && !devices[DEV_USB])')
        ensure = main.index('themeDirectory = SusamuneThemeEnsureDirectory(')
        load = main.index('if (!themeLoaded)', ensure)
        self.assertLess(mounted, ensure)
        self.assertLess(ensure, load)
        body = main[ensure:load]
        self.assertNotIn('ExitToLoader', body)
        self.assertNotIn('usleep', body)
        self.assertNotIn('ShowMessageScreen', body)

    def test_background_and_music_share_lookup_without_folder_writes_or_duplicate_stat(self):
        for name in ("SusamuneTheme.c", "SusamuneMusic.c"):
            source = (ROOT / "launcher/loader/source" / name).read_text()
            self.assertEqual(source.count("SusamuneThemeFindFile("), 1)
            self.assertNotIn("f_stat_char(", source)
            self.assertNotIn("f_mkdir_char(", source)
            self.assertNotIn("/apps/", source)
            self.assertNotIn("theme/", source)


if __name__ == "__main__":
    unittest.main()
