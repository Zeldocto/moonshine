"""Run the production landing/GB observer through retail quarterframe calls."""

import ctypes as C
from pathlib import Path
import re
import subprocess
import tempfile
import unittest



ROOT = Path(__file__).resolve().parents[1]
JUMP, DIVE, GROUND = 0x02000880, 0x0080088A, 0x0C400201
A, B = 0x100, 0x200


class MovementTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.temp = tempfile.TemporaryDirectory(prefix="moonshine-movement-timing-")
        cls.addClassCleanup(cls.temp.cleanup)
        work = Path(cls.temp.name)
        source = (ROOT / "src/movement_timing_display.cpp").read_text(encoding="utf-8")
        tracking = source
        tracking = re.sub(r"^#include[^\n]*", "", tracking, flags=re.M)
        tracking = re.sub(r'asm\("[^"]+"\)', "", tracking)
        code = r'''
extern "C" int _fltused=0;
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned u32;
namespace JDrama {struct TGraphics {};}
struct TMarioControllerWork { enum {A=0x100,B=0x200}; unsigned mFrameInput; };
struct TMario {
 void **vtable;
 enum {STATE_JUMP=0x02000880, STATE_AIRBORN=0x800,
       STATE_WATERBORN=0x2000, STATE_CUTSCENE=0x1000};
 unsigned mState;
 unsigned mActionState;unsigned short mSubStateTimer;const void *mFloorTriangle;
 struct {float x,y,z;} mTranslation,mSpeed;
 TMarioControllerWork *mControllerWork;
};
enum {SETTING_GB_SKIP_DISPLAY,SETTING_JUMP_DISPLAY};
struct Settings {unsigned on[2]; bool getBool(int id) const{return on[id]!=0;}
 unsigned get(int id) const{return on[id];}} gSettings;
struct TMarDirector {enum{STATE_NORMAL=4};unsigned _260,mCurState,unk58;};
TMarDirector director,otherDirector;
TMarDirector *currentDirector;
namespace RetailInput {TMarDirector *stageDirector(){return currentDirector;}}
void DCStoreRange(void*,unsigned long long){}
TMarioControllerWork pad;
TMario mario[2];
TMario *gpMarioOriginal;
extern "C" void *marioTimingVtable[9]={};
unsigned outputState,outputPressed,retailCalls,lastCue,swapOwner;
int slipMode;unsigned slipQueries;
extern "C" int retailSlipJumpMode(TMario*){++slipQueries;return slipMode;}
JDrama::TGraphics *lastGraphics;
extern "C" void retailMarioTimingPerform(TMario*m,unsigned cue,JDrama::TGraphics*g){
 ++retailCalls;lastCue=cue;lastGraphics=g;
 m->mState=outputState;pad.mFrameInput=outputPressed;
 m->mTranslation.y+=77;m->mSpeed.y-=123;
 if(swapOwner)gpMarioOriginal=&mario[1];
}
int (*snprintf)(char*,unsigned long long,const char*,...);
void *memcpy(void*d,const void*s,unsigned long long n){
 for(unsigned long long i=0;i<n;i++)((char*)d)[i]=((const char*)s)[i];return d;}
struct Menu{};
struct CreationStyle{int x,y;u8 scale,padding[3];};
struct SusamuneWallkickStyleCfg{int x,y;u8 scale,padding[3],rgb[7][3];};
char drawnText[80];unsigned drawnColor;
struct CreationExtras{
 void stageWallkickInto(SusamuneWallkickStyleCfg*c){
  c->x=c->y=0;c->scale=100;for(unsigned i=0;i<7;i++)c->rgb[i][0]=i;}
} gCreationExtras;
namespace JapaneseUi {const char *text(const char*s){return s;}}
namespace Creation {
 int textWidth(const char*,int){return 200;}
 void drawTextBox(Menu*,const CreationStyle&,const u8(*rgb)[3],int,const char*text){
  unsigned i=0;while(text[i]){drawnText[i]=text[i];++i;}drawnText[i]=0;drawnColor=rgb[0][0];}
}
'''
        code += tracking
        code += r'''
#define API extern "C" __declspec(dllexport)
JDrama::TGraphics graphics;
API void init(){
 gSettings.on[0]=true;gSettings.on[1]=false;gpMarioOriginal=&mario[0];
 mario[0].vtable=marioTimingVtable;mario[1].vtable=marioTimingVtable;
 mario[0].mControllerWork=&pad;mario[1].mControllerWork=&pad;
 mario[0].mFloorTriangle=&director;mario[0].mState=0;slipMode=slipQueries=0;
 currentDirector=&director;director._260=1;director.mCurState=4;director.unk58=0;
 marioTimingVtable[8]=(void*)&retailMarioTimingPerform;
 MovementTimingDisplay::onStageSetup();retailCalls=0;swapOwner=0;
}
API void enable(unsigned gb,unsigned jump){gSettings.on[0]=gb;gSettings.on[1]=jump;}
API void loaded(){MovementTimingDisplay::onSavestateLoaded();}
API void setup(){MovementTimingDisplay::onStageSetup();}
API void tick(unsigned before,unsigned after,unsigned pressed,float y,float v,unsigned active){
 gpMarioOriginal->mState=before;gpMarioOriginal->mTranslation.y=y;gpMarioOriginal->mSpeed.y=v;
 MovementTimingDisplay::beforeDirect(active!=0);
 // As in retail, only the first quarterframe owns the controller edge.
 for(unsigned i=0;i<4;i++){
  ++director.unk58;outputState=after;outputPressed=i?0:pressed;
  MovementTimingDisplay::perform(gpMarioOriginal,1,&graphics);
 }
 MovementTimingDisplay::afterDirect(active!=0);
}
API void landAtQuarter(unsigned quarter){
 MovementTimingDisplay::beforeDirect(true);gpMarioOriginal->mState=0x02000880;
 for(unsigned i=0;i<4;i++){
  director.unk58=i;outputState=i>=quarter?0x0C400201:0x02000880;outputPressed=0;
  MovementTimingDisplay::perform(gpMarioOriginal,1,&graphics);
 }
 MovementTimingDisplay::afterDirect(true);
}
API void jumpAtPhase(unsigned phase){
 MovementTimingDisplay::beforeDirect(true);director.unk58=phase;
 gpMarioOriginal->mState=0x0C400201;outputState=0x02000880;outputPressed=0x100;
 MovementTimingDisplay::perform(gpMarioOriginal,1,&graphics);
 MovementTimingDisplay::afterDirect(true);
}
API void ownerChangeDuringFrame(){
 MovementTimingDisplay::beforeDirect(true);swapOwner=1;
 MovementTimingDisplay::perform(gpMarioOriginal,1,&graphics);swapOwner=0;
 MovementTimingDisplay::afterDirect(true);
}
API void guardCase(unsigned which){
 MovementTimingDisplay::beforeDirect(true);
 if(which==0)currentDirector=&otherDirector;
 if(which==1)mario[0].vtable=0;
 if(which==2)director.mCurState=5;
 if(which==3)director._260=0;
 outputState=0x0080088A;outputPressed=0x200;
 MovementTimingDisplay::perform(&mario[0],which==4?8:1,&graphics);
 MovementTimingDisplay::afterDirect(true);
}
API unsigned shown(){return MovementTimingDisplay::sPopupFrames;}
API unsigned result(){return MovementTimingDisplay::sResult;}
API unsigned resultFrames(){return MovementTimingDisplay::sResultFrames;}
API unsigned phase(){return MovementTimingDisplay::sJumpPhase;}
API float y(){return MovementTimingDisplay::sResultY;}
API float v(){return MovementTimingDisplay::sResultV;}
API unsigned input(){return pad.mFrameInput;}
API unsigned calls(){return retailCalls;}
API unsigned cue(){return lastCue;}
API unsigned graphicsPassed(){return lastGraphics==&graphics;}
API void setFormatter(void*p){snprintf=(decltype(snprintf))p;}
API const char *drawResult(){Menu menu;drawnText[0]=0;MovementTimingDisplay::draw(&menu);return drawnText;}
API unsigned color(){return drawnColor;}
API void conflictingHook(){marioTimingVtable[8]=0;MovementTimingDisplay::onStageSetup();}
API unsigned hookReady(){return MovementTimingDisplay::sHookReady;}
API unsigned slotUntouched(){return marioTimingVtable[8]==0;}
API unsigned slide(unsigned state,unsigned timer,unsigned mode,unsigned input){
 mario[0].mState=state;mario[0].mSubStateTimer=timer;mario[0].mActionState=input;slipMode=mode;
 return MovementTimingDisplay::buttslideStatus();}
API unsigned queries(){return slipQueries;}
API unsigned slideGuard(unsigned which){
 if(which==0)currentDirector=0;if(which==1)currentDirector=&otherDirector;
 if(which==2)director._260=0;if(which==3)director.mCurState=5;
 if(which==4)mario[0].vtable=0;if(which==5)gpMarioOriginal=&mario[1];
 if(which==6)mario[0].mFloorTriangle=0;
 return MovementTimingDisplay::buttslideStatus();}
'''
        # Execute the retail common handlers and their shared early jump path.
        # The remaining sliding movement is neutral in this decision fixture.
        code += r'''
typedef int BOOL;
enum{MARIO_STATUS_CATCH_STOP=0x8a6,MARIO_STATUS_JUMP=0x02000880};
struct RetailSlip {
 unsigned short mStatusTimer;unsigned mInput;int mode;bool jumped;
 int canSlipJump(){return mode;}void isForceSlip(){}
 int changePlayerJumping(int,int){jumped=true;return 1;}
 int changePlayerDropping(int,int){jumped=true;return 1;}
 int changePlayerStatus(int,int,bool){jumped=true;return 1;}
 int getSlideStopNormal(){return 0;}bool doSliding(int){return false;}
 void slippingBasic(int,int,int);BOOL slipForeCommon(int,int,int,int);BOOL slipBackCommon(int,int,int);
};
'''
        code += r'''

void RetailSlip::slippingBasic(int statusOnStop, int statusOnFall, int slipAnim)
{
	isForceSlip();
	if ((mInput & 0x2) && canSlipJump() == 1) {
		changePlayerStatus(MARIO_STATUS_JUMP, 0, false);
		return;
	}
}

BOOL RetailSlip::slipForeCommon(int arg0, int arg1, int arg2, int arg3)
{
	if (mStatusTimer > 20 && canSlipJump()) {
		if (mInput & 0x2)
			return changePlayerJumping(arg1, 0);
	} else {
		mStatusTimer++;
	}

	if (doSliding(getSlideStopNormal()))
		return changePlayerStatus(arg0, 0, false);

	slippingBasic(arg0, arg2, arg3);
	return 0;
}

BOOL RetailSlip::slipBackCommon(int arg0, int arg1, int arg2)
{
	if (mStatusTimer > 20) {
		if (!(mInput & 0x8) && (mInput & 0x2) && canSlipJump())
			return changePlayerDropping(MARIO_STATUS_CATCH_STOP, 0);
	} else {
		mStatusTimer++;
	}

	if (doSliding(getSlideStopNormal()))
		return changePlayerStatus(arg0, 0, false);

	slippingBasic(arg0, arg1, arg2);
	return 0;
}
'''
        code += r'''
API unsigned retailReady(unsigned back,unsigned timer,unsigned mode,unsigned input){
 RetailSlip r={(unsigned short)timer,input|2,(int)mode,false};
 if(back)r.slipBackCommon(0,0,0);else r.slipForeCommon(0,0,0,0);
 return r.jumped;
}
'''
        path = work / "fixture.cpp"
        path.write_text(code, encoding="ascii")
        dll = work / "fixture.dll"
        build = subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                                "-nostdlib", "-fno-builtin", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                                str(path), "-o", str(dll)], capture_output=True, text=True)
        if build.returncode:
            raise AssertionError(build.stderr)
        cls.lib = C.CDLL(str(dll))
        from _ctypes import FreeLibrary
        cls.addClassCleanup(FreeLibrary, cls.lib._handle)
        cls.lib.tick.argtypes = [C.c_uint, C.c_uint, C.c_uint,
                                C.c_float, C.c_float, C.c_uint]
        cls.lib.y.restype = cls.lib.v.restype = C.c_float
        cls.lib.drawResult.restype = C.c_char_p
        cls.lib.setFormatter.argtypes = [C.c_void_p]
        cls.crt = C.CDLL("msvcrt.dll")
        cls.lib.setFormatter(C.cast(cls.crt._snprintf, C.c_void_p))

    def setUp(self):
        self.lib.init()

    def tick(self, before=JUMP, after=JUMP, pressed=0, y=404, v=6, active=True):
        self.lib.tick(before, after, pressed, y, v, active)

    def jump(self, frames):
        self.tick(GROUND, JUMP, A, 230, 38)
        for _ in range(frames - 1):
            self.tick()

    def test_ninth_completed_frame_uses_pre_dive_y_and_velocity(self):
        self.jump(9)
        self.tick(after=DIVE, pressed=B)
        self.assertEqual((self.lib.result(), self.lib.resultFrames()), (1, 9))
        self.assertEqual((self.lib.y(), self.lib.v()), (404, 6))
        self.assertEqual(self.lib.shown(), 90)
        self.assertEqual(self.lib.input(), 0)  # Later retail quarters cleared it.
        self.assertEqual(self.lib.calls(), 40)

    def test_early_and_late_frames(self):
        for frames, expected in ((1, 0), (8, 0), (10, 2), (22, 2), (270, 2)):
            with self.subTest(frames=frames):
                self.lib.init()
                self.jump(frames)
                self.tick(after=DIVE, pressed=B)
                self.assertEqual(self.lib.result(), expected)
                self.assertEqual(self.lib.resultFrames(), min(frames, 255))

    def test_nine_frames_alone_cannot_report_on_time(self):
        for y, v in ((403, 6), (405, 6), (404, 5.9), (404, 6.1),
                     (float("nan"), 6), (404, float("inf"))):
            with self.subTest(y=y, v=v):
                self.lib.init()
                self.jump(9)
                self.tick(after=DIVE, pressed=B, y=y, v=v)
                self.assertEqual(self.lib.result(), 3)

    def test_reference_tolerance_matches_display_precision(self):
        self.jump(9)
        self.tick(after=DIVE, pressed=B, y=403.75, v=6.02)
        self.assertEqual(self.lib.result(), 1)

    def test_menu_and_practice_holds_do_not_age_jump_or_popup(self):
        self.jump(8)
        for _ in range(300):
            self.tick(active=False)
        self.tick()
        self.tick(after=DIVE, pressed=B)
        self.assertEqual(self.lib.result(), 1)
        for _ in range(300):
            self.tick(active=False)
        self.assertEqual(self.lib.shown(), 90)
        for _ in range(90):
            self.tick(before=GROUND, after=GROUND)
        self.assertEqual(self.lib.shown(), 0)

    def test_untracked_airborne_start_cannot_invent_takeoff(self):
        for previous in (JUMP, 0x0000088C, 0x0000088B, 0x000024D7, 0x10001308):
            with self.subTest(previous=previous):
                self.lib.init()
                self.tick(previous, JUMP, A)
                self.tick(after=DIVE, pressed=B)
                self.assertEqual(self.lib.shown(), 0)

    def test_a_must_cause_a_grounded_single_jump_before_gb_can_track(self):
        for after, pressed in ((GROUND, A), (JUMP, 0), (0x02000881, A)):
            self.lib.init()
            self.tick(GROUND, after, pressed)
            for _ in range(8):
                self.tick()
            self.tick(after=DIVE, pressed=B)
            self.assertEqual(self.lib.shown(), 0)

    def test_diving_without_a_new_consumed_b_edge_does_not_report(self):
        self.jump(9)
        self.tick(after=DIVE, pressed=0)
        self.assertEqual(self.lib.shown(), 0)

    def test_landing_hover_and_other_jumps_end_gb_tracking(self):
        for next_state in (GROUND, 0x0000088B, 0x02000881, 0x00000890):
            with self.subTest(next_state=next_state):
                self.lib.init()
                self.jump(8)
                self.tick(after=next_state)
                self.tick(after=DIVE, pressed=B)
                self.assertEqual(self.lib.shown(), 0)

    def test_stage_state_and_owner_changes_discard_old_counter(self):
        for reset in (self.lib.setup, self.lib.loaded, self.lib.ownerChangeDuringFrame):
            self.lib.init()
            self.jump(9)
            reset()
            self.tick(after=DIVE, pressed=B)
            self.assertEqual(self.lib.shown(), 0)

    def test_disabled_display_cannot_resume_mid_jump(self):
        self.jump(8)
        self.lib.enable(0, 0)
        self.tick()
        self.lib.enable(1, 0)
        self.tick(after=DIVE, pressed=B)
        self.assertEqual(self.lib.shown(), 0)

    def test_jump_reports_next_active_frame_and_actual_takeoff_phase(self):
        for landing in range(4):
            for phase in range(4):
                with self.subTest(landing=landing, phase=phase):
                    self.lib.init()
                    self.lib.enable(0, 1)
                    self.lib.landAtQuarter(landing)
                    self.lib.jumpAtPhase(phase)
                    self.assertEqual((self.lib.result(), self.lib.resultFrames()), (4, 1))
                    self.assertEqual(self.lib.phase(), phase)

    def test_jump_waits_and_holds_are_separate(self):
        self.lib.enable(0, 1)
        self.lib.landAtQuarter(2)
        for _ in range(5):
            self.tick(GROUND, GROUND)
        for _ in range(300):
            self.tick(GROUND, GROUND, active=False)
        self.lib.jumpAtPhase(3)
        self.assertEqual((self.lib.resultFrames(), self.lib.phase()), (6, 3))

    def test_landing_jump_shows_one_through_six_then_late_with_qf(self):
        for frames in (1, 2, 3, 4, 5, 6, 7, 252, 1001):
            with self.subTest(frames=frames):
                self.lib.init()
                self.lib.enable(0, 1)
                self.lib.landAtQuarter(2)
                for _ in range(frames - 1):
                    self.tick(GROUND, GROUND)
                self.lib.jumpAtPhase(3)
                self.assertEqual(self.lib.resultFrames(), min(frames, 7))
                label = f"{frames}f" if frames <= 6 else "Late"
                self.assertEqual(self.lib.drawResult().decode(), f"Jump: {label} QF3")
                self.assertEqual(self.lib.color(), min(frames, 7) - 1)

    def test_landing_clock_starts_at_most_recent_landing_not_stage_start(self):
        self.lib.enable(0, 1)
        for _ in range(252):
            self.tick(GROUND, GROUND)
        self.lib.landAtQuarter(3)
        self.lib.jumpAtPhase(1)
        self.assertEqual(self.lib.drawResult(), b"Jump: 1f QF1")
        self.lib.landAtQuarter(0)
        for _ in range(6):
            self.tick(GROUND, GROUND)
        self.lib.jumpAtPhase(2)
        self.assertEqual(self.lib.drawResult(), b"Jump: Late QF2")
        self.lib.landAtQuarter(2)
        self.lib.jumpAtPhase(0)
        self.assertEqual(self.lib.drawResult(), b"Jump: 1f QF0")

    def test_landing_history_is_cleared_on_stage_and_state_load(self):
        for reset in (self.lib.setup, self.lib.loaded):
            with self.subTest(reset=reset):
                self.lib.init()
                self.lib.enable(0, 1)
                self.lib.landAtQuarter(2)
                reset()
                self.lib.jumpAtPhase(1)
                self.assertEqual(self.lib.drawResult(), b"")
                self.lib.landAtQuarter(0)
                self.lib.jumpAtPhase(2)
                self.assertEqual(self.lib.drawResult(), b"Jump: 1f QF2")

    def test_jump_requires_observed_landing_and_disallows_walkoff(self):
        self.lib.enable(0, 1)
        self.tick(GROUND, JUMP, A)
        self.assertEqual(self.lib.shown(), 0)
        self.lib.landAtQuarter(1)
        self.tick(GROUND, 0x0000088C)
        self.tick(GROUND, JUMP, A)
        self.assertEqual(self.lib.shown(), 0)

    def test_retained_foreign_hook_is_never_overwritten(self):
        self.lib.conflictingHook()
        self.assertEqual(self.lib.hookReady(), 0)
        self.assertEqual(self.lib.slotUntouched(), 1)
        self.jump(9)
        self.tick(after=DIVE, pressed=B)
        self.assertEqual(self.lib.shown(), 0)

    def test_buttslide_matches_retail_jump_gates_for_both_directions(self):
        self.lib.enable(0,2)
        for back in (0,1):
            for mode in (0,1,2,3,255):
                for timer in (0,1,19,20,21,22,65535):
                    for input_ in (0,8):
                        with self.subTest(back=back,mode=mode,timer=timer,input=input_):
                            ready=self.lib.retailReady(back,timer,mode,input_)
                            shown=self.lib.slide(0x00840452+back,timer,mode,input_)
                            self.assertEqual(shown,2 if ready else 1)

    def test_buttslide_is_live_read_only_and_has_no_animation_guess(self):
        self.lib.enable(0,2)
        calls=self.lib.calls()
        self.assertEqual(self.lib.slide(0x00840452,20,2,0),1)
        self.assertEqual(self.lib.slide(0x00840452,21,2,0),2)
        self.assertEqual(self.lib.slide(0x00840452,21,0,0),1)
        self.assertEqual(self.lib.slide(0x00840452,0,1,0),2)
        for _ in range(100):self.assertEqual(self.lib.slide(0x00840452,20,2,0),1)
        self.assertEqual(self.lib.calls(),calls)
        self.assertEqual(self.lib.shown(),0)

    def test_buttslide_modes_and_runtime_guards(self):
        for setting,expected in ((0,0),(1,0),(2,2),(3,2)):
            self.lib.enable(0,setting)
            self.assertEqual(self.lib.slide(0x00840452,21,2,0),expected)
        for state in (GROUND,JUMP,DIVE,0x00800456,0x0084045d,0x04808459):
            calls=self.lib.queries()
            self.assertEqual(self.lib.slide(state,21,2,0),0)
            self.assertEqual(self.lib.queries(),calls)
        for guard in range(7):
            self.lib.init();self.lib.enable(0,2);self.lib.slide(0x00840452,21,2,0)
            calls=self.lib.queries()
            self.assertEqual(self.lib.slideGuard(guard),0)
            self.assertEqual(self.lib.queries(),calls)

    def test_buttslide_only_does_not_record_landing_popup_both_does(self):
        for setting,frames in ((2,0),(3,90)):
            self.lib.init();self.lib.enable(0,setting);self.lib.landAtQuarter(1)
            self.lib.jumpAtPhase(2)
            self.assertEqual(self.lib.shown(),frames)

    def test_guarded_nonmovement_calls_still_forward_once_unchanged(self):
        for guard in range(5):
            self.lib.init()
            self.jump(9)
            before = self.lib.calls()
            self.lib.guardCase(guard)
            self.assertEqual(self.lib.calls(), before + 1)
            self.assertEqual(self.lib.shown(), 0)
            self.assertEqual(self.lib.cue(), 8 if guard == 4 else 1)
            self.assertEqual(self.lib.graphicsPassed(), 1)


if __name__ == "__main__":
    unittest.main()
