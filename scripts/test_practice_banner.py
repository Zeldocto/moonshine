"""Exercise production TAS overlay visibility without changing playback state."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class PracticeBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / 'banner.cpp'
        source.write_text(r'''
typedef unsigned u32; typedef int s32;
extern "C" int _fltused=0;
static bool sPausePending,sPaused,sFreeCamera,sRecord,sReplay,sLoadKind,sStartRelease;
static u32 sCount=300,sCursor=290,kMaxFrames=4096;
static s32 mismatch=-1;
enum {SETTING_TAS_BANNER};
struct {int value;int get(int){return value;}}gSettings;
namespace JUtility {struct TColor {TColor(int,int,int,int){}};}
static const char *formats[3];static int boxes,texts,boxWidth,boxHeight;
int snprintf(char *out,unsigned long long,const char *format,...) {
    *(const char**)out=format;return 0;
}
struct Menu {
 bool visible=false,toast=false;
 bool shown(){return visible;}bool hasToast(){return toast;}
 void fillBox(int,int,int w,int h,JUtility::TColor){++boxes;boxWidth=w;boxHeight=h;}
 void drawText(const char*t,int,int,int,int,JUtility::TColor){
   formats[texts++]=texts==0?*(const char**)t:t;
 }
};
s32 desyncFrame(){return mismatch;}float cameraSpeedScale(){return 1;}
bool paused(){return sPaused;}bool normalStage(){return true;}
''' + function_source(ROOT/'src/practice_session.cpp', 'void draw(Menu *menu)') + r'''
extern "C" __declspec(dllexport) int render(int flags,int banner,int warning,int *out) {
 sRecord=flags&1;sReplay=flags&2;sFreeCamera=flags&4;sPausePending=flags&8;sLoadKind=flags&16;
 gSettings.value=banner;mismatch=warning;boxes=texts=0;boxWidth=boxHeight=0;
 Menu menu;menu.visible=flags&32;menu.toast=flags&64;
 draw(flags&128?0:&menu);
 out[0]=boxes;out[1]=texts;out[2]=boxWidth;out[3]=boxHeight;
 return sCount==300&&sCursor==290&&mismatch==warning;
}
extern "C" __declspec(dllexport) const char *line(int i){return formats[i];}
''')
        dll = source.with_suffix('.dll')
        result = subprocess.run([str(ROOT/'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-shared','-nostdlib','-fuse-ld=lld','-Wl,/noentry','-O2','-std=c++17',
            str(source),'-o',str(dll)],capture_output=True,text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(dll))
        cls.lib.line.restype = C.c_char_p
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def render(self, flags, banner, warning=-1):
        out = (C.c_int*4)()
        self.assertEqual(self.lib.render(flags,banner,warning,out),1)
        return list(out)

    def test_off_hides_record_replay_and_loading_progress(self):
        for flags in (1,2,16):
            self.assertEqual(self.render(flags,0),[0,0,0,0])
            self.assertEqual(self.render(flags,1),[1,2,556,40])

    def test_desync_keeps_only_a_small_warning_when_banner_is_off(self):
        self.assertEqual(self.render(2,0,290),[1,1,160,20])
        self.assertIn(b'DESYNC',self.lib.line(0))
        self.assertEqual(self.render(2,1,290),[1,2,556,40])
        self.assertIn(b'DESYNC',self.lib.line(0))
        self.assertEqual(self.render(0,0,290),[0,0,0,0])

    def test_camera_and_armed_pause_keep_their_own_help(self):
        for flags, text in ((4,b'CAMERA ON'),(5,b'CAMERA ON'),(8,b'FRAME ADVANCE ARMED')):
            self.assertEqual(self.render(flags,0),[1,2,556,40])
            self.assertIn(text,self.lib.line(0))

    def test_menu_toast_and_missing_menu_suppress_all_overlay_drawing(self):
        for flags in (32,64,128):
            self.assertEqual(self.render(flags|2,1,290),[0,0,0,0])


if __name__ == '__main__':
    unittest.main()
