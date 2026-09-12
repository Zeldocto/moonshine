"""Run production practice bind edges and gameplay filtering on the host."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_controls import Input
from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class PracticeInputGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            "void stripControlInput(", "void consumeControlInput()",
            "bool requestPauseToggle(", "bool requestStep("))
        functions += function_source(ROOT / "src/binds.cpp", "bool Binds::wasPressed(")
        functions += function_source(ROOT / "src/binds.cpp", "bool Binds::wasPressedPracticeRaw(")
        dispatch = (ROOT / "src/main.cpp").read_text(encoding="utf-8").split(
            "if (!practiceModal) {", 1)[1].split(
            "if (gBinds.wasPressed(BIND_FREE_CAMERA))", 1)[0]
        source = Path(cls.folder.name) / "gates.cpp"
        source.write_text(r'''
#define private public
#include "susamune/binds.hxx"
#undef private
#include "susamune/practice_input.h"
struct JUTGamePad { enum { A=0x100,B=0x200,L=0x40,R=0x20 }; };
static Binds localBinds;
Binds &gBinds=localBinds;
static SusamunePracticeInput sPhysical,sConsumed;
static u16 sStripButtons;
static bool sPaused,sPausePending,sCollisionHooksReady,sStateHookReady,sRecord,sReplay,sFreeCamera;
static bool sStepQueued,sAvailable,sActionable;
static u8 sMenuAction,sSpinRemaining;
static u32 sSteps,invalidations,stops;
static bool classicSuppressed,nativePause;
struct TPauseMenu2 {enum {MENU_APPEARING=0,MENU_OPEN=1,MENU_SAVING=3};unsigned mState;};
static TPauseMenu2 pauseMenu;
static struct {TPauseMenu2 *mPauseMenu;} director={&pauseMenu},*gpMarDirector=&director;
bool nativePaused(){return nativePause;}
bool mem1(const void *p,unsigned){return p!=nullptr;}
namespace Ghost { bool observerActive() { return false; } }
namespace WarpWheel { void suppressClassicInstantUntilRelease() { classicSuppressed=true; } }
namespace CrashReport { void note(unsigned,unsigned,unsigned) {} }
static const unsigned SUSAMUNE_CRASH_EVENT_PRACTICE=1;
bool available() { return sAvailable; }
bool actionableStage() { return sActionable; }
void message(const char *) {}
void invalidate() { ++invalidations; }
void restoreCamera() {}
void stopTape(const char *) { sRecord=sReplay=false;++stops; }
''' + functions + r'''
namespace PracticeSession {
bool paused() { return sPaused; }
bool requestPauseToggle() { return ::requestPauseToggle(false); }
bool requestStep() { return ::requestStep(false); }
}
extern "C" __declspec(dllexport) unsigned dispatch(unsigned pause,unsigned before,unsigned now) {
    localBinds.mMask[BIND_PRACTICE_PAUSE]=(u16)pause;
    localBinds.mPrevHeld=(u16)before;localBinds.mHeld=(u16)now;
    const bool stepOverridesShortcut=!gBinds.recording() && PracticeSession::paused() &&
        gBinds.wasPressedSubsetRaw(BIND_PRACTICE_STEP);
    bool practiceStepConsumed=false;
''' + dispatch + r'''
    return sPaused|(sStepQueued<<1);
}
extern "C" __declspec(dllexport) void reset(unsigned flags,unsigned bind) {
    sPaused=flags&1;sPausePending=flags&2;sActionable=flags&4;
    sAvailable=(flags&8)==0;sCollisionHooksReady=(flags&16)==0;sStateHookReady=true;
    sRecord=flags&32;sReplay=false;sFreeCamera=false;nativePause=false;pauseMenu.mState=1;director.mPauseMenu=&pauseMenu;
    sStepQueued=false;sStripButtons=0;sMenuAction=0;sSpinRemaining=0;
    sSteps=invalidations=stops=0;classicSuppressed=false;
    for (unsigned i=0;i<BIND_COUNT;++i) localBinds.mMask[i]=0;
    localBinds.mMask[BIND_PRACTICE_STEP]=(u16)bind;
    localBinds.mMask[BIND_PRACTICE_PAUSE]=4;
    localBinds.mHeld=localBinds.mPrevHeld=0;
    localBinds.mRecState=0;localBinds.mRecSilent=false;
}
extern "C" __declspec(dllexport) unsigned edge(unsigned previous,unsigned current,
                                               unsigned silent,unsigned recorder) {
    localBinds.mPrevHeld=(u16)previous;localBinds.mHeld=(u16)current;
    localBinds.mRecSilent=silent!=0;localBinds.mRecState=(u8)recorder;
    const bool active=!gBinds.recording() && (sPaused ?
        gBinds.wasPressedSubsetRaw(BIND_PRACTICE_STEP) : gBinds.wasPressedPracticeRaw(BIND_PRACTICE_STEP));
    return active;
}
extern "C" __declspec(dllexport) unsigned conflicting_actions() {
    return gBinds.wasPressed(BIND_FULL_RESTART)|(classicSuppressed<<1);
}
extern "C" __declspec(dllexport) void shortcut(unsigned mask,unsigned inert) {
    localBinds.mMask[inert ? BIND_PRACTICE_SPIN_CW : BIND_FULL_RESTART]=(u16)mask;
}
extern "C" __declspec(dllexport) unsigned request(unsigned kind,unsigned menu) {
    const bool result=kind ? requestPauseToggle(menu!=0) : requestStep(menu!=0);
    return result|(sPaused<<1)|(sPausePending<<2)|(sStepQueued<<3)|
        ((unsigned)sMenuAction<<4)|(invalidations<<8)|(stops<<16);
}
extern "C" __declspec(dllexport) void native(unsigned camera,unsigned state) {
    nativePause=true;sActionable=false;sFreeCamera=camera;pauseMenu.mState=state;
}
extern "C" __declspec(dllexport) unsigned resumeCamera(unsigned menu) {
    sFreeCamera=true;sPaused=true;
    requestPauseToggle(menu!=0);
    return sFreeCamera|(sPaused<<1)|((unsigned)sMenuAction<<4);
}
extern "C" __declspec(dllexport) unsigned filter(unsigned add,const SusamunePracticeInput *in,
                                                  SusamunePracticeInput *out) {
    sStripButtons|=(u16)add;sPhysical=*in;sConsumed=*in;
    consumeControlInput();*out=sConsumed;return sStripButtons;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.filter.argtypes = [C.c_uint, C.POINTER(Input), C.POINTER(Input)]

    def setUp(self):
        self.lib.reset(5, 8)

    def test_resume_keeps_free_camera_for_both_shortcut_and_menu(self):
        self.assertEqual(self.lib.resumeCamera(0), 1)
        self.assertEqual(self.lib.resumeCamera(1), 1 | 2 | 32)

    def test_native_pause_resume_is_scoped_to_camera_and_refuses_save_dialog(self):
        self.lib.reset(4, 8)
        self.lib.native(0, 1)
        self.assertEqual(self.lib.request(1, 1) & 255, 5)  # ordinary Pause still buffers
        self.lib.reset(4, 8)
        self.lib.native(1, 1)
        self.assertEqual(self.lib.request(1, 1) & 255, 49)  # camera queues retail resume
        self.lib.reset(4, 8)
        self.lib.native(1, 3)
        self.assertEqual(self.lib.request(1, 1), 0)

    def filtered(self, add=0, **fields):
        raw, out = Input(**fields), Input()
        pending = self.lib.filter(add, C.byref(raw), C.byref(out))
        return out, pending

    def test_DUp_step_accepts_A_in_either_press_order_and_keeps_jump(self):
        for before in (0, 0x100):
            self.assertEqual(self.lib.edge(before, 0x108, 0, 0), 1)
            self.assertEqual(self.lib.request(0, 0) & 15, 11)
            out, _ = self.filtered(buttons=0x108, analogA=255, stickX=47)
            self.assertEqual((out.buttons, out.analogA, out.stickX), (0x100, 255, 47))
        self.assertEqual(self.lib.edge(8, 0x108, 0, 0), 0)
        self.assertEqual(self.lib.edge(0x108, 0x108, 0, 0), 0)

    def test_fresh_step_after_menu_release_accepts_held_A_but_recorder_is_blocked(self):
        self.assertEqual(self.lib.edge(0x100, 0x108, 1, 0), 1)
        self.assertEqual(self.lib.edge(0x100, 0x108, 1, 1), 0)
        self.lib.reset(4, 8)
        self.assertEqual(self.lib.edge(0x100, 0x108, 1, 0), 1)

    def test_pause_accepts_held_A_and_consumes_only_its_own_buttons(self):
        self.lib.reset(4, 8)
        self.assertEqual(self.lib.dispatch(4, 0x100, 0x104), 1)
        out, _ = self.filtered(buttons=0x104, analogA=255)
        self.assertEqual((out.buttons, out.analogA), (0x100, 255))
        self.assertEqual(self.lib.dispatch(4, 0x104, 0x104), 1)
        self.assertEqual(self.lib.dispatch(4, 0x100, 0x104), 0)

    def test_restart_combo_does_not_pause_or_mark_assistance(self):
        for before in (0, 0x200):
            self.lib.reset(4, 4)
            self.lib.shortcut(0x208, 0)
            self.assertEqual(self.lib.dispatch(8, before, 0x208), 0)
            out, _ = self.filtered(buttons=0x208)
            self.assertEqual(out.buttons, 0x208)
            self.assertEqual(self.lib.dispatch(8, 0x208, 8), 0)
            self.assertEqual(self.lib.dispatch(8, 0, 8), 1)

    def test_paused_step_wins_over_restart_and_suppresses_both_restart_paths(self):
        self.lib.shortcut(0x208, 0)
        self.assertEqual(self.lib.edge(0x200, 0x208, 0, 0), 1)
        self.assertEqual(self.lib.dispatch(4, 0x200, 0x208), 3)
        self.assertEqual(self.lib.conflicting_actions(), 2)

    def test_jumpdive_steps_keep_A_B_and_strip_only_advance(self):
        self.lib.shortcut(0x208, 0)
        for before in (0, 0x100, 0x200, 0x300):
            self.lib.reset(5, 8)
            self.lib.shortcut(0x208, 0)
            self.assertEqual(self.lib.dispatch(4, before, 0x308), 3)
            out, _ = self.filtered(buttons=0x308, analogA=255, analogB=255)
            self.assertEqual((out.buttons, out.analogA, out.analogB), (0x300, 255, 255))
            self.assertEqual(self.lib.conflicting_actions(), 2)
        self.assertEqual(self.lib.edge(0x308, 0x308, 1, 0), 0)
        self.assertEqual(self.lib.edge(0x300, 0x308, 1, 0), 1)

    def test_every_held_gameplay_combination_allows_one_fresh_paused_step(self):
        self.lib.shortcut(0x208, 0)
        bits = [1 << n for n in range(16) if (1 << n) & 0x1f77]
        for choice in range(1 << len(bits)):
            held = sum(bit for n, bit in enumerate(bits) if choice & (1 << n))
            self.assertEqual(self.lib.edge(held, held | 8, 1, 0), 1, hex(held))
            self.assertEqual(self.lib.edge(held | 8, held | 8, 1, 0), 0, hex(held))

    def test_inactive_larger_shortcut_does_not_block_starting_frame_advance(self):
        self.lib.reset(4, 8)
        self.lib.shortcut(0x208, 0)
        self.assertEqual(self.lib.dispatch(4, 0x300, 0x308), 1)

    def test_live_default_step_does_not_steal_the_normal_restart(self):
        self.lib.reset(4, 8)
        self.lib.shortcut(0x208, 0)
        self.assertEqual(self.lib.dispatch(4, 0x200, 0x208), 0)
        self.assertEqual(self.lib.conflicting_actions(), 1)
        out, _ = self.filtered(buttons=0x208, analogB=255)
        self.assertEqual((out.buttons, out.analogB), (0x208, 255))

    def test_restart_with_jump_held_does_not_pause_on_press_or_release(self):
        self.lib.reset(4, 4)
        self.lib.shortcut(0x208, 0)
        for before, now in ((0x100, 0x308), (0x300, 0x308),
                            (0x308, 0x108), (0x108, 8)):
            self.assertEqual(self.lib.dispatch(8, before, now), 0)
        self.assertEqual(self.lib.dispatch(8, 0x100, 0x108), 1)

    def test_identical_shortcut_keeps_existing_shared_behavior(self):
        self.lib.shortcut(8, 0)
        self.assertEqual(self.lib.edge(0, 8, 0, 0), 1)

    def test_removed_spin_shortcut_cannot_block_practice(self):
        self.lib.shortcut(0x108, 1)
        self.assertEqual(self.lib.edge(0x100, 0x108, 0, 0), 1)

    def test_L_step_and_resume_do_not_leak_until_analog_trigger_releases(self):
        self.lib.reset(5, 0x42)
        self.lib.request(0, 0)
        for buttons, trigger, expected in ((0x142, 255, 0x42), (0x140, 240, 0x40),
                                            (0x100, 120, 0x40), (0x100, 0, 0)):
            out, pending = self.filtered(buttons=buttons, triggerL=trigger, analogA=255)
            self.assertEqual((out.buttons, out.triggerL, out.analogA), (0x100, 0, 255))
            self.assertEqual(pending, expected)
        out, _ = self.filtered(buttons=0x140, triggerL=255)
        self.assertEqual((out.buttons, out.triggerL), (0x140, 255))

    def test_only_configured_controls_are_consumed(self):
        out, _ = self.filtered(0x100, buttons=0x300, analogA=255, analogB=111,
                               triggerL=123, substickX=-45)
        self.assertEqual((out.buttons, out.analogA, out.analogB,
                          out.triggerL, out.substickX), (0x200, 0, 111, 123, -45))

    def test_first_step_pauses_live_game_without_advancing_then_next_tap_steps(self):
        self.lib.reset(4, 8)
        self.assertEqual(self.lib.request(0, 0) & 15, 3)
        self.assertEqual(self.lib.request(0, 0) & 15, 11)

    def test_advance_has_priority_over_an_overlapping_resume_shortcut(self):
        self.assertEqual(self.lib.dispatch(0x48, 0, 0x48), 3)
        self.lib.reset(5, 8)
        self.assertEqual(self.lib.dispatch(8, 0, 8), 3)
        self.lib.reset(5, 8)
        self.assertEqual(self.lib.dispatch(0x48, 0, 0x108), 3)

    def test_unavailable_or_loading_controls_arm_without_queuing_a_step(self):
        for kind in (0, 1):
            self.lib.reset(0, 8)
            self.assertEqual(self.lib.request(kind, 0) & 15, 5)
            self.assertEqual(self.lib.request(0, 0) & 15, 5)
            self.assertEqual(self.lib.request(1, 0) & 15, 1)
        for flags in (8, 16):
            self.lib.reset(flags, 8)
            self.assertEqual(self.lib.request(0, 0) & 15, 0)

    def test_menu_step_and_resume_wait_for_A_release(self):
        self.assertEqual(self.lib.request(0, 1) & 63, 27)
        self.assertEqual(self.lib.request(1, 1) & 63, 35)


if __name__ == "__main__":
    unittest.main()
