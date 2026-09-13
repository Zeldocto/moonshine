"""An asynchronous settings ACK must not persist an unconfirmed editor preview."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_practice_tape import function_source

ROOT = Path(__file__).resolve().parents[1]


class SettingsPreviewSaveTests(unittest.TestCase):
    backend = 0

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-preview-save-')
        cls.addClassCleanup(cls.temp.cleanup)
        source = r'''
typedef unsigned char u8;typedef unsigned int u32;
enum SettingsSaveState{SETTINGS_SAVE_IDLE,SETTINGS_SAVE_PENDING,SETTINGS_SAVE_OK,
SETTINGS_SAVE_ERROR,SETTINGS_SAVE_TIMEOUT,SETTINGS_SAVE_UNSUPPORTED};
static u32 liveValue,stagedValue,diskValue,writes;
const u32 kSaveTimeoutFrames=300,kSaveRetryFrames=600,kFatFsInternalError=2;
struct SusamuneCfg{u32 ackSeq,status;}cfg;
#define SUSAMUNE_CFG_PPC_PTR (&::cfg)
void DCInvalidateRange(void*,u32){}
namespace EmulatorPersistence{
 enum SaveResult{SAVE_OK,SAVE_ERROR,SAVE_PENDING};
 SaveResult poll(u32 ticket,u32*error){if(ticket!=cfg.ackSeq)return SAVE_PENDING;
 *error=cfg.status;return *error?SAVE_ERROR:SAVE_OK;}
}
struct Appearance{bool changed;bool dirty(){return changed;}};
Appearance gBinds,gInputDisplay,gMetadataDisplay,gQftDisplay,gCreationExtras;
namespace MarioColors{bool dirty(){return false;}}
namespace FluddColors{bool dirty(){return false;}}
struct Settings{
 SettingsSaveState mSaveState;u32 mSaveSeq,mSaveWaitFrames,mLastError;bool mDirty;
 SettingsSaveState saveState(){return mSaveState;}SettingsSaveState pollSave();
 u32 lastError(){return mLastError;}bool dirty(){return mDirty;}
 void save(){stagedValue=liveValue;++writes;++mSaveSeq;mSaveState=SETTINGS_SAVE_PENDING;mDirty=false;gCreationExtras.changed=false;}
}gSettings;
struct MenuTab{bool ownsInput;bool grabsInput(){return ownsInput;}}tab;
struct Menu{
 bool mShown,mSaveWatch;int mCurTab,mToastFrames;char mToastBuf[64];MenuTab*mTabs[1];
 static const int kToastFrames=180;
 void toast(const char*s){unsigned i=0;while(s[i]&&i<63){mToastBuf[i]=s[i];++i;}mToastBuf[i]=0;mToastFrames=kToastFrames;}
 void pollSettingsSave();void requestSettingsSave();
}menu;
const char*settingsStorageError(u32){return "storage error";}
int snprintf(char*out,__SIZE_TYPE__ capacity,const char*text,...){unsigned i=0;while(text[i]&&i+1<capacity){out[i]=text[i];++i;}out[i]=0;return i;}
''' + function_source(ROOT/('src/settings_emulator.cpp' if cls.backend else 'src/settings.cpp'), 'SettingsSaveState Settings::pollSave()') + '\n' + function_source(ROOT/'src/menu.cpp', 'void Menu::requestSettingsSave()') + '\n' + function_source(ROOT/'src/menu.cpp', 'void Menu::pollSettingsSave()') + r'''
static u32 backup;static bool dirtyBefore;
#define API extern "C" __declspec(dllexport)
API void reset(){liveValue=10;stagedValue=diskValue=writes=0;backup=0;dirtyBefore=false;
 gSettings.mDirty=gBinds.changed=gInputDisplay.changed=gMetadataDisplay.changed=gQftDisplay.changed=gCreationExtras.changed=false;
 gSettings.mSaveState=SETTINGS_SAVE_IDLE;gSettings.mSaveSeq=gSettings.mSaveWaitFrames=gSettings.mLastError=0;
 cfg.ackSeq=cfg.status=0;tab.ownsInput=false;menu.mTabs[0]=&tab;
 menu.mCurTab=menu.mToastFrames=0;menu.mShown=true;menu.mSaveWatch=false;menu.mToastBuf[0]=0;}
API void start(){menu.requestSettingsSave();}
API void preview(u32 value){backup=liveValue;dirtyBefore=gCreationExtras.changed;tab.ownsInput=true;
 liveValue=value;gCreationExtras.changed=true;}
API void complete(u32 error){cfg.ackSeq=gSettings.mSaveSeq;cfg.status=error;
 if(!error)diskValue=stagedValue;menu.pollSettingsSave();}
API void poll(){menu.pollSettingsSave();}
API void finish(u32 keep){if(!keep){liveValue=backup;gCreationExtras.changed=dirtyBefore;}
 tab.ownsInput=false;menu.pollSettingsSave();}
API void change_setting(u32 value){liveValue=value;gSettings.mDirty=true;}
API void expire_retry(){gSettings.mSaveWaitFrames=0;}
API u32 get(u32 key){switch(key){case 0:return liveValue;case 1:return stagedValue;case 2:return diskValue;
 case 3:return writes;case 4:return menu.mSaveWatch;case 5:return gSettings.mSaveState;case 6:return gCreationExtras.changed;
 case 7:return menu.mToastFrames;}return 0;}
'''
        path = Path(cls.temp.name)/'preview.cpp'
        path.write_text(source)
        proc = subprocess.run([str(ROOT/'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
            '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2', '-fno-builtin',
            str(path), '-o', str(path.with_suffix('.dll'))], capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(proc.stdout + proc.stderr)
        cls.lib = C.CDLL(str(path.with_suffix('.dll')))
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def setUp(self):
        self.lib.reset()

    def test_ack_during_preview_then_cancel_keeps_only_original_save(self):
        self.lib.start()
        self.lib.preview(99)
        self.lib.complete(0)
        for _ in range(3):
            self.lib.poll()
        self.assertEqual([self.lib.get(i) for i in (0,1,2,3,4,6)], [99,10,10,1,1,1])
        self.lib.finish(0)
        self.assertEqual([self.lib.get(i) for i in (0,1,2,3,4,6)], [10,10,10,1,0,0])

    def test_ack_during_preview_then_keep_saves_confirmed_value_once(self):
        self.lib.start()
        self.lib.preview(99)
        self.lib.complete(0)
        self.lib.finish(1)
        self.assertEqual([self.lib.get(i) for i in (1,2,3,4,5)], [99,10,2,1,1])
        self.lib.complete(0)
        self.lib.poll()
        self.assertEqual([self.lib.get(i) for i in (0,2,3,4)], [99,99,2,0])

    def test_pending_write_and_error_ack_wait_for_preview_to_finish(self):
        self.lib.start()
        self.lib.preview(99)
        self.lib.poll()
        self.assertEqual([self.lib.get(i) for i in (2,3,4,5)], [0,1,1,1])
        self.lib.complete(1)
        self.assertEqual([self.lib.get(i) for i in (2,3,4,5)], [0,1,1,1])
        self.lib.finish(0)
        self.assertEqual([self.lib.get(i) for i in (2,3,4,7)], [0,1,0,180])

    def test_error_retry_does_not_stage_preview_values(self):
        self.lib.start()
        self.lib.complete(1)
        self.lib.preview(99)
        self.lib.expire_retry()
        self.lib.poll()
        self.assertEqual([self.lib.get(i) for i in (1,2,3)], [10,0,1])
        self.lib.finish(0)
        self.assertEqual([self.lib.get(i) for i in (1,2,3)], [10,0,2])

    def test_committed_setting_correction_outside_editor_still_requeues(self):
        self.lib.start()
        self.lib.change_setting(27)
        self.lib.complete(0)
        self.assertEqual([self.lib.get(i) for i in (1,2,3,5)], [27,10,2,1])
        self.lib.complete(0)
        self.assertEqual([self.lib.get(i) for i in (2,3,4)], [27,2,0])


class SettingsPreviewSaveDolphinTests(SettingsPreviewSaveTests):
    backend = 1


if __name__ == '__main__':
    unittest.main()
