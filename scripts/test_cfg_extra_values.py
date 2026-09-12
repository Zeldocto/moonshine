"""Check appended settings against the real wire, value loops and CARD record."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_timer_creation import function

ROOT = Path(__file__).resolve().parents[1]


class ExtraSettingValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang++.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled host compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-extra-settings-')
        cls.addClassCleanup(cls.temp.cleanup)
        settings = (ROOT/'src/settings.cpp').read_text()
        card = (ROOT/'src/emulator_persistence.cpp').read_text()
        code = r'''
#define private public
#include "susamune/settings.hxx"
#undef private
#include "susamune/susamune_cfg.h"
#include "susamune/packed_text.hxx"
#define SUSAMUNE_GAME_VERSION 2
int snprintf(char*,__SIZE_TYPE__,const char*,...){return 0;}
extern "C" void*memcpy(void*d,const void*s,__SIZE_TYPE__ n){u8*a=(u8*)d;const u8*b=(const u8*)s;while(n--)*a++=*b++;return d;}
extern "C" void*memset(void*d,int c,__SIZE_TYPE__ n){u8*a=(u8*)d;while(n--)*a++=(u8)c;return d;}
'''
        code += settings[settings.index('namespace {'):settings.index('Settings &gSettings')]
        code += function(settings, 'Settings::set')
        code += function(settings, 'Settings::cycle')
        code += function(settings, 'Settings::valueLabel')
        defaults = function(settings, 'Settings::resetDefaults')
        code += 'void Settings::resetDefaults(){' + defaults[defaults.index('    for (int i'):]
        adopt = function(settings, 'Settings::adopt')
        code += adopt[:adopt.index('    // Binds, same deal.')] + '}\n'
        stage = function(settings, 'Settings::stageInto')
        code += stage[:stage.index('    gBinds.stageInto')] + '}\n'
        code += card[card.index('constexpr u32 kRecordMagic'):card.index('struct RecordV1')]
        code += function(card, 'checksum') + function(card, 'valid')
        code += r'''
static Settings settings;
static SusamuneCfg cfg;
static Record record;
#define API extern "C" __declspec(dllexport)
API void reset(unsigned count){settings.resetDefaults();memset(&cfg,0xa5,sizeof(cfg));cfg.count=count;}
API unsigned write(unsigned index,unsigned value){return SusamuneCfgSetSetting(&cfg,index,(u8)value);}
API unsigned read(unsigned index){return SusamuneCfgGetSetting(&cfg,index);}
API unsigned get(unsigned index){return settings.get((SettingId)index);}
API void set(unsigned index,unsigned value){settings.set((SettingId)index,(u8)value);}
API void adopt(){settings.adopt(&cfg);}
API void stage(){settings.stageInto(&cfg);}
API unsigned byteAt(unsigned index){return ((u8*)&cfg)[index];}
API unsigned size(){return sizeof(cfg);}
API unsigned count(){return cfg.count;}
API unsigned smoothingId(){return SETTING_FREE_CAMERA_SMOOTHING;}
API void cycle(unsigned index,int direction){settings.cycle((SettingId)index,direction);}
API const char*label(unsigned index){return settings.valueLabel((SettingId)index);}
API unsigned cardRoundtrip(unsigned oldCount){
 memset(&record,0,sizeof(record));record.magic=kRecordMagic;record.version=kRecordVersion;
 record.payloadSize=kRecordPayloadSize;record.gameVersion=SUSAMUNE_GAME_VERSION;
 settings.stageInto(&record.cfg);record.cfg.magic=SUSAMUNE_CFG_MAGIC;record.cfg.version=SUSAMUNE_CFG_VERSION;
 if(oldCount){record.cfg.count=128;memset(record.cfg.extraValues,0x7f,sizeof(record.cfg.extraValues));}
 record.checksum=checksum(&record);if(!valid(&record))return 0;
 settings.resetDefaults();settings.adopt(&record.cfg);return 1;
}
API unsigned corruptExtra(unsigned i){record.cfg.extraValues[i]^=1;return valid(&record);}
'''
        path = Path(cls.temp.name)/'test.cpp'
        path.write_text(code)
        result = subprocess.run([str(compiler),'--target=x86_64-pc-windows-msvc','-shared','-nostdlib',
            '-fuse-ld=lld','-Wl,/noentry','-O2','-fno-builtin','-mno-stack-arg-probe',
            '-I',str(ROOT/'include'),'-I',str(ROOT/'src'),str(path),
            str(ROOT/'src/packed_text.cpp'),'-o',str(path.with_suffix('.dll'))],
            capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        cls.lib = C.CDLL(str(path.with_suffix('.dll')))
        cls.lib.label.restype = C.c_char_p
        cls.addClassCleanup(lambda:C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))

    def test_wire_boundaries_preserve_bind_and_ack_cache_lines(self):
        self.lib.reset(130)
        self.assertEqual(self.lib.size(), 5152)
        for i in range(142):
            self.assertEqual(self.lib.write(i, i), 1)
            self.assertEqual(self.lib.read(i), i)
            self.assertEqual(self.lib.byteAt(i+64 if i<128 else i-128+18), i)
        before = bytes(self.lib.byteAt(i) for i in range(5152))
        for i in (142, 143, 65535, 0xffffffff):
            self.assertEqual(self.lib.write(i, 7), 0)
            self.assertEqual(self.lib.read(i), 255)
        self.assertEqual(bytes(self.lib.byteAt(i) for i in range(5152)), before)
        self.assertEqual(before[32:64], b'\xa5'*32)
        self.assertEqual(before[192:], b'\xa5'*(5152-192))

    def test_old_count_and_unset_keep_defaults_while_new_count_clamps_values(self):
        for count in (0, 128):
            self.lib.reset(count)
            self.lib.write(128, 4)
            self.lib.write(129, 1)
            self.lib.adopt()
            self.assertEqual([self.lib.get(i) for i in (128,129)], [2,0])
        for count in (130, 142, 65535):
            self.lib.reset(count)
            self.lib.write(128, 254)
            self.lib.write(129, 254)
            self.lib.adopt()
            self.assertEqual([self.lib.get(i) for i in (128,129)], [4,0])
            self.lib.reset(count)
            self.lib.write(128, 255)
            self.lib.write(129, 255)
            self.lib.adopt()
            self.assertEqual([self.lib.get(i) for i in (128,129)], [2,0])

    def test_staging_places_extra_settings_in_header_and_never_overwrites_binds(self):
        self.lib.reset(128)
        self.lib.set(128, 4)
        self.lib.set(129, 1)
        self.lib.stage()
        self.assertEqual(self.lib.count(), 140)
        self.assertEqual([self.lib.read(i) for i in (128,129)], [4,1])
        self.assertEqual(bytes(self.lib.byteAt(i) for i in range(192,320)), b'\xa5'*128)

    def test_current_card_roundtrip_and_older_count_defaults_with_checksum_coverage(self):
        for older in (0,1):
            self.lib.reset(130)
            self.lib.set(128, 4)
            self.lib.set(129, 1)
            self.assertEqual(self.lib.cardRoundtrip(older), 1)
            self.assertEqual([self.lib.get(i) for i in (128,129)], [2,0] if older else [4,1])
            self.assertEqual(self.lib.corruptExtra(0), 0)

    def test_new_shined_banks_survive_wire_and_card_with_old_count_defaults(self):
        self.lib.reset(138)
        for index in range(130, 138):
            self.lib.set(index, 0x7f - index % 7)
        self.lib.stage()
        self.assertEqual([self.lib.read(i) for i in range(130, 138)],
                         [0x7f - i % 7 for i in range(130, 138)])
        self.assertEqual(self.lib.cardRoundtrip(0), 1)
        self.assertEqual([self.lib.get(i) for i in range(130, 138)],
                         [0x7f - i % 7 for i in range(130, 138)])
        self.lib.reset(130)
        self.lib.adopt()
        self.assertEqual([self.lib.get(i) for i in range(130, 138)], [0] * 8)

    def test_banner_defaults_on_for_older_settings_and_persists_off(self):
        self.lib.reset(138)
        self.lib.adopt()
        self.assertEqual(self.lib.get(138), 1)
        self.lib.set(138, 0)
        self.lib.stage()
        self.assertEqual(self.lib.count(), 140)
        self.assertEqual(self.lib.read(138), 0)
        self.assertEqual(self.lib.cardRoundtrip(0), 1)
        self.assertEqual(self.lib.get(138), 0)

    def test_camera_smoothing_appends_off_default_and_persists_all_durations(self):
        setting = self.lib.smoothingId()
        self.assertEqual(setting, 139)
        self.lib.reset(139)
        self.lib.write(setting, 15)
        self.lib.adopt()
        self.assertEqual(self.lib.get(setting), 0)
        for value in range(16):
            self.lib.set(setting, value)
            expected = 'Off' if not value else '1 s' if value == 10 else f'{value / 10:.1f} s'
            self.assertEqual(self.lib.label(setting).decode(), expected)
            self.assertEqual(self.lib.cardRoundtrip(0), 1)
            self.assertEqual(self.lib.get(setting), value)
            self.lib.stage()
            self.assertEqual(self.lib.read(setting), value)
            self.assertEqual(self.lib.byteAt(29), value)
        self.lib.cycle(setting, 1)
        self.assertEqual(self.lib.get(setting), 0)
        self.lib.cycle(setting, -1)
        self.assertEqual(self.lib.get(setting), 15)
        self.lib.set(setting, 16)
        self.assertEqual(self.lib.get(setting), 0)

    def test_header_publication_and_kernel_ack_remain_on_their_owned_lines(self):
        settings = (ROOT/'src/settings.cpp').read_text()
        kernel = (ROOT/'launcher/kernel/SusamuneCfg.c').read_text()
        save = function(settings, 'Settings::save')
        self.assertLess(save.index('stageInto(cfg)'), save.index('cfg->saveSeq = mSaveSeq'))
        self.assertLess(save.index('cfg->saveSeq = mSaveSeq'), save.index('DCStoreRange((void *)cfg, 32)'))
        service = function(kernel, 'SusamuneCfgService')
        self.assertLess(service.index('sync_before_read(cfg, 32)'), service.index('WriteIniFile(cfg)'))
        self.assertIn('sync_after_write(&cfg->ackSeq, 32)', service)
        self.assertNotIn('sync_after_write(cfg,', service)


if __name__ == '__main__':
    unittest.main()
