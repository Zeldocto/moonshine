"""Compare compact notification drawing with the previous shipped geometry."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = r'''
void Reference::drawToast(Menu *menu, const char *message) const {
    if (!menu || !message || !message[0]) return;
    const int scale = mToastStyle.scale;
    int size = clampi((16 * scale + 50) / 100, 8, 32);
    const int padX = (10 * scale + 50) / 100;
    const int padY = (6 * scale + 50) / 100;
    while (size > 8 && Menu::textWidth(message, size) + padX * 2 > 640)
        size--;
    const int w = Menu::textWidth(message, size) + padX * 2;
    const int h = size + padY * 2;
    const int x = clampi(mToastStyle.x, 0, 640 - w);
    const int y = clampi(mToastStyle.y, 0, 480 - h);
    menu->fillBox(x, y, w, h, Color(0, 0, 0, 200));
    menu->fillBox(x, y, clampi((3 * scale + 50) / 100, 1, 6), h,
                  Color(90, 170, 255, 255));
    menu->drawText(message, x + padX, y + padY, size, size,
                   Color(255, 255, 255, 255));
}

void Reference::drawPbBanner(Menu *menu, const char *message) const {
    if (!menu || !message || !message[0]) return;
    const int scale = mPbBannerStyle.scale;
    int size = clampi((22 * scale + 50) / 100, 11, 44);
    const int padX = (14 * scale + 50) / 100;
    const int textY = (10 * scale + 50) / 100;
    while (size > 11 && Menu::textWidth(message, size) + padX * 2 > 640)
        size--;
    const int w = Menu::textWidth(message, size) + padX * 2;
    const int h = (42 * scale + 50) / 100;
    const int x = clampi((int)mPbBannerStyle.x - w / 2, 0, 640 - w);
    const int y = clampi(mPbBannerStyle.y, 0, 480 - h);
    menu->fillBox(x, y, w, h, Color(90, 58, 4, 230));
    menu->fillBox(x, y, clampi((4 * scale + 50) / 100, 1, 8), h,
                  Color(255, 196, 40, 255));
    menu->drawText(message, x + padX, y + textY, size, size,
                   Color(255, 239, 178, 255));
}

void Reference::drawStageSessionCounter(Menu *menu,
                                              const char *message) const {
    if (!menu || !message || !message[0]) return;
    const int scale = mStageSessionStyle.scale;
    const int size = clampi((18 * scale + 50) / 100, 9, 36);
    const int padX = (9 * scale + 50) / 100;
    const int padY = (5 * scale + 50) / 100;
    const int w = Menu::textWidth(message, size) + padX * 2;
    const int h = size + padY * 2;
    const int x = clampi(mStageSessionStyle.x, 0, 640 - w);
    const int y = clampi(mStageSessionStyle.y, 0, 480 - h);
    const int bar = clampi((3 * scale + 50) / 100, 1, 6);
    menu->fillBox(x, y, w, h,
                  Color(mStageSessionStyle.bgR, mStageSessionStyle.bgG,
                        mStageSessionStyle.bgB, mStageSessionStyle.bgA));
    menu->fillBox(x, y, bar, h, Color(80, 180, 255, 255));
    menu->drawText(message, x + padX, y + padY, size, size,
                   Color(255, 255, 255, mStageSessionStyle.textA));
}

'''


class NotificationRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-notification-rendering-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = (ROOT / "src/creation_extras.cpp").read_text()
        code = r'''
typedef unsigned char u8;typedef unsigned short u16;typedef unsigned u32;
struct CreationStyle{u16 x,y;u8 scale,textA,bgR,bgG,bgB,bgA,textBrightness,padding;};
struct Color{u32 rgba;Color(unsigned r,unsigned g,unsigned b,unsigned a):rgba(r<<24|g<<16|b<<8|a){}};
struct Command{int kind,x,y,w,h;u32 rgba,text;};
struct Menu{
 unsigned count=0;Command commands[3];static int width;
 static int textWidth(const char*,int size){return width*size/20;}
 void fillBox(int x,int y,int w,int h,Color c){commands[count++]={0,x,y,w,h,c.rgba,0};}
 void drawText(const char*t,int x,int y,int w,int h,Color c){
  u32 hash=0;while(*t)hash=hash*33+(unsigned char)*t++;
  commands[count++]={1,x,y,w,h,c.rgba,hash};}
};
int Menu::width;
struct CreationExtras{
 CreationStyle mToastStyle,mPbBannerStyle,mStageSessionStyle;
 void drawToast(Menu*,const char*)const;void drawPbBanner(Menu*,const char*)const;
 void drawStageSessionCounter(Menu*,const char*)const;
};
struct Reference{
 CreationStyle mToastStyle,mPbBannerStyle,mStageSessionStyle;
 void drawToast(Menu*,const char*)const;void drawPbBanner(Menu*,const char*)const;
 void drawStageSessionCounter(Menu*,const char*)const;
};
'''
        code += function(source, "clampi") + REFERENCE
        code += "\n".join(function(source, name) for name in (
            "drawNotification", "CreationExtras::drawToast", "CreationExtras::drawPbBanner",
            "CreationExtras::drawStageSessionCounter"))
        code += r'''
extern "C" __declspec(dllexport) int compare(unsigned kind,unsigned x,unsigned y,unsigned scale,unsigned width,unsigned mode){
 CreationStyle style={(u16)x,(u16)y,(u8)scale,(u8)(x+y),31,73,117,(u8)(x^y),100,5};
 CreationExtras current={style,style,style};Reference old={style,style,style};
 Menu a,b;Menu::width=width;const char*text=mode==1?nullptr:mode==2?"":"Practice notification";
 Menu*ap=mode==3?nullptr:&a;Menu*bp=mode==3?nullptr:&b;
 if(kind==0){current.drawToast(ap,text);old.drawToast(bp,text);}
 else if(kind==1){current.drawPbBanner(ap,text);old.drawPbBanner(bp,text);}
 else{current.drawStageSessionCounter(ap,text);old.drawStageSessionCounter(bp,text);}
 if(a.count!=b.count)return 1;
 for(unsigned i=0;i<a.count;++i){
  const Command&c=a.commands[i],&d=b.commands[i];
  if(c.kind!=d.kind||c.x!=d.x||c.y!=d.y||c.w!=d.w||c.h!=d.h||c.rgba!=d.rgba||c.text!=d.text)return 2+i;
 }
 return 0;
}
'''
        path = work / "fixture.cpp"
        path.write_text(code)
        library = path.with_suffix(".dll")
        result = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
            "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
            str(path), "-o", str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.lib = C.CDLL(str(library))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)

    def test_all_three_overlays_keep_exact_geometry_colours_and_text(self):
        for kind in range(3):
            for x in (0, 19, 319, 639, 65535):
                for y in (0, 200, 479, 65535):
                    for scale in (0, 1, 49, 50, 51, 80, 100, 199, 200, 255):
                        for width in (0, 1, 80, 319, 620, 640, 1000, 2000):
                            result = self.lib.compare(kind, x, y, scale, width, 0)
                            self.assertEqual(result, 0, (kind, x, y, scale, width))

    def test_null_and_empty_inputs_still_draw_nothing(self):
        for kind in range(3):
            for mode in (1, 2, 3):
                self.assertEqual(self.lib.compare(kind, 320, 400, 100, 500, mode), 0)


if __name__ == "__main__":
    unittest.main()
