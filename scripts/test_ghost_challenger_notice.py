"""Preserving an unsaved challenger should not notify again on every reset."""

import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class ChallengerNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / "toolchain/clang++.exe"
        if not compiler.exists():
            raise unittest.SkipTest("Bundled Windows compiler required")
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        ghost = ROOT / "src/ghost.cpp"
        source = Path(cls.folder.name) / "challenger.cpp"
        source.write_text(r'''
using u32=unsigned; using u8=unsigned char; using s32=int;
struct Sample {}; struct Segment {}; struct SusamuneGhostInputSample {};
struct Track {
    bool valid,completed,saved;
    Sample *samples; Segment *segments; SusamuneGhostInputSample *inputs;
} sRecord,sPlayback;
u32 sRecordToken,sRecordIdentityToken,sPlaybackOriginRecordToken;
const u32 kPlaybackTokenBit=0x80000000;
bool sChallengerNotified,sPlaybackPinned,sPinRouteCheckPending,sRecording;
bool sRestoredPrefix; int sRestoredEndpoint;
namespace ILing {enum {SAVED_GHOST_END_NONE=0};}
u8 sLiveArea,sLiveEpisode,sLiveRouteParentArea,sLiveRouteFlags;
s32 sLiveParentEpisode,sLastSampleQf;
int gpMarDirector=1;
enum {SETTING_GHOST_LAST_SUCCESS=1};
struct Settings {bool getBool(int){return false;}}gSettings;
static unsigned notices;
struct Menu {void toast(const char*){++notices;}} menu,*gMenu=&menu;
void clearTrack(Track &track){track.valid=track.completed=track.saved=false;}
void clearRaceContext(){} void captureLiveRoute(){}
bool recordRouteMatches(u8,u8,s32,u8,u8){return true;}
bool pinSurvivesRoute(u8,u8,s32,u8){return true;}
bool recordPromotableForRoute(bool,bool){return sRecord.completed;}
void bumpPlaybackToken(){} void captureRaceContext(){} void rewindPlayback(){}
void prepareClock(s32){} bool appendSegment(){return true;}
void startEpochSamples(s32){}
''' + function_source(ghost, "void bumpRecordToken()") + "\n" +
            function_source(ghost, "void clearRecord()") + "\n" +
            function_source(ghost, "void beginAttempt(") + r'''
extern "C" __declspec(dllexport) void reset() {
    sPlaybackPinned=true;sRecordToken=0;notices=0;gMenu=&menu;clearRecord();
}
extern "C" __declspec(dllexport) void complete() {
    sRecord.valid=sRecord.completed=true;bumpRecordToken();
}
extern "C" __declspec(dllexport) unsigned restart(unsigned withMenu) {
    gMenu=withMenu?&menu:nullptr;beginAttempt(0);return notices;
}
extern "C" __declspec(dllexport) unsigned kept() {
    return sRecord.valid && sRecord.completed && !sRecord.saved && !sRecording;
}
extern "C" __declspec(dllexport) void saved() {sRecord.saved=true;}
''', encoding="ascii")
        library = source.with_suffix(".dll")
        subprocess.run([str(compiler), "--target=x86_64-pc-windows-msvc", "-shared",
                        "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry", "-O2",
                        str(source), "-o", str(library)], check=True)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_restarts_keep_challenger_and_notify_only_once(self):
        self.lib.reset()
        self.lib.complete()
        for _ in range(3):
            self.assertEqual(self.lib.restart(1), 1)
            self.assertEqual(self.lib.kept(), 1)

    def test_an_unavailable_menu_does_not_consume_initial_notice(self):
        self.lib.reset()
        self.lib.complete()
        self.assertEqual(self.lib.restart(0), 0)
        self.assertEqual(self.lib.restart(1), 1)

    def test_saved_track_releases_recording_and_new_challenger_notifies(self):
        self.lib.reset()
        self.lib.complete()
        self.assertEqual(self.lib.restart(1), 1)
        self.lib.saved()
        self.assertEqual(self.lib.restart(1), 1)
        self.assertEqual(self.lib.kept(), 0)
        self.lib.complete()
        self.assertEqual(self.lib.restart(1), 2)


if __name__ == "__main__":
    unittest.main()
