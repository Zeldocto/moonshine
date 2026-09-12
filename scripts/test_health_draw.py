"""Run the production health/air palette scope with a retail-shaped pane fixture."""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class HealthDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-health-draw-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        prod = (ROOT / "src/creation_extras.cpp").read_text()
        code = r'''
#include "susamune/susamune_cfg.h"
typedef unsigned char u8;typedef unsigned u32;
extern "C" void*memset(void*p,int v,unsigned long long n){u8*b=(u8*)p;while(n--)*b++=(u8)v;return p;}
extern "C" void*memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
struct Color {u8 r,g,b,a;};
struct J2DPane {u32 mTypeMagic;u8 mAlpha,mAlphaCopy;bool mIsVisible;};
struct J2DPicture:J2DPane {Color mColorMask,mColorOverlay;};
struct J2DScreen {J2DPane*root,*label,*group,*background;J2DPane*search(u32 t){return t=='\0l_0'?root:t=='l_tx'?label:t=='lm_0'?group:background;}};
struct TGCConsole2 {u32 pad[6],mode;J2DScreen*mMainScreen;struct {J2DPicture*mActivePicture,*mInactivePicture;} mHealthPoints[9];};
struct Director {bool _260;TGCConsole2*mGCConsole;} *gpMarDirector;
struct TApplication {enum {CONTEXT_DIRECT_STAGE=5};int mContext;} gpApplication;
namespace RetailInput {Director*stageDirector(){return gpApplication.mContext==5?gpMarDirector:nullptr;}}
struct CreationExtras {enum {EDIT_HEALTH=1};J2DScreen*mHudScreen;struct{bool active;bool editing(){return active;}}mEditor;
 unsigned mEditMode,mEditFirst,mColorPresent;u8 mHealthRgb[2][3];
 bool beginHudDraw(J2DScreen*);void endHudDraw();};
'''
        states = prod[prod.index("struct HealthPaneState"):prod.index("static_assert(__builtin_offsetof(TGCConsole2")]
        states = states.replace('__attribute__((section(".foxtrot.bss")))', "")
        code += states
        code += "\n".join(function(prod, name) for name in (
            "loadRgb", "applyPictureRgb", "CreationExtras::beginHudDraw", "CreationExtras::endHudDraw"))
        code += r'''
static J2DPicture pictures[19],backup[19];
extern "C" __declspec(dllexport) int run(unsigned mode,bool preview,bool invalid){
 J2DPane root={'PAN1',101,102,false},group={'PAN1',103,104,false},bg={'PIC1',105,106,true};
 J2DPane oldRoot=root,oldGroup=group,oldBg=bg;
 J2DScreen screen={&root,pictures+18,&group,&bg};TGCConsole2 console={};console.mode=mode;console.mMainScreen=&screen;
 Director director={true,&console};gpMarDirector=&director;gpApplication.mContext=5;
 CreationExtras extra={};extra.mHudScreen=&screen;extra.mEditor.active=preview;extra.mEditMode=1;
 extra.mEditFirst=1;extra.mColorPresent=(1u<<25)|(1u<<26);
 extra.mHealthRgb[0][0]=255;extra.mHealthRgb[1][2]=255;
 for(unsigned i=0;i<19;i++){
  pictures[i].mTypeMagic='PIC1';pictures[i].mIsVisible=i&1;pictures[i].mAlpha=220;pictures[i].mAlphaCopy=80;
  pictures[i].mColorMask={0,255,255,255};pictures[i].mColorOverlay={0,60,255,0};
  if(i<18){if(i&1)console.mHealthPoints[i/2].mInactivePicture=pictures+i;else console.mHealthPoints[i/2].mActivePicture=pictures+i;}
 }
 if(!preview){root.mIsVisible=oldRoot.mIsVisible=true;group.mIsVisible=oldGroup.mIsVisible=true;}
 if(invalid)pictures[8].mTypeMagic='BAD!';
 memcpy(backup,pictures,sizeof(pictures));
 bool active=extra.beginHudDraw(&screen);
 if(invalid){if(active)return 1;}else{
  if(!active||extra.beginHudDraw(&screen))return 2;
  bool air=preview||mode==4||mode==5||mode==6||mode==8||mode==9;
  for(unsigned i=0;i<19;i++){
   if(!(i&1)){
    if(pictures[i].mColorMask.r!=(air?0:255)||pictures[i].mColorOverlay.b!=(air?255:0))return 3;
    if(pictures[i].mColorMask.a!=255||pictures[i].mColorOverlay.a!=0)return 4;
   }else if(pictures[i].mColorOverlay.g!=60)return 5;
   pictures[i].mAlphaCopy=8;
  }
  root.mAlphaCopy=group.mAlphaCopy=bg.mAlphaCopy=7;
  if(preview&&(!root.mIsVisible||!group.mIsVisible||root.mAlpha!=255))return 6;
  extra.endHudDraw();extra.endHudDraw();
 }
 const u8*a=(u8*)pictures,*b=(u8*)backup;
 for(unsigned i=0;i<sizeof(pictures);i++)if(a[i]!=b[i])return 7;
 if(root.mAlpha!=oldRoot.mAlpha||root.mAlphaCopy!=oldRoot.mAlphaCopy||root.mIsVisible!=oldRoot.mIsVisible)return 8;
 if(group.mAlphaCopy!=oldGroup.mAlphaCopy||group.mIsVisible!=oldGroup.mIsVisible||bg.mAlphaCopy!=oldBg.mAlphaCopy)return 9;
 return 0;
}
'''
        source = work / "health.cpp"
        source.write_text(code, encoding="ascii")
        library = work / "health.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
            "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
            "-I", str(ROOT / "include"), str(source), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_retail_air_modes_select_independent_palette_and_restore(self):
        for mode in range(12):
            with self.subTest(mode=mode):
                self.assertEqual(self.dll.run(mode, False, False), 0)

    def test_preview_alpha_visibility_reentrancy_and_invalid_type(self):
        self.assertEqual(self.dll.run(0, True, False), 0)
        self.assertEqual(self.dll.run(4, False, True), 0)


if __name__ == "__main__":
    unittest.main()
