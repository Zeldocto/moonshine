"""Exercise actual regional director admission for Intro Skip's file-select context."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class FileSelectDirectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory(prefix="moonshine-file-select-")
        cls.addClassCleanup(cls.folder.cleanup)
        source = ROOT / "src/retail_input.cpp"
        code = r'''
using u32=unsigned long long;
struct TMarDirector {}; struct TMovieDirector {};
struct TGameSequence {enum {AREA_OPTION=15};unsigned mAreaID;};
struct TApplication {
 enum {CONTEXT_GAME_INTRO=4,CONTEXT_DIRECT_STAGE=5,CONTEXT_DIRECT_MOVIE=6};
 unsigned mContext;TGameSequence mCurrentScene;void*mDirector;
} gpApplication;
unsigned region;
#define SUSAMUNE_MEM1_ADDR(j,u,p) (region==0?(j):region==1?(u):(p))
''' + function_source(source, "u32 directorType(") + "\nnamespace RetailInput {\n"
        code += function_source(source, "TMarDirector *stageDirector()")
        code += function_source(source, "TMovieDirector *movieDirector()")
        code += r'''
}
extern "C" __declspec(dllexport) unsigned admit(unsigned r,unsigned context,unsigned area,u32 address) {
 region=r;gpApplication.mContext=context;gpApplication.mCurrentScene.mAreaID=area;
 gpApplication.mDirector=reinterpret_cast<void*>(address);
 return (RetailInput::stageDirector()?1:0)|(RetailInput::movieDirector()?2:0);
}
'''
        cpp = Path(cls.folder.name) / "file_select.cpp"
        cpp.write_text(code, encoding="ascii")
        dll = cpp.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(cpp), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.admit.argtypes = [C.c_uint, C.c_uint, C.c_uint, C.c_uint64]
        kernel = C.windll.kernel32
        kernel.VirtualAlloc.restype = C.c_void_p
        kernel.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, C.c_uint, C.c_uint]
        cls.memory = kernel.VirtualAlloc(C.c_void_p(0x81000000), 0x10000, 0x3000, 4)
        if cls.memory != 0x81000000:
            raise unittest.SkipTest("Test MEM1 address unavailable")
        cls.addClassCleanup(lambda: kernel.VirtualFree(C.c_void_p(cls.memory), 0, 0x8000))

    def set_type(self, vtable):
        # Host u32 is widened solely to retain the actual pointer range checks.
        C.c_uint64.from_address(self.memory).value = vtable

    def test_intro_skip_file_select_accepts_exact_stage_type_in_every_region(self):
        for region, vtable in enumerate((0x803b3ca0, 0x803df0c8, 0x803d68a8)):
            self.set_type(vtable)
            self.assertEqual(self.lib.admit(region, 4, 15, self.memory), 1)
            self.assertEqual(self.lib.admit(region, 5, 15, self.memory), 1)

    def test_intro_exception_cannot_admit_movie_or_unrelated_directors(self):
        for region, movie in enumerate((0x803b48d8, 0x803dfa50, 0x803d73b8)):
            self.set_type(movie)
            self.assertEqual(self.lib.admit(region, 4, 15, self.memory), 0)
            self.assertEqual(self.lib.admit(region, 5, 1, self.memory), 2)
            self.assertEqual(self.lib.admit(region, 6, 15, self.memory), 2)
        self.set_type(0x803d6000)
        self.assertEqual(self.lib.admit(2, 4, 15, self.memory), 0)

    def test_unrelated_contexts_areas_and_invalid_director_addresses_stay_blocked(self):
        self.set_type(0x803d68a8)
        for context in (0, 1, 2, 3, 7, 8, 9):
            self.assertEqual(self.lib.admit(2, context, 15, self.memory), 0)
        for area in (0, 1, 13, 255):
            self.assertEqual(self.lib.admit(2, 4, area, self.memory), 0)
        for address in (0, 0x7ffffffc, 0x81000001, 0x817ffd04, 0x181000000):
            self.assertEqual(self.lib.admit(2, 4, 15, address), 0)


if __name__ == "__main__":
    unittest.main()
