"""Exercise practice page actions and inline binding without game input leaks."""

import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class PracticeMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        text = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        cls.ids = re.findall(r"X\((SETTING_\w+),", (ROOT / "include/susamune/settings_list.h").read_text())
        text = text[text.index("class PracticeControlsTab final"):]
        methods = "\n".join(function(text, signature).replace(" override", "")
                            for signature in ("void focus() override",
                                "bool grabsInput() const override",
                                "bool favoriteHint() const override",
                                "void update(Menu *menu, TMarioGamePad *pad) override",
                                "static SettingId cameraSetting(int row)", "int rowCount() const", "BindId selectedBind() const"))
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        shim = r'''
#include "susamune/binds_list.h"
#include "susamune/settings_list.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
#define ID(name,key) name,
enum BindId { SUSAMUNE_BIND_LIST(ID) BIND_COUNT };
enum SettingId { SUSAMUNE_SETTING_LIST(ID) };
#undef ID
struct JUTGamePad {enum{A=0x100,B=0x200,X=0x400};
    struct Status{u16 mButton;};static Status mPadStatus[1];};
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad {enum{CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8};u32 nav;};
static int action,events,closeCount,fromMenu,bindTarget,settingDirection;
void hit(int id){action=id;++events;}
struct Menu {u32 navigationInput(TMarioGamePad *p){return p->nav;}
    void hide(){++closeCount;}void toast(const char*){}};
struct Binds {bool rec;bool recording(){return rec;}
    void beginRecord(BindId id){rec=true;bindTarget=id;}
    void cancelRecord(){rec=false;}}gBinds;
static bool favoriteFlags[256];
struct Settings {
    void cycle(int id,int d){settingDirection=d;hit(1000+id);}
    void toggleFavorite(int id){favoriteFlags[id]=!favoriteFlags[id];hit(2000+id);}
    bool favorite(int id){return favoriteFlags[id];}
}gSettings;
int wrap(int value,int count){return (value+count)%count;}
namespace PracticeSession {
bool requestPauseToggle(bool menu){fromMenu=menu;hit(1);return true;}
bool requestStep(bool menu){fromMenu=menu;hit(2);return true;}
bool requestFreeCameraToggle(){hit(5);return true;}
void recenterCamera(){hit(6);}
bool requestRecord(){hit(7);return true;}
bool requestPlayback(){hit(8);return true;}
bool requestContinue(){hit(10);return true;}
void requestStop(){hit(9);}
const char *status(){return "status";}
}
'''
        body = r'''
class PracticeControlsTab {
public:
PracticeControlsTab(int):mSel(0),mBinding(false){focus();}
METHODS
u8 mSel;bool mBinding;RawPromptInput mInput;
};
static void reset(){action=events=closeCount=fromMenu=settingDirection=0;
    bindTarget=-1;gBinds.rec=false;JUTGamePad::mPadStatus[0].mButton=0;
    for(unsigned i=0;i<256;++i)favoriteFlags[i]=false;}
extern "C" __declspec(dllexport) int route(int page,int row,int nav,int held,int *out){
    reset();PracticeControlsTab tab(page);tab.mSel=(u8)row;Menu menu;TMarioGamePad pad={(u32)nav};
    JUTGamePad::mPadStatus[0].mButton=(u16)held;tab.update(&menu,&pad);
    out[0]=action;out[1]=closeCount;out[2]=fromMenu;out[3]=tab.mSel;
    out[4]=bindTarget;out[5]=settingDirection;return events;
}
extern "C" __declspec(dllexport) int modal(int page,int row,int cancel,int *out){
    reset();PracticeControlsTab tab(page);tab.mSel=(u8)row;Menu menu;TMarioGamePad pad={};
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::X;tab.update(&menu,&pad);
    out[0]=tab.grabsInput();out[1]=bindTarget;
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;
    for(int i=0;i<10;++i)tab.update(&menu,&pad);
    if(cancel)pad.nav=TMarioGamePad::CSTICK_RIGHT;
    else gBinds.rec=false;
    tab.update(&menu,&pad);pad.nav=0;tab.update(&menu,&pad);
    out[2]=events;out[3]=tab.mSel;out[4]=tab.grabsInput();
    JUTGamePad::mPadStatus[0].mButton=0;tab.update(&menu,&pad);
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;tab.update(&menu,&pad);
    out[5]=action;return events;
}
extern "C" __declspec(dllexport) int entry(int page){
    reset();JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;
    PracticeControlsTab tab(page);Menu menu;TMarioGamePad pad={};
    for(int i=0;i<10;++i)tab.update(&menu,&pad);
    JUTGamePad::mPadStatus[0].mButton=0;tab.update(&menu,&pad);
    return events;
}
extern "C" __declspec(dllexport) int fourthButton(int button,int *out){
    reset();PracticeControlsTab tab(0);tab.mSel=1;Menu menu;TMarioGamePad pad={};
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::X;tab.update(&menu,&pad);
    JUTGamePad::mPadStatus[0].mButton=0x260;tab.update(&menu,&pad);
    gBinds.rec=false;
    JUTGamePad::mPadStatus[0].mButton=(u16)(0x260|button);
    out[0]=tab.grabsInput();tab.update(&menu,&pad);
    out[1]=tab.grabsInput();out[2]=events;out[3]=gBinds.recording();
    return closeCount;
}
'''.replace("METHODS", methods)
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        file = Path(cls.folder.name) / "practice_menu.cpp"
        file.write_text(shim + raw + body, encoding="ascii")
        dll = file.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(file), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def route(self, page, row, nav=0, held=0x100):
        out = (C.c_int * 6)()
        events = self.lib.route(page, row, nav, held, out)
        return events, list(out)

    def test_each_page_reaches_its_own_actions(self):
        for page, row, action, closes, from_menu in (
                (1, 0, 5, 1, 0), (1, 1, 1, 1, 1), (1, 7, 6, 0, 0)):
            self.assertEqual(self.route(page, row),
                             (1, [action, closes, from_menu, row, -1, 0]))

    def test_held_entry_press_does_not_pause_enable_camera_or_record(self):
        for page in (1,):
            self.assertEqual(self.lib.entry(page), 0)

    def test_inline_binding_never_activates_selected_action(self):
        for page, row, action in ((1, 1, 1), (1, 0, 5)):
            for cancel in (0, 1):
                out = (C.c_int * 6)()
                self.assertEqual(self.lib.modal(page, row, cancel, out), 1)
                self.assertEqual(out[0], 1)
                self.assertGreaterEqual(out[1], 0)
                self.assertEqual(list(out)[2:], [0, row, 0, action])

    def test_speed_and_direction_adjust_both_ways_without_closing(self):
        for row in (2, 3, 4, 5, 6):
            for nav, direction in ((4, -1), (8, 1)):
                events, out = self.route(1, row, nav, 0)
                self.assertEqual(events, 1)
                self.assertGreater(out[0], 1000)
                self.assertEqual(out[1:], [0, 0, row, -1, direction])

    def test_x_shines_exact_camera_setting_without_adjusting_rebinding_or_closing(self):
        settings = ("SETTING_FREE_CAMERA_SPEED", "SETTING_FREE_CAMERA_STRAFE_REVERSE",
                    "SETTING_FREE_CAMERA_SENSITIVITY", "SETTING_FREE_CAMERA_HIDE_HUD",
                    "SETTING_FREE_CAMERA_SMOOTHING")
        for row, setting in enumerate(settings, 2):
            with self.subTest(row=row):
                self.assertEqual(self.route(1, row, held=0x400),
                                 (1, [2000 + self.ids.index(setting), 0, 0, row, -1, 0]))
        for row in (0, 1):
            events, out = self.route(1, row, held=0x400)
            self.assertEqual(events, 0)
            self.assertGreaterEqual(out[4], 0)
            self.assertEqual(out[0:4], [0, 0, 0, row])

    def test_fourth_bind_button_cannot_step_rebind_or_switch_outer_tabs(self):
        for button in (0x100, 0x400):
            out = (C.c_int * 4)()
            self.assertEqual(self.lib.fourthButton(button, out), 0)
            self.assertEqual(list(out), [1, 0, 0, 0])

    def test_navigation_stays_within_each_page(self):
        for page, last in ((1, 7),):
            self.assertEqual(self.route(page, 0, 1, 0)[1][3], last)
            self.assertEqual(self.route(page, last, 2, 0)[1][3], 0)


if __name__ == "__main__":
    unittest.main()
