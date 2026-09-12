"""Exercise HSL conversion and the production Creation editor input path."""

import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class CreationHslTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-hsl-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        (work / "Dolphin").mkdir()
        (work / "Dolphin/types.h").write_text(
            "typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;",
            encoding="ascii")
        creation = (ROOT / "src/creation.cpp").read_text()
        color = (ROOT / "src/creation_color.cpp").read_text()
        layout = (ROOT / "src/layout_editor.cpp").read_text()
        code = r'''
#define private public
#include "susamune/creation.hxx"
#include "susamune/creation_color.hxx"
#undef private
#define API extern "C" __declspec(dllexport)
extern "C" void *memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
struct TMarioGamePad {
 enum{A=1,B=2,X=4,Y=8,Z=16,START=32,L=64,R=128,DPAD_LEFT=256,DPAD_RIGHT=512,
 DPAD_UP=1024,DPAD_DOWN=2048,CSTICK_LEFT=4096,CSTICK_RIGHT=8192,CSTICK_UP=16384,CSTICK_DOWN=32768};
 struct{u32 mInput,mFrameInput,mRapidInput;}mButtons;
};
'''
        code += re.sub(r"^#include[^\n]*", "", color, flags=re.M)
        code += creation[creation.index("enum EditOption"):creation.index("inline int clampi")]
        code += function(creation, "clampi")
        code += "namespace LayoutEditor {" + function(layout, "updatePositionScale") + "}\n"
        code += "\n".join(function(creation, name) for name in (
            "textChannel", "adjustTextChannel", "resetOption", "CreationEditor::reset",
            "CreationEditor::begin", "CreationEditor::optionEnabled", "CreationEditor::moveOption",
            "CreationEditor::repeatInput", "CreationEditor::update"))
        code += r'''
CreationEditor editor;
CreationStyle style,defaults;
u16 custom;
const u8 white[1][3]={{255,255,255}};
API void begin(u8*rgb,u8*backup,unsigned count,const u8*background,int modes){
 editor.reset();style={91,72,100,217,background[0],background[1],background[2],127,100,255};
 defaults=style;custom=0;
 unsigned caps=CreationEditor::CAP_ALL;
 if(modes)caps|=CreationEditor::CAP_COLOR_MODE;
 if(modes==2)caps|=CreationEditor::CAP_RGB_ENABLES_CUSTOM;
 editor.begin(&style,(u8(*)[3])rgb,(u8(*)[3])backup,count,count,0,caps,modes?&custom:0);
}
API unsigned editing(){return editor.editing();}
API void target(unsigned slot){editor.selectTarget(slot);}
API unsigned adjust(unsigned option,int direction,unsigned fine){
 editor.mOption=(u8)option;TMarioGamePad pad={};
 pad.mButtons.mInput=pad.mButtons.mFrameInput=direction<0?TMarioGamePad::CSTICK_LEFT:TMarioGamePad::CSTICK_RIGHT;
 if(fine)pad.mButtons.mInput|=TMarioGamePad::Y;
 return editor.update(&pad,defaults,white);
}
API unsigned finish(unsigned keep){
 TMarioGamePad pad={};pad.mButtons.mRapidInput=keep?TMarioGamePad::A:TMarioGamePad::B;
 editor.update(&pad,defaults,white);pad.mButtons.mRapidInput=TMarioGamePad::A;
 return editor.update(&pad,defaults,white);
}
API void resetOptionAt(unsigned option){
 editor.mOption=(u8)option;TMarioGamePad pad={};pad.mButtons.mRapidInput=TMarioGamePad::Z;
 editor.update(&pad,defaults,white);pad.mButtons.mRapidInput=TMarioGamePad::A;
 editor.update(&pad,defaults,white);
}
API unsigned mode(){return custom;}
API unsigned value(unsigned slot,unsigned channel){return sHsl[slot].channel[channel];}
API unsigned background(unsigned channel){return (&style.bgR)[channel];}
API unsigned alpha(){return style.textA;}
API unsigned mixed(unsigned channel){u16 out;return !textChannel(editor.mTextRgb,editor.mTextSlots,editor.mTextTarget,channel,&out);}
API void fromRgb(const u8*rgb,u16*out){const auto hsl=CreationColor::fromRgb(rgb);for(int i=0;i<3;i++)out[i]=hsl.channel[i];}
API unsigned roundtripAllRgb(){
 for(unsigned r=0;r<256;r++)for(unsigned g=0;g<256;g++)for(unsigned b=0;b<256;b++){
  u8 rgb[3]={(u8)r,(u8)g,(u8)b},back[3];
  CreationColor::toRgb(CreationColor::fromRgb(rgb),back);
  if(rgb[0]!=back[0]||rgb[1]!=back[1]||rgb[2]!=back[2])return 1+(r<<16)+(g<<8)+b;
 }
 return 0;
}
'''
        source = work / "fixture.cpp"
        source.write_text(code, encoding="ascii")
        dll = work / "fixture.dll"
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(work), "-I", str(ROOT / "include"), str(source), "-o", str(dll)],
                       check=True)
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)

    def begin(self, colors, background=(0, 0, 0), modes=0):
        self.rgb = (C.c_ubyte * (len(colors) * 3))(*(c for rgb in colors for c in rgb))
        self.backup = (C.c_ubyte * len(self.rgb))()
        bg = (C.c_ubyte * 3)(*background)
        self.lib.begin(self.rgb, self.backup, len(colors), bg, modes)

    def rgb_at(self, slot):
        return tuple(self.rgb[slot * 3:slot * 3 + 3])

    def hsl(self, slot):
        return tuple(self.lib.value(slot, channel) for channel in range(3))

    def adjust(self, option, amount, fine=True):
        step = 1 if fine else 4
        for _ in range(abs(amount) // step):
            self.lib.adjust(option, 1 if amount > 0 else -1, fine)

    def test_every_rgb_color_roundtrips_without_quantization_loss(self):
        self.assertEqual(self.lib.roundtripAllRgb(), 0)

    def test_named_colors_and_neutral_endpoints(self):
        for rgb, expected in (((255, 0, 0), (0, 10000, 5000)),
                              ((0, 255, 0), (12000, 10000, 5000)),
                              ((0, 0, 255), (24000, 10000, 5000)),
                              ((255, 255, 0), (6000, 10000, 5000)),
                              ((0, 255, 255), (18000, 10000, 5000)),
                              ((255, 0, 255), (30000, 10000, 5000)),
                              ((0, 0, 0), (0, 0, 0)), ((255, 255, 255), (0, 0, 10000))):
            with self.subTest(rgb=rgb):
                out = (C.c_ushort * 3)()
                self.lib.fromRgb((C.c_ubyte * 3)(*rgb), out)
                self.assertEqual(tuple(out), expected)

    def test_enter_select_mode_and_opacity_leave_existing_rgb_exact(self):
        colors = [(i, (i * 17) % 256, 255 - i) for i in range(16)]
        self.begin(colors, (19, 71, 221), modes=1)
        original = bytes(self.rgb)
        self.assertEqual(bytes(self.backup), original)
        self.lib.target(7)
        self.lib.adjust(10, 1, 0)
        self.lib.adjust(3, -1, 1)
        self.assertEqual(bytes(self.rgb), original)
        self.assertEqual(self.lib.alpha(), 216)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (19, 71, 221))

    def test_hue_wrap_coarse_fine_and_saturation_lightness_limits(self):
        self.begin([(255, 0, 0)])
        self.adjust(0, -1)
        self.assertEqual(self.hsl(0)[0], 35900)
        self.adjust(0, 4, fine=False)
        self.assertEqual(self.hsl(0)[0], 300)
        self.adjust(1, 4, fine=False)
        self.assertEqual(self.hsl(0)[1], 10000)
        self.adjust(1, -200, fine=False)
        self.assertEqual(self.hsl(0)[1], 0)
        self.adjust(2, 200, fine=False)
        self.assertEqual(self.hsl(0)[2], 10000)
        self.assertEqual(self.rgb_at(0), (255, 255, 255))
        self.adjust(2, -200, fine=False)
        self.assertEqual(self.rgb_at(0), (0, 0, 0))

    def test_black_white_and_grey_retain_hue_across_target_changes(self):
        for option, amount in ((2, 50), (2, -50), (1, -100)):
            with self.subTest(option=option, amount=amount):
                self.begin([(255, 0, 0), (0, 255, 0)])
                self.lib.target(1)
                self.adjust(option, amount)
                self.adjust(0, 240, fine=False)
                self.lib.target(2)
                self.adjust(0, 60, fine=False)
                self.lib.target(1)
                self.adjust(option, -amount)
                self.assertEqual(self.rgb_at(0), (0, 0, 255))
                self.assertEqual(self.rgb_at(1), (0, 255, 255))

    def test_many_inverse_edits_do_not_accumulate_rounding(self):
        colors = [(21, 94, 203), (213, 87, 117)]
        self.begin(colors)
        before = bytes(self.rgb)
        for slot in (1, 2):
            self.lib.target(slot)
            self.adjust(0, 360, fine=False)
            for _ in range(100):
                self.adjust(1, -1)
                self.adjust(1, 1)
                self.adjust(2, -1)
                self.adjust(2, 1)
        self.assertEqual(bytes(self.rgb), before)

    def test_all_changes_one_component_preserving_other_components_and_modes(self):
        self.begin([(255, 0, 0), (20, 40, 60)], modes=2)
        original = [self.hsl(i) for i in range(2)]
        self.assertTrue(self.lib.mixed(0))
        self.lib.adjust(0, 1, 0)
        self.assertEqual(self.lib.mode(), 3)
        for i in range(2):
            self.assertEqual(self.hsl(i), (400, original[i][1], original[i][2]))
        self.assertFalse(self.lib.mixed(0))
        self.assertTrue(self.lib.mixed(1))
        self.lib.target(2)
        self.lib.adjust(10, -1, 0)
        self.assertEqual(self.lib.mode(), 1)

    def test_background_has_independent_latent_hue_and_reset(self):
        self.begin([(17, 61, 202)], (0, 0, 255))
        original = bytes(self.rgb)
        self.adjust(7, 50)
        self.adjust(5, 120, fine=False)
        self.adjust(7, -50)
        self.assertEqual(tuple(self.lib.background(c) for c in range(4)), (255, 0, 0, 127))
        self.assertEqual(bytes(self.rgb), original)
        self.lib.resetOptionAt(5)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (0, 0, 255))

    def test_reset_one_hsl_component_and_cancel_restore_exact_rgb(self):
        self.begin([(24, 117, 201), (0, 255, 0)], (19, 29, 41), modes=2)
        original = bytes(self.rgb)
        self.lib.target(2)
        before = self.hsl(1)
        self.lib.resetOptionAt(0)
        self.assertEqual(self.hsl(1), (0, before[1], before[2]))
        self.assertEqual(self.rgb_at(1), (255, 0, 0))
        self.assertEqual(self.rgb_at(0), (24, 117, 201))
        self.assertEqual(self.lib.mode(), 2)
        self.lib.adjust(7, 1, 0)
        self.assertEqual(self.lib.finish(0), 6)
        self.assertEqual(bytes(self.rgb), original)
        self.assertEqual(self.lib.mode(), 0)
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (19, 29, 41))

    def test_maximum_metadata_target_and_reject_over_capacity(self):
        self.begin([(0, 0, 255)] * 256)
        self.assertTrue(self.lib.editing())
        self.lib.target(256)
        self.adjust(0, 120, fine=False)
        self.assertEqual(self.rgb_at(254), (0, 0, 255))
        self.assertEqual(self.rgb_at(255), (255, 0, 0))
        self.assertEqual(tuple(self.lib.background(c) for c in range(3)), (0, 0, 0))
        self.lib.finish(1)
        self.begin([(255, 255, 255)] * 257)
        self.assertFalse(self.lib.editing())


if __name__ == "__main__":
    unittest.main()
