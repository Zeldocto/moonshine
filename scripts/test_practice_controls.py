"""Exercise the production camera basis and queued physical stick inputs."""

import ctypes as C
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source


ROOT = Path(__file__).resolve().parents[1]


class Input(C.Structure):
    _fields_ = [("buttons", C.c_ushort), ("stickX", C.c_byte),
                ("stickY", C.c_byte), ("substickX", C.c_byte),
                ("substickY", C.c_byte), ("triggerL", C.c_ubyte),
                ("triggerR", C.c_ubyte), ("analogA", C.c_ubyte),
                ("analogB", C.c_ubyte), ("error", C.c_byte),
                ("flags", C.c_ubyte)]


class PracticeControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        source = Path(cls.folder.name) / "controls.cpp"
        production = ROOT / "src/practice_session.cpp"
        functions = "\n".join(function_source(production, signature) for signature in (
            'extern "C" void susamunePracticeClampPad(', "bool observerTransition()", "void cameraStick(",
            "f32 cameraScale(", "f32 cameraSpeedScale()", "void resetCameraMotion()", "void smoothCameraGroup(", "bool smoothCameraInput(", "void updateCamera()"))
        source.write_text(r'''
#include "susamune/practice_input.h"
#include "Dolphin/PAD.h"
typedef unsigned char u8;
typedef float f32;
extern "C" { int _fltused; }
struct Vec { float x,y,z; void set(float a,float b,float c) { x=a;y=b;z=c; } };
struct CameraView { Vec position,target,up; float fovy; };
struct JUTGamePad { enum { X=0x400 }; };
static const int SETTING_FREE_CAMERA_SPEED=1;
static const int SETTING_FREE_CAMERA_STRAFE_REVERSE=2;
static const int SETTING_FREE_CAMERA_SENSITIVITY=3;
static const int SETTING_FREE_CAMERA_SMOOTHING=4;
typedef int SettingId;
struct Settings { u8 choice,reverse,sensitivity,smoothing; u8 get(int id) { return id==1?choice:id==2?reverse:id==3?sensitivity:smoothing; } } gSettings;
static CameraView sCameraView;
static SusamunePracticeInput sPhysical;
static s8 sCameraSticks[4];
static f32 sCameraMotion[5];static u32 sCameraTick;static bool sCameraTickValid;
static u32 mockTick;
#define OS_TIMER_CLOCK 40000000u
u32 OSGetTick(){return mockTick;}
extern "C" void *memset(void *d,int v,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)v;return d;}
static unsigned clampCalls;
extern "C" void *memcpy(void *d,const void *s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void PADClamp(PADStatus *pad) {
    ++clampCalls;
    for(unsigned port=0;port<4;++port) {
        if(pad[port].mCurError) continue;
        s8 *axes=reinterpret_cast<s8*>(&pad[port].mStickX);
        for(unsigned i=0;i<4;++i){int v=axes[i];axes[i]=(s8)(v>15?v-15:v<-15?v+15:0);}
        pad[port].mTriggerLeft/=2;pad[port].mTriggerRight/=2;
    }
}
static bool sFreeCamera,sModal,sCameraWaitButtons,sControl,sNormal,sPaused;
static bool sStepQueued,sSpinClockwise;
static u8 sSpinRemaining,sMenuAction;
static const u8 kSpinFrames=9;
static unsigned invalidations;
static float sYaw,sPitch;
static float (*sine)(float),(*cosine)(float),(*squareRoot)(float);
float sinf(float x) { return sine(x); }
float cosf(float x) { return cosine(x); }
float retailSquareRoot(float x) { return squareRoot(x); }
float Clamp(float x,float lo,float hi) { return x<lo?lo:(x>hi?hi:x); }
bool controlStage() { return sControl; }
bool normalStage() { return sNormal; }
void message(const char *) {}
void invalidate() { ++invalidations; }
namespace Ghost {
static bool active,loading,cleanup;
bool observerActive() { return active; }
bool observerLoading() { return loading; }
bool observerCleanupPending() { return cleanup; }
}
''' + functions + r'''
extern "C" __declspec(dllexport) void smoothingStart(unsigned choice,unsigned tick) {
    resetCameraMotion();mockTick=tick;gSettings.smoothing=(u8)choice;
    gSettings.choice=gSettings.sensitivity=2;gSettings.reverse=0;
    sYaw=sPitch=0;sCameraView.position.set(0,0,0);
}
extern "C" __declspec(dllexport) unsigned filterInput(float *input,unsigned tick,unsigned choice) {
    mockTick=tick;gSettings.smoothing=(u8)choice;return smoothCameraInput(input);
}
extern "C" __declspec(dllexport) void vectorStep(float *value,const float *target,unsigned count,float step) {
    smoothCameraGroup(value,target,count,step);
}
extern "C" __declspec(dllexport) void smoothingFrame(unsigned tick,const SusamunePracticeInput *input,
    unsigned flags,float *out) {
    mockTick=tick;sPhysical=*input;sCameraSticks[0]=input->stickX;sCameraSticks[1]=input->stickY;
    sCameraSticks[2]=input->substickX;sCameraSticks[3]=input->substickY;
    sFreeCamera=!(flags&1);sModal=flags&2;sControl=!(flags&4);sCameraWaitButtons=flags&8;
    updateCamera();out[0]=sCameraView.position.x;out[1]=sCameraView.position.y;out[2]=sCameraView.position.z;
    out[3]=sYaw;out[4]=sPitch;memcpy(out+5,sCameraMotion,sizeof(sCameraMotion));
}
extern "C" __declspec(dllexport) unsigned rawClamp(const SusamunePracticeInput *in,
    SusamunePracticeInput *out,s8 *raw,unsigned wrapped) {
    PADStatus pad[4];memcpy(pad,in,sizeof(pad));clampCalls=0;
    if(wrapped)susamunePracticeClampPad(pad);else PADClamp(pad);
    memcpy(out,pad,sizeof(pad));memcpy(raw,sCameraSticks,4);return clampCalls;
}
extern "C" __declspec(dllexport) void trig(float (*s)(float),float (*c)(float),float (*r)(float)) {
    sine=s;cosine=c;squareRoot=r;
}
extern "C" __declspec(dllexport) void camera(float yaw,unsigned choice,unsigned flags,
    const SusamunePracticeInput *input,float *out) {
    sPhysical=*input;sCameraSticks[0]=input->stickX;sCameraSticks[1]=input->stickY;sCameraSticks[2]=input->substickX;sCameraSticks[3]=input->substickY;sYaw=yaw;sPitch=0;sFreeCamera=true;
    sModal=flags&1;sCameraWaitButtons=flags&2;sControl=!(flags&4);
    gSettings.smoothing=0;gSettings.choice=(u8)choice;gSettings.reverse=(flags&8)!=0;
    gSettings.sensitivity=(flags&16)?(flags>>5):2;sCameraView.position.set(0,0,0);
    sCameraView.target.set(0,0,0);updateCamera();
    out[0]=sCameraView.position.x;out[1]=sCameraView.position.y;
    out[2]=sCameraView.position.z;out[3]=sCameraView.target.x;
    out[4]=sCameraView.target.y;out[5]=sCameraView.target.z;
    out[6]=sYaw;out[7]=sPitch;out[8]=sCameraWaitButtons;
}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        "-I", str(ROOT / "include"), str(source), "-o", str(library)],
                       check=True, text=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        callback = C.CFUNCTYPE(C.c_float, C.c_float)
        cls.sine, cls.cosine, cls.square_root = callback(math.sin), callback(math.cos), callback(math.sqrt)
        cls.lib.trig.argtypes = [callback, callback, callback]
        cls.lib.trig(cls.sine, cls.cosine, cls.square_root)
        cls.lib.vectorStep.argtypes = [C.POINTER(C.c_float), C.POINTER(C.c_float), C.c_uint, C.c_float]
        cls.lib.filterInput.argtypes = [C.POINTER(C.c_float), C.c_uint, C.c_uint]
        cls.lib.smoothingFrame.argtypes = [C.c_uint, C.POINTER(Input), C.c_uint, C.POINTER(C.c_float)]
        cls.lib.camera.argtypes = [C.c_float, C.c_uint, C.c_uint, C.POINTER(Input),
                                  C.POINTER(C.c_float)]

    def vector_step(self, value, target, step):
        out = (C.c_float * len(value))(*value)
        self.lib.vectorStep(out, (C.c_float * len(target))(*target), len(value), step)
        return list(out)

    def filtered(self, target, seconds, choice):
        values = (C.c_float * 5)(*target)
        self.lib.filterInput(values, round(seconds * 40000000) & 0xffffffff, choice)
        return list(values)

    def test_smoothing_both_start_and_release_settle_for_ntsc_pal_and_irregular_frames(self):
        for seconds in (.1, .3, 1.5):
            for intervals in ([1 / 30], [1 / 25], [1 / 60], [.012, .024, .017, .029]):
                value = [0.0, 0.0]
                target = [.6, .8]
                elapsed = 0
                frame = 0
                while elapsed < seconds + .001:
                    dt = intervals[frame % len(intervals)]
                    before = value
                    value = self.vector_step(value, target, dt / seconds)
                    self.assertTrue(all(a <= b + 1e-6 and b <= t + 1e-6 for a, b, t in zip(before, value, target)))
                    if elapsed == 0 and dt < seconds:
                        self.assertGreater(value[1], 0)
                        self.assertLess(value[1], target[1])
                    elapsed += dt
                    frame += 1
                for actual, expected in zip(value, target):
                    self.assertAlmostEqual(actual, expected, places=6)
                elapsed = 0
                while elapsed < seconds + .001:
                    dt = intervals[frame % len(intervals)]
                    value = self.vector_step(value, [0, 0], dt / seconds)
                    if value[1] > 1e-7:
                        self.assertAlmostEqual(value[0] / value[1], .75, delta=1e-4)
                    elapsed += dt
                    frame += 1
                self.assertEqual(value, [0, 0])

    def test_smoothing_tracks_jitter_without_restarting_and_does_not_overshoot_reversal(self):
        value = [0.0, 0.0]
        for frame in range(90):
            value = self.vector_step(value, [0, .99 + .01 * (frame & 1)], 1 / 90)
        self.assertGreater(value[1], .97)
        previous = value[1]
        for frame in range(130):
            value = self.vector_step(value, [0, -1], 1 / 90)
            self.assertLessEqual(value[1], previous + 1e-6)
            self.assertGreaterEqual(value[1], -1)
            previous = value[1]
        self.assertEqual(value, [0, -1])

    def test_smoothing_setting_uses_real_seconds_for_every_displayed_duration(self):
        target = [.6, .8, -.8, .6, 1]
        for choice in range(1, 16):
            self.lib.smoothingStart(choice, 0)
            self.assertEqual(self.filtered(target, 0, choice), [0] * 5)
            frames = choice * 4  # 25 ms increments: four frames per 0.1 s
            for frame in range(1, frames + 1):
                value = self.filtered(target, frame * .025, choice)
                if frame == frames // 2:
                    for actual, goal in zip(value, target):
                        self.assertAlmostEqual(actual, .75 * goal, delta=2e-6)
            for actual, goal in zip(value, target):
                self.assertAlmostEqual(actual, goal, delta=1e-6)
            for frame in range(1, frames + 1):
                value = self.filtered([0] * 5, (frames + frame) * .025, choice)
            self.assertEqual(value, [0] * 5)

    def test_smoothing_clock_wrap_gap_reset_and_off_identity(self):
        choice = 10
        start = 0xffff0000
        self.lib.smoothingStart(choice, start)
        target = [1, 0, 0, 1, .5]
        first = (C.c_float * 5)(*target)
        self.lib.filterInput(first, start, choice)
        self.assertEqual(list(first), [0] * 5)
        second = (C.c_float * 5)(*target)
        self.lib.filterInput(second, (start + 1333333) & 0xffffffff, choice)
        self.assertGreater(second[0], 0)
        self.assertLess(second[0], 1)
        stalled = (C.c_float * 5)(*target)
        self.lib.filterInput(stalled, (start + 1333333 + 10000001) & 0xffffffff, choice)
        self.assertEqual(list(stalled), [0] * 5)
        for mode in (0, 255):
            original = (C.c_float * 5)(.3125, -.625, .75, -.875, .375)
            before = bytes(original)
            self.assertEqual(self.lib.filterInput(original, 123, mode), 0)
            self.assertEqual(bytes(original), before)

    def test_smoothing_height_and_rotation_start_gently_and_reset_without_drift(self):
        full = Input(stickX=80, substickX=60, substickY=30, triggerR=255)
        zero = Input()
        for flags, error in ((1, 0), (2, 0), (4, 0), (8, 0), (0, -1)):
            self.lib.smoothingStart(10, 100)
            out = (C.c_float * 10)()
            self.lib.smoothingFrame(100, C.byref(full), 0, out)
            self.assertEqual(list(out), [0] * 10)
            self.lib.smoothingFrame(1333433, C.byref(full), 0, out)
            self.assertTrue(0 < out[1] < 20)
            self.assertTrue(-.035 < out[3] < 0)
            self.assertGreater(out[4], 0)
            before = list(out)[:5]
            rejected = Input(buttons=0x100 if flags == 8 else 0, error=error)
            self.lib.smoothingFrame(2666766, C.byref(rejected), flags, out)
            self.assertEqual(list(out)[:5], before)
            self.assertEqual(list(out)[5:], [0] * 5)
            self.lib.smoothingFrame(4000099, C.byref(zero), 0, out)
            self.assertEqual(list(out)[:5], before)

    def test_raw_camera_capture_precedes_unchanged_retail_clamp_for_all_ports(self):
        for error in (0, -1):
            source = (Input * 4)(*[Input(buttons=0x1300 + i, stickX=70, stickY=5,
                substickX=-6, substickY=-65, triggerL=120, triggerR=180,
                error=error if i == 0 else 0) for i in range(4)])
            expected, actual = (Input * 4)(), (Input * 4)()
            raw = (C.c_byte * 4)()
            self.assertEqual(self.lib.rawClamp(source, expected, raw, 0), 1)
            self.assertEqual(self.lib.rawClamp(source, actual, raw, 1), 1)
            self.assertEqual(bytes(actual), bytes(expected))
            self.assertEqual(list(raw), [70, 5, -6, -65])
            if not error:
                self.assertEqual((actual[0].stickX, actual[0].stickY), (55, 0))

    def camera(self, yaw=0, choice=2, flags=0, **controls):
        raw = Input(**controls)
        out = (C.c_float * 9)()
        self.lib.camera(yaw, choice, flags, C.byref(raw), out)
        return list(out)

    def test_strafe_follows_lookat_screen_right_for_every_heading(self):
        for degree in range(-180, 181, 5):
            yaw = math.radians(degree)
            x, _, z, *_ = self.camera(yaw, stickX=80)
            self.assertAlmostEqual(x, -math.cos(yaw) * 20, places=4)
            self.assertAlmostEqual(z, math.sin(yaw) * 20, places=4)
            self.assertAlmostEqual(x * math.sin(yaw) + z * math.cos(yaw), 0, places=4)

    def test_speed_scales_translation_height_and_existing_boost(self):
        for choice, scale in enumerate((.25, .5, 1, 2, 4)):
            for boost, base in ((0, 20), (0x400, 75)):
                out = self.camera(choice=choice, stickY=80, triggerR=255, buttons=boost)
                self.assertAlmostEqual(out[2], base * scale)
                self.assertAlmostEqual(out[1], base * scale)
        self.assertAlmostEqual(self.camera(choice=255, stickY=80)[2], 20)

    def test_look_right_agrees_with_strafe_right_and_speed_does_not_change_turning(self):
        for choice in range(5):
            out = self.camera(choice=choice, substickX=80)
            self.assertLess(out[3], 0)
            self.assertAlmostEqual(out[6], -.035, places=6)

    def test_reverse_sideways_changes_only_main_stick_lateral_motion(self):
        for degree in range(-180, 181, 15):
            yaw = math.radians(degree)
            normal = self.camera(yaw, stickX=80)
            reverse = self.camera(yaw, flags=8, stickX=80)
            self.assertAlmostEqual(normal[0], -reverse[0], places=4)
            self.assertAlmostEqual(normal[2], -reverse[2], places=4)
            for controls in ({"stickY": 80}, {"substickX": 80},
                             {"substickY": 80}, {"triggerR": 255}):
                self.assertEqual(self.camera(yaw, **controls),
                                 self.camera(yaw, flags=8, **controls))

    def test_look_sensitivity_changes_both_angles_without_scaling_movement(self):
        for choice, scale in enumerate((.25, .5, 1, 2, 4)):
            out = self.camera(flags=16 | choice << 5, substickX=80, substickY=80, triggerR=255)
            self.assertAlmostEqual(out[6], -.035 * scale / math.sqrt(2), places=6)
            self.assertAlmostEqual(out[7], .035 * scale / math.sqrt(2), places=6)
            self.assertAlmostEqual(out[1], 20)
        self.assertAlmostEqual(self.camera(flags=16 | 255 << 5, substickX=80)[6], -.035, places=6)

    def test_camera_modal_release_latch_and_deadzone(self):
        for flags in (1, 4):
            self.assertEqual(self.camera(flags=flags, stickX=80)[:3], [0, 0, 0])
        out = self.camera(flags=2, buttons=0x44, triggerL=255, stickX=80)
        self.assertEqual(out[:3], [0, 0, 0])
        self.assertEqual(out[8], 1)
        self.assertNotEqual(self.camera(flags=2, stickX=80)[0], 0)
        for x in range(-12, 13):
            for y in range(-12, 13):
                if x*x + y*y <= 144:
                    self.assertEqual(self.camera(stickX=x, stickY=y)[:3], [0, 0, 0])

    def test_radial_input_preserves_shallow_angles_in_all_quadrants(self):
        for x, y in ((1, 80), (11, 70), (30, 60), (60, 30), (80, 1)):
            for sx in (-1, 1):
                for sy in (-1, 1):
                    mx, _, mz, *_ = self.camera(stickX=x*sx, stickY=y*sy)
                    self.assertNotEqual(mx, 0)
                    self.assertAlmostEqual(-mx/mz, x*sx/(y*sy), places=5)
                    look = self.camera(substickX=x*sx, substickY=y*sy)
                    self.assertAlmostEqual(-look[6]/look[7], x*sx/(y*sy), places=5)

    def test_radial_response_caps_diagonal_speed_and_eases_from_rest(self):
        for x, y in ((80, 0), (0, 80), (80, 80), (-128, 127)):
            out = self.camera(stickX=x, stickY=y, substickX=x, substickY=y)
            self.assertAlmostEqual(math.hypot(out[0], out[2]), 20, places=5)
            self.assertAlmostEqual(math.hypot(out[6], out[7]), .035, places=6)
        speeds = [self.camera(stickY=y)[2] / 20 for y in range(12, 81)]
        self.assertEqual(speeds[0], 0)
        self.assertLess(speeds[1], .001)
        self.assertAlmostEqual(speeds[-1], 1)
        self.assertTrue(all(a < b for a, b in zip(speeds, speeds[1:])))
        self.assertLess(speeds[17], .25)
        self.assertGreater(speeds[51], .75)
        self.assertEqual(self.camera(stickY=0)[:3], [0, 0, 0])

    def test_disconnected_controller_cannot_move_the_camera(self):
        self.assertEqual(self.camera(error=-1, stickY=80, triggerR=255)[:3], [0, 0, 0])

    def test_automated_spins_are_removed_but_wire_ids_stay_reserved(self):
        practice = (ROOT / "src/practice_session.cpp").read_text()
        main = (ROOT / "src/main.cpp").read_text()
        menu = (ROOT / "src/menu.cpp").read_text()
        binds = (ROOT / "include/susamune/binds_list.h").read_text()
        for token in ("requestSpin", "spinInput", "sSpinRemaining", "Queue clockwise spin"):
            self.assertNotIn(token, practice + main + menu)
        for token in ("BIND_PRACTICE_SPIN_CW", "BIND_PRACTICE_SPIN_CCW"):
            self.assertIn(token, binds)
            self.assertNotIn(token, main)


if __name__ == "__main__":
    unittest.main()
