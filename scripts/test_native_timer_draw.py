"""Execute the production scoped timer draw against a bounded pane fixture."""
import ctypes
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeTimerDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "win32":
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-native-draw-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = (ROOT / "src/native_timer_layout.cpp").read_text()
        source = source[source.index("namespace NativeTimerLayout"):]
        # Host pointers are 64-bit; the separate PPC compile checks retail ABI.
        source = re.sub(r"static_assert\([^;]*;", "", source)
        stub = r'''
typedef unsigned char u8; typedef unsigned u32;
extern "C" void *memcpy(void*d,const void*s,unsigned long long n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void *memset(void*d,int v,unsigned long long n){u8*a=(u8*)d;while(n--)*a++=(u8)v;return d;}
extern "C" { int _fltused; }
namespace JUtility {struct TColor {u8 r,g,b,a;};}
struct JSUPtrList;
struct JSUPtrLink {void *mItemPtr;JSUPtrList*mParentList;JSUPtrLink*mNextLink;};
struct JSUPtrList {JSUPtrLink*mFirst;};
struct JUTRect {int mX1,mY1,mX2,mY2;};
struct J2DPane {
 void **vtable; bool mIsVisible;unsigned mTag;JUTRect mRect,mCRect,mClipRect,mScissorBound;
 float mScreenMtx[3][4];u8 pad[48];unsigned _B4;u8 mAlpha,mAlphaCopy;JSUPtrList mChildrenList;
 void add(int x,int y){mRect.mX1+=x;mRect.mX2+=x;mRect.mY1+=y;mRect.mY2+=y;}
};
struct J2DPicture:J2DPane {JUtility::TColor mColorMask,mColorOverlay;};
struct J2DScreen {J2DPane*root;J2DPane*search(unsigned){return root;}};
struct Console {J2DScreen*mMainScreen;};
struct Director {bool _260;Console*mGCConsole;};
struct TApplication {enum {CONTEXT_DIRECT_STAGE=5};int mContext;} gpApplication;
Director*gpMarDirector;
namespace RetailInput {Director*stageDirector(){return gpApplication.mContext==5?gpMarDirector:nullptr;}}
struct CreationStyle {unsigned short x,y;u8 scale,textA,bgR,bgG,bgB,bgA,textBrightness,padding;};
struct Extras {CreationStyle style;bool preview,colors,label,tint;unsigned target;u8 rgb[3];J2DPane*originalPane,*tintPane;
 const CreationStyle&nativeTimerStyle(){return style;} bool editingNativeTimer(){return preview;}
 bool nativeTimerColorsEnabled(){return colors;} unsigned nativeTimerTarget(){return target;}
 bool timerLabelVisible(){return label;} const u8*nativeTimerRgb(J2DPane*p,bool*custom){
  *custom=!tint&&p!=tintPane;return colors&&p!=originalPane?rgb:0;}
} gCreationExtras;
void *retailPaneVtable[11],*retailPictureVtable[11],*retailTextVtable[11];
#include "susamune/native_timer_transform.h"
'''
        tests = r'''
void matrix(J2DPane*p,int x,int y){p->mCRect=p->mRect;p->mScreenMtx[0][0]=1;p->mScreenMtx[1][1]=1;
 p->mScreenMtx[0][3]=(float)x;p->mScreenMtx[1][3]=(float)y;}
static J2DPicture panes[34],before[34];static JSUPtrLink links[33];
extern "C" __declspec(dllexport) int run(int which,int red,int green,int blue) {
 memset(panes,0,sizeof(panes));memset(links,0,sizeof(links));
 memset(&gCreationExtras,0,sizeof(gCreationExtras));
 gCreationExtras.style={640,480,100,255,0,0,0,0,100,255};gCreationExtras.label=true;
 J2DScreen screen={panes};Console console={&screen};Director director={true,&console};
 gpApplication.mContext=5;gpMarDirector=&director;
 retailPaneVtable[10]=retailPictureVtable[10]=retailTextVtable[10]=(void*)matrix;
 unsigned count=which==3?33:18;
 for(unsigned i=0;i<count;i++){
  panes[i].vtable=i?retailPictureVtable:retailPaneVtable;
  panes[i].mIsVisible=true;panes[i].mAlpha=201;panes[i].mAlphaCopy=121;
  panes[i].mRect={13,419,23,429};panes[i].mCRect={20,30,40,50};
  panes[i].mColorMask={255,211,5,255};panes[i].mColorOverlay={0,60,255,0};
  if(i){links[i-1]={panes+i,&panes[0].mChildrenList,i+1<count?links+i:0};}
 }
 panes[0].mChildrenList.mFirst=links;
 if(which==0){memcpy(before,panes,sizeof(panes));if(NativeTimerLayout::beginDraw(&screen))return 1;}
 else {
  gCreationExtras.style.x=0;gCreationExtras.style.y=960;gCreationExtras.style.scale=200;
  gCreationExtras.style.textA=128;gCreationExtras.colors=true;
  gCreationExtras.rgb[0]=(u8)red;gCreationExtras.rgb[1]=(u8)green;gCreationExtras.rgb[2]=(u8)blue;
  if(which==2){gCreationExtras.preview=true;gCreationExtras.target=7;panes[0].mIsVisible=false;
   panes[1].mTag='\0t_1';panes[2].mTag='\0t_2';panes[3].mTag='t_tx';gCreationExtras.label=false;}
  if(which==4)panes[5].vtable=(void**)0x1234;
  if(which==5)links[2].mItemPtr=panes;
  if(which==6)gCreationExtras.originalPane=panes+4;
  if(which==7){gCreationExtras.colors=false;gCreationExtras.preview=true;}
  if(which==8)gCreationExtras.tint=true;
  if(which==9)gCreationExtras.tintPane=panes+4;
  memcpy(before,panes,sizeof(panes));
  bool active=NativeTimerLayout::beginDraw(&screen);
  if(which>=3&&which<=5){if(active)return 2;}
  else{
   if(!active||NativeTimerLayout::beginDraw(&screen))return 3;
   if(panes[0].mRect.mX1!=-627||panes[0].mRect.mY1!=899)return 4;
   if(panes[4].mAlpha!=100)return 5;
   if(which==6||which==7){
    if(panes[4].mColorMask.r!=255||panes[4].mColorMask.g!=211||panes[4].mColorMask.b!=5)return 11;
    if(panes[4].mColorOverlay.r!=0||panes[4].mColorOverlay.g!=60||panes[4].mColorOverlay.b!=255)return 12;
    if(which==6&&(panes[5].mColorMask.r!=red||panes[5].mColorOverlay.b!=blue))return 13;
   }else if(which==8||which==9){
    if(panes[4].mColorMask.r!=red||panes[4].mColorMask.g!=green||panes[4].mColorMask.b!=blue)return 14;
    if(panes[4].mColorOverlay.r!=0||panes[4].mColorOverlay.g!=60||panes[4].mColorOverlay.b!=255)return 15;
    if(panes[5].mColorMask.r!=red||panes[5].mColorMask.g!=green||panes[5].mColorMask.b!=blue)return 16;
    if(which==9&&(panes[5].mColorOverlay.r!=red||panes[5].mColorOverlay.g!=green||panes[5].mColorOverlay.b!=blue))return 17;
   }else{
    if(panes[4].mColorMask.r!=red||panes[4].mColorMask.g!=green||panes[4].mColorMask.b!=blue)return 6;
    if(panes[4].mColorOverlay.r!=red||panes[4].mColorOverlay.g!=green||panes[4].mColorOverlay.b!=blue)return 7;
   }
   if(panes[4].mColorMask.a!=255||panes[4].mColorOverlay.a!=0)return 8;
   if(which==2&&(!panes[0].mIsVisible||panes[1].mIsVisible||!panes[2].mIsVisible||panes[3].mIsVisible))return 9;
   for(unsigned i=0;i<count;i++){
    ((void(*)(J2DPane*,int,int))panes[i].vtable[10])(panes+i,20,30);
    panes[i].mAlphaCopy=19;
   }
   NativeTimerLayout::endDraw();NativeTimerLayout::endDraw();
  }
 }
 const u8*a=(u8*)panes,*b=(u8*)before;
 for(unsigned i=0;i<sizeof(panes);i++)if(a[i]!=b[i])return 10;
 return 0;
}
'''
        cpp = work / "draw.cpp"
        cpp.write_text(stub + source + tests, encoding="ascii")
        library = work / "draw.dll"
        subprocess.run([str(ROOT / "toolchain/clang++.exe"), "--target=x86_64-pc-windows-msvc",
                        "-shared", "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Xlinker", "/noentry",
                        "-I", str(ROOT / "include"), str(cpp), "-o", str(library)], check=True)
        cls.dll = ctypes.CDLL(str(library))
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_blue_purple_white_replace_hue_without_changing_texture_alpha(self):
        for rgb in ((0, 0, 255), (180, 0, 255), (255, 255, 255)):
            with self.subTest(rgb=rgb):
                self.assertEqual(self.dll.run(1, *rgb), 0)

    def test_default_preview_invalid_tree_and_reentrancy_restore_all_bytes(self):
        for case in (0, 2, 3, 4, 5):
            with self.subTest(case=case):
                self.assertEqual(self.dll.run(case, 30, 40, 50), 0)

    def test_unedited_original_preserves_retail_endpoints_in_mixed_and_original_preview(self):
        for case in (6, 7):
            with self.subTest(case=case):
                self.assertEqual(self.dll.run(case, 30, 40, 50), 0)

    def test_original_rgb_keeps_retail_shading_and_restores_all_bytes(self):
        for case in (8, 9):
            for rgb in ((0, 0, 255), (180, 0, 255), (255, 255, 255)):
                with self.subTest(case=case, rgb=rgb):
                    self.assertEqual(self.dll.run(case, *rgb), 0)


if __name__ == "__main__":
    unittest.main()
