"""Execute production Creation navigation and editor-routing methods."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_nested_menu_focus import function

ROOT = Path(__file__).resolve().parents[1]


class CreationMenuRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        src = (ROOT / "src/menu.cpp").read_text(encoding="utf-8")
        creation = src[src.index("class CreationTab final"):]
        methods = "\n".join(function(creation, signature).replace(" override", "")
                            for signature in ("void focus() override", "bool back() override",
                                "void update(Menu *menu, TMarioGamePad *pad) override",
                                "int pageFirst() const", "int pageEnd() const",
                                "void moveSelection(", "void activate(",
                                "static int inputRow(", "static int metadataRow(",
                                "static int extraRow("))
        rows = function(creation, "enum Row") + ";"
        raw = (ROOT / "include/susamune/raw_prompt_input.hxx").read_text()
        raw = raw[raw.index("class RawPromptInput"):raw.index("#endif")]
        movement = function(src, "const u8 kDisplayMovementSettings[]") + ";"
        movement_method = function(src, "bool hasMovementEditors() const")
        shim = r'''
#include "susamune/settings_list.h"
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
#define ID(name,key) name,
enum SettingId { SUSAMUNE_SETTING_LIST(ID) SETTING_BUTTSLIDE_DISPLAY };
#undef ID
enum { SUSAMUNE_CREATION_TIMER_BG=1,SUSAMUNE_CREATION_TIMER_LABEL=2 };
#define SUSAMUNE_GLYPH_SLASH "/"
struct JUTGamePad { enum {A=0x100,B=0x200};struct Status{u16 mButton;};static Status mPadStatus[1]; };
JUTGamePad::Status JUTGamePad::mPadStatus[1];
struct TMarioGamePad { enum{CSTICK_UP=1,CSTICK_DOWN=2,CSTICK_LEFT=4,CSTICK_RIGHT=8};u32 nav; };
struct Menu { u32 navigationInput(TMarioGamePad *pad) {return pad->nav;} };
int wrap(int value,int count) {return (value+count)%count;}
static int owner,row,direction,actions;
void hit(int o,int r,int d=1) {owner=o;row=r;direction=d;++actions;}
struct Editor {
    bool active=false;int id;
    bool editing() {return active;}
    void updateEditor(TMarioGamePad*) {}
    void beginEditor() {hit(id,99);}
    void toggleLeadingZero() {hit(id,98);}
    void adjustMenuRow(int r,int d) {hit(id,r,d);}
};
struct InputDisplay:Editor {enum{MENU_ROW_COUNT=6};};
struct MetadataDisplay:Editor {enum{FIELD_COUNT=11};static constexpr int menuRowCount(){return 20;} };
struct CreationExtras:Editor {
    enum{MENU_ROW_COUNT=24};
    void beginNativeTimerEditor(){hit(4,100);}
    void beginTimerCharacterEditor(){hit(4,101);}
    void beginColorEditor(int c,int,const char*){hit(4,102+c);}
    void toggleTimerLabel(){hit(4,105);}
    void beginHealthEditor(bool air){hit(4,air?107:106);}
    void beginWallkickEditor(){hit(4,108);}
    void beginRolloutEditor(){hit(4,109);}
    void beginDustEditor(){hit(4,110);}
    void beginPracticeDisplayEditor(unsigned display){hit(4,113+display);}
    void beginSavestateFeedbackEditor(){hit(4,111);}
    void beginRecentIlEditor(){hit(4,112);}
};
Editor gQftDisplay;InputDisplay gInputDisplay;MetadataDisplay gMetadataDisplay;CreationExtras gCreationExtras;
struct Settings{void cycle(int id,int d){hit(5,id,d);}}gSettings;
void reset() {owner=row=direction=actions=0;JUTGamePad::mPadStatus[0].mButton=0;
    gQftDisplay.id=1;gInputDisplay.id=2;gMetadataDisplay.id=3;gCreationExtras.id=4;}
'''
        more = r'''
class CreationTab {
public:
    CreationTab():mSel(0),mPage(0){mInput.begin(JUTGamePad::A);}
ROWS
METHODS
    u8 mSel,mPage;RawPromptInput mInput;
};
MOVEMENT
class CategorySettingsTab {
public:
    bool display;int mMode;struct Page{const u8 *ids;}page;
    bool isDisplay()const{return display;}
    const Page&currentPage()const{return page;}
MOVEMENT_METHOD
};
extern "C" __declspec(dllexport) int range(int page,int end) {
    CreationTab tab;tab.mPage=page+1;return end?tab.pageEnd():tab.pageFirst();
}
extern "C" __declspec(dllexport) int route(int page,int local,int nav,int held,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};
    tab.mPage=page+1;tab.mSel=tab.pageFirst()+local;pad.nav=nav;
    JUTGamePad::mPadStatus[0].mButton=(u16)held;tab.update(&menu,&pad);
    out[0]=owner;out[1]=row;out[2]=direction;out[3]=tab.mSel-tab.pageFirst();return actions;
}
extern "C" __declspec(dllexport) int entry(int page,int *out) {
    reset();CreationTab tab;Menu menu;TMarioGamePad pad={};tab.mSel=page;
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;tab.update(&menu,&pad);
    for(int i=0;i<20;i++)tab.update(&menu,&pad);
    out[0]=actions;out[1]=tab.mPage;
    JUTGamePad::mPadStatus[0].mButton=0;tab.update(&menu,&pad);
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::A;tab.update(&menu,&pad);
    out[2]=actions;out[3]=owner;out[4]=row;
    JUTGamePad::mPadStatus[0].mButton=JUTGamePad::B;
    bool back=tab.back();out[5]=tab.mPage;out[6]=tab.mSel;
    for(int i=0;i<20;i++)tab.update(&menu,&pad);
    out[7]=actions;return back;
}
extern "C" __declspec(dllexport) int movementPage(int display,int mode,int same) {
    static const u8 other[]={0};CategorySettingsTab tab;
    tab.display=display!=0;tab.mMode=mode;tab.page.ids=same?kDisplayMovementSettings:other;
    return tab.hasMovementEditors();
}
'''.replace("MOVEMENT_METHOD", movement_method).replace("MOVEMENT", movement)
        more = more.replace("ROWS", rows).replace("METHODS", methods)
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        file = Path(cls.folder.name) / "creation.cpp"
        file.write_text(shim + raw + more, encoding="ascii")
        dll = file.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(file), "-o", str(dll)], check=True)
        cls.lib = C.CDLL(str(dll))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def route(self, page, local, nav=0, held=0x100):
        out = (C.c_int * 4)()
        count = self.lib.route(page, local, nav, held, out)
        return count, list(out)

    def test_page_ranges_include_every_new_row_and_no_headers(self):
        self.assertEqual([self.lib.range(p, 1) - self.lib.range(p, 0) for p in range(7)],
                         [7, 7, 20, 9, 9, 8, 5])

    def test_health_air_and_shifted_custom_notification_editors(self):
        for page, local, row in ((3, 7, 106), (3, 8, 107), (4, 0, 9),
                                  (4, 8, 17), (6, 0, 19), (6, 4, 23)):
            count, out = self.route(page, local)
            self.assertEqual((count, out[:3]), (1, [4, row, 1]))
        for local, row in enumerate((108, 113, 114, 115, 109, 110, 111, 112)):
            self.assertEqual(self.route(5, local)[1][:2], [4, row])

    def test_metadata_style_first_mapping_preserves_all_twenty_actions(self):
        expected = [14] + list(range(14)) + list(range(15, 20))
        for local, row in enumerate(expected):
            self.assertEqual(self.route(2, local)[1][:3], [3, row, 1])

    def test_new_metadata_geometry_has_bidirectional_controls_without_opening_editors(self):
        for local in range(16, 20):
            for nav, direction in ((4, -1), (8, 1)):
                self.assertEqual(self.route(2, local, nav, 0), (1, [3, local, direction, local]))
        for local in (0, 15):
            self.assertEqual(self.route(2, local, 4, 0)[0], 0)

    def test_navigation_wraps_within_each_group(self):
        for page in range(7):
            count = self.lib.range(page, 1) - self.lib.range(page, 0)
            self.assertEqual(self.route(page, 0, 1, 0)[1][3], count - 1)
            self.assertEqual(self.route(page, count - 1, 2, 0)[1][3], 0)

    def test_held_A_enters_group_only_and_back_keeps_selected_group(self):
        for page in range(7):
            out = (C.c_int * 8)()
            self.assertEqual(self.lib.entry(page, out), 1)
            self.assertEqual(list(out[:3]), [0, page + 1, 1])
            self.assertEqual(list(out[5:]), [0, page, 1])

    def test_movement_editors_follow_the_settings_list_after_page_reordering(self):
        for mode in range(1, 8):
            self.assertEqual(self.lib.movementPage(1, mode, 1), 1)
            self.assertEqual(self.lib.movementPage(1, mode, 0), 0)
            self.assertEqual(self.lib.movementPage(0, mode, 1), 0)
        self.assertEqual(self.lib.movementPage(1, 0, 1), 0)


if __name__ == "__main__":
    unittest.main()
