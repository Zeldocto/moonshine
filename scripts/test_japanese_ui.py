"""Exercise the shipped asset validator, lookup and bounded texture cache."""
import ctypes as C
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
import zlib

from gen_japanese_ui import build, catalogue, expand, TOKENS, JA_TOKENS, MAX_SIZE

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class JapaneseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset, cls.report = build()
        cls.work = tempfile.TemporaryDirectory(prefix='moonshine-ja-')
        work = Path(cls.work.name)
        source = (ROOT/'src/japanese_ui.cpp').read_text()
        harness = '''
#include "susamune/japanese_ui.h"
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;
static const u8 *sAsset, *sProbeAsset; static bool sChecked;
static u16 sCacheIds[64]; static u8 sCache[64][128];
static unsigned int sNext, barriers, flushes, invalidations;
#define IS_EMULATOR 0
#undef SUSAMUNE_JP_UI_PPC_BASE
#define SUSAMUNE_JP_UI_PPC_BASE sProbeAsset
static void GXDrawDone() {++barriers;}
static void DCFlushRange(void *, unsigned int n) {if(n==128)++flushes;}
static void GXInvalidateTexAll() {++invalidations;}
extern "C" void *memset(void *p,int v,__SIZE_TYPE__ n) {volatile u8 *b=(volatile u8*)p;while(n--)*b++=v;return p;}
'''
        for signature in ('bool ready()', 'unsigned int word(', 'unsigned int nextCode(', 'int glyph(',
                          'int units(', 'u8 *image(', 'const char *text(', 'const char *fitLine('):
            harness += function(source, signature)+'\n'
        harness += '''
extern "C" {
__declspec(dllexport) int valid(const u8 *p,unsigned int n) {return SusamuneJpUiValid(p,n);}
__declspec(dllexport) void reset(const u8 *p,unsigned int n) {
 sAsset=nullptr;sProbeAsset=p;sChecked=false;ready();sNext=barriers=flushes=invalidations=0;
 for(unsigned int i=0;i<64;++i)sCacheIds[i]=0;
}
__declspec(dllexport) const char *lookup(const char *p) {return text(p);}
__declspec(dllexport) int measure(const char *p) {return units(p);}
__declspec(dllexport) const char *line(const char *p,char *out,unsigned int n,int max,int size) {return fitLine(p,out,n,max,size);}
__declspec(dllexport) const u8 *getImage(int id) {return image(id);}
__declspec(dllexport) unsigned int counts(unsigned int which) {return which==0?barriers:which==1?flushes:invalidations;}
}
'''
        (work/'test.cpp').write_text(harness)
        command = [str(ROOT/'toolchain/clang++.exe'), '--target=x86_64-pc-windows-msvc',
                   '-shared', '-nostdlib', '-fuse-ld=lld', '-Wl,/noentry', '-O2',
                   '-I'+str(ROOT/'include'), str(work/'test.cpp'), '-o', str(work/'test.dll')]
        subprocess.run(command, check=True, capture_output=True)
        cls.lib = C.CDLL(str(work/'test.dll'))
        cls.lib.valid.argtypes = [C.c_void_p,C.c_uint]
        cls.lib.reset.argtypes = [C.c_void_p,C.c_uint]
        cls.lib.lookup.argtypes = [C.c_char_p]; cls.lib.lookup.restype = C.c_char_p
        cls.lib.measure.argtypes = [C.c_char_p]; cls.lib.measure.restype = C.c_int
        cls.lib.line.argtypes = [C.c_char_p,C.c_void_p,C.c_uint,C.c_int,C.c_int]
        cls.lib.line.restype = C.c_void_p
        cls.lib.getImage.argtypes = [C.c_int];cls.lib.getImage.restype = C.c_void_p
        cls.lib.counts.argtypes = [C.c_uint];cls.lib.counts.restype = C.c_uint
        cls.buffer = C.create_string_buffer(bytes(cls.asset))

    @classmethod
    def tearDownClass(cls):
        import _ctypes
        _ctypes.FreeLibrary(cls.lib._handle)
        cls.work.cleanup()

    def setUp(self):
        self.lib.reset(self.buffer,len(self.asset))

    def test_asset_bounded_and_reproducible(self):
        self.assertEqual(self.asset,build()[0])
        self.assertLessEqual(len(self.asset),MAX_SIZE)
        self.assertEqual(len(self.asset)%32,0)
        self.assertTrue(self.lib.valid(self.buffer,len(self.asset)))

    def test_entire_catalogue_roundtrips_through_production_lookup(self):
        for line in (ROOT/'data/japanese_ui.tsv').read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'):continue
            en,ja=line.split('\t')
            self.assertEqual(self.lib.lookup(expand(en,TOKENS)),expand(ja,JA_TOKENS),en)

    def test_unknown_text_and_missing_asset_preserve_english(self):
        self.assertEqual(self.lib.lookup(b'User custom text 987'),b'User custom text 987')
        broken=C.create_string_buffer(b'\0'*64)
        self.lib.reset(broken,64)
        self.assertEqual(self.lib.lookup(b'Practice'),b'Practice')
        self.assertEqual(self.lib.measure('日本語'.encode('cp932')),-1)

    def test_release_identity_is_japanese_only_with_the_japanese_asset(self):
        translated = self.lib.lookup(b'Moonshine')
        self.assertEqual(translated, 'Moonshine 日本語版'.encode('cp932'))
        self.assertEqual(self.lib.lookup(b'Moonshine guide'), 'Moonshineガイド'.encode('cp932'))
        self.assertEqual(self.lib.lookup(b'V2.3.1 Frame By Frame'), b'V2.3.1 Frame By Frame')
        # Leave at least a full-cell allowance for every version character.
        title_width = (self.lib.measure(translated) * 20 + 23) // 24
        self.assertLess(title_width + len('V2.3.1 Frame By Frame') * 12 + 12, 560 - 2 * 18)
        stale = C.create_string_buffer(bytes(64) + bytes(self.asset[64:]))
        self.lib.reset(stale, len(self.asset))
        self.assertEqual(self.lib.lookup(b'Moonshine'), b'Moonshine')
        self.assertEqual(self.lib.lookup(b'Moonshine guide'), b'Moonshine guide')

    def test_zeroed_ready_header_keeps_entire_catalogue_english_after_previous_japanese_boot(self):
        self.assertNotEqual(self.lib.lookup(b'Practice'),b'Practice')
        # The previous payload can remain in the staging tail; only its header is cleared.
        stale=C.create_string_buffer(bytes(64)+bytes(self.asset[64:]))
        self.lib.reset(stale,len(self.asset))
        for line in (ROOT/'data/japanese_ui.tsv').read_text(encoding='utf-8').splitlines():
            if not line.strip() or line.startswith('#'):continue
            english=expand(line.split('\t')[0],TOKENS)
            self.assertEqual(self.lib.lookup(english),english)
            self.assertEqual(self.lib.measure(english),-1)
        # An asset appearing later cannot silently change language during the same boot.
        C.memmove(stale,bytes(self.asset),len(self.asset))
        self.assertEqual(self.lib.lookup(b'Practice'),b'Practice')
        self.lib.reset(stale,len(self.asset))
        self.assertNotEqual(self.lib.lookup(b'Practice'),b'Practice')

    def test_all_asset_sections_are_covered_by_crc(self):
        for offset in (0,4,8,12,16,63,64,19000,45000,len(self.asset)-1):
            bad=bytearray(self.asset);bad[offset]^=1
            self.assertFalse(self.lib.valid(C.create_string_buffer(bytes(bad)),len(bad)),offset)
        for size in (0,32,63,len(self.asset)-1,len(self.asset)+1,MAX_SIZE+1):
            self.assertFalse(self.lib.valid(self.buffer,size),size)

    def test_rechecks_structural_bounds_even_with_repaired_crc(self):
        for offset,value in ((20,0xFFFFFFFF),(24,0),(28,65536),(32,0),(36,0xFFFFFFFF),
                             (40,0),(44,24),(48,128),(52,1),(56,1),(60,1)):
            bad=bytearray(self.asset);struct.pack_into('>I',bad,offset,value)
            struct.pack_into('>I',bad,12,0);struct.pack_into('>I',bad,12,zlib.crc32(bad))
            self.assertFalse(self.lib.valid(C.create_string_buffer(bytes(bad)),len(bad)),offset)

    def test_texture_cache_matches_every_packed_glyph_with_one_barrier_per_wrap(self):
        header=struct.unpack_from('>16I',self.asset)
        for i in range(header[9]):
            raw=self.asset[header[10]+i*64:header[10]+(i+1)*64]
            coverage=(0,7,12,15)
            expected=bytes(v for b in raw for v in ((coverage[b>>6]<<4)|coverage[b>>4&3],(coverage[b>>2&3]<<4)|coverage[b&3]))
            self.assertEqual(C.string_at(self.lib.getImage(i),128),expected)
            self.lib.getImage(i)
        self.assertEqual(self.lib.counts(0),(header[9]-1)//64)
        self.assertEqual(self.lib.counts(1),header[9])
        self.assertEqual(self.lib.counts(2),header[9])

    def test_measurement_uses_font_widths_and_rejects_unknown_or_truncated_codes(self):
        self.assertGreater(self.lib.measure('日本語'.encode('cp932')),0)
        self.assertEqual(self.lib.measure(b'ASCII remains the retail font'),-1)
        self.assertEqual(self.lib.measure(b'\x82'),-1)
        self.assertEqual(self.lib.measure(b'\xff\xff'),-1)

    def test_approved_wording_is_presentation_only(self):
        expected={'Force plaza events':'ドルピックタウンイベントの強制再生',
                  'PB popup':'記録更新時に通知','Expert Spider Bouncer':'アメンボ跳びの達人',
                  'Coconut King':'ヤシの実王','Plungelo Plucker':'チュウハナ抜き'}
        for en,ja in expected.items():self.assertEqual(self.lib.lookup(en.encode()),ja.encode('cp932'))

    def test_rc1_wording_amendments(self):
        expected={'Left Bell':'西のベル','Right Bell':'東のベル','Grass Secret':'草原',
            'Gelato GBS':'マンマ ヤシ抜け','Mode':'モード切り替え','Run playlist':'プレイリストの開始',
            'Playlist entries':'選択されたプレイリスト','Clear playlist':'プレイリストの取り消し',
            'Built-in preset':'プリセットを構築','Load playlist':'プレイリストの読込',
            'Save playlist':'プレイリストの保存','Value widths':'値の幅','Field gap':'隙間',
            'Rollout display style':'起き上がりジャンプ表示スタイル','Dust display style':'着地からの入力間隔スタイル'}
        for en,ja in [('Bianco 3','ビアンコ3'),('Bianco 6','ビアンコ6'),('Ricco 4','リコ4'),
                      ('Gelato 1','マンマ1'),('Pinna 2','ピンナ2'),('Pinna 6','ピンナ6'),
                      ('Sirena 2','シレナ2'),('Sirena 4','シレナ4'),('Noki 6','マーレ6'),('Pianta 5','モンテ5')]:
            expected[en+' Full Reds']=ja+' 赤コイン(通し)'
        for en,ja in expected.items():
            with self.subTest(english=en):self.assertEqual(self.lib.lookup(en.encode()),ja.encode('cp932'))

    def test_readable_help_wraps_on_whole_glyphs_and_preserves_words(self):
        text='メタデータの値と Moonshine の表示位置を変更します。'.encode('cp932')
        source=C.create_string_buffer(text)
        remaining=C.addressof(source);parts=[]
        while C.string_at(remaining):
            out=C.create_string_buffer(32)
            next_=self.lib.line(C.cast(remaining,C.c_char_p),out,len(out),140,14)
            self.assertGreater(next_,remaining)
            out.value.decode('cp932')
            self.assertLessEqual(self.lib.measure(out.value)*14//24,140)
            self.assertNotIn(b'Moons',out.value.replace(b'Moonshine',b''))
            parts.append(out.value);remaining=next_
        self.assertEqual(b''.join(parts).replace(b' ',b''),text.replace(b' ',b''))
        for capacity in (0,1,2,3):
            out=C.create_string_buffer(b'guard!')
            self.lib.line(source,out,capacity,140,14)
            self.assertEqual(out.raw[capacity:],b'guard!\0'[capacity:])

    def test_translated_menu_help_fits_two_readable_lines(self):
        source=(ROOT/'src/menu.cpp').read_text()+(ROOT/'src/tas_menu.inc').read_text()
        literals=re.findall(r'"([^"\\\n]*)"',source)
        for literal in set(literals):
            translated=self.lib.lookup(literal.encode())
            if translated==literal.encode() or self.lib.measure(translated)<0:continue
            # Help sentences use prose punctuation, unlike labels and formatted values.
            if not literal.endswith('.') or '%' in literal:continue
            a=C.create_string_buffer(256);b=C.create_string_buffer(256)
            data=C.create_string_buffer(translated)
            rest=self.lib.line(data,a,len(a),512,14)
            end=self.lib.line(C.cast(rest,C.c_char_p),b,len(b),512,14)
            self.assertEqual(C.string_at(end),b'',literal)

    def test_tas_shortcuts_and_checkpoint_prompts_are_translated(self):
        labels=['TAS PROJECTS','Rename TAS project','Refresh','Checkpoint',
                'This replaces the checkpoint with your current position.',
                'A: replace checkpoint   B: keep it',
                'Hold new buttons, then release to save. C-stick cancels.']
        binds=(ROOT/'src/binds_descs.inc').read_text()
        labels+=re.findall(r'BIND_DESC\("(TAS:[^"]+)"',binds)
        self.assertEqual(len(labels),14)
        for label in labels:
            with self.subTest(label=label):
                translated=self.lib.lookup(label.encode())
                self.assertNotEqual(translated,label.encode())
                self.assertGreater(self.lib.measure(translated),0)
        formats={b'%lu / %lu frames':('%lu / %luコマ',32),
                 b'Replace %s?':('%sを置き換えますか？',64),
                 b'Shortcut: %s   X: change   Z: clear':('割当：%s　X：変更　Z：解除',128)}
        for english,(japanese,capacity) in formats.items():
            translated=self.lib.lookup(english)
            self.assertEqual(translated,japanese.encode('cp932'))
            sample=translated.replace(b'%lu',b'4096').replace(b'%s',self.lib.lookup(b'Checkpoint 1'))
            self.assertLess(len(sample),capacity)
            self.assertGreater(self.lib.measure(sample),0)

    def test_current_navigation_has_translated_labels(self):
        source = (ROOT/'src/menu.cpp').read_text()
        category = source[source.index('const char kCategoryTitles'):source.index('enum CategoryTitleOffset')]
        labels = ''.join(re.findall(r'"([^"]+)"', category)).split(r'\0')
        pages = source[source.index('const SettingPage kGameplayPages'):source.index('const char *settingHelp')]
        labels += re.findall(r'\{"([^"\\]+)",', pages)
        labels += ['Quick','Practice','Runs','Records','Ghosts','Display','System',
                   'ILs','Stage Loader','PB Safety','Layout editor','Button binds',
                   'Moonshine guide','Frame advance','Free camera','Input replay (experimental)',
                   'Timers','Controller inputs','Metadata','Native HUD colours','Custom text',
                   'Practice feedback','Menu and notifications','Save latest ghost',
                   'Achievements  >','Statistics overview  >','Worlds  >']
        for label in labels:
            with self.subTest(label=label):
                translated=self.lib.lookup(label.encode())
                self.assertNotEqual(translated,label.encode())
                if any(byte >= 128 for byte in translated):
                    self.assertGreater(self.lib.measure(translated),0)

    def test_jp_disc_asset_is_raw_and_outside_both_dol_sections(self):
        from gen_iso_bps import build_operations
        layout=json.loads((ROOT/'data/iso_layout_jp.json').read_text())
        layout['japanese_ui']={'offset':0x004AA8C0,'size':MAX_SIZE}
        manifest={'base_addr':layout['base_addr'],'writes':[],
                  'segments':[{'offset':0,'memory_size':0x57000,'code':'00'*32},
                              {'offset':0x80000,'memory_size':0x3F000,'code':'00'*32}]}
        operations=build_operations(layout,manifest,ui_language='ja')
        literals=[o for o in operations if o['kind']=='literal' and o['target_offset']==0x004AA8C0]
        self.assertEqual(len(literals),1)
        self.assertEqual(literals[0]['value'],self.asset)
        self.assertLessEqual(layout['dol']['iso_offset']+layout['dol']['size']+0x97000,0x004AA8C0)
        for region in ('us','pal'):
            other=json.loads((ROOT/f'data/iso_layout_{region}.json').read_text())
            manifest['base_addr']=other['base_addr']
            self.assertFalse(any(o['kind']=='literal' and o['value']==self.asset
                                 for o in build_operations(other,manifest)))
        for field,value in (('offset',0x004AA8C4),('size',MAX_SIZE+32)):
            changed=json.loads(json.dumps(layout));changed['japanese_ui'][field]=value
            with self.assertRaises(ValueError):build_operations(changed,manifest)

    def test_disc_extent_only_replaces_a_file_already_relocated_in_full(self):
        layout=json.loads((ROOT/'data/iso_layout_jp.json').read_text())
        start,end=0x004AA8C0,0x004AA8C0+MAX_SIZE
        self.assertTrue(any(f['source_offset']<=start and
                            end<=f['source_offset']+f['size'] for f in layout['relocated_files']))
        self.assertEqual(layout['mod_region_size'],0xA0000)


if __name__=='__main__':unittest.main()
