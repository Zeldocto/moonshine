"""Drive production loader migration through the bundled FatFs and UTF-8 wrapper."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = '/Moonshine data'
MARKER = DATA + '/.layout-v1'


class DataMigrationFatFsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = ROOT / 'toolchain/clang.exe'
        if not compiler.exists():
            raise unittest.SkipTest('Bundled Windows compiler required')
        cls.temp = tempfile.TemporaryDirectory(prefix='moonshine-data-fatfs-')
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(cls.temp.name) / 'migration.c'
        headers = {
            'stdint.h': 'typedef unsigned char uint8_t;typedef unsigned short uint16_t;typedef unsigned int uint32_t;\n',
            'stdbool.h': '#define bool _Bool\n#define true 1\n#define false 0\n',
            'stddef.h': 'typedef __SIZE_TYPE__ size_t;\n#define NULL ((void*)0)\n',
            'string.h': 'void *memcpy(void*,const void*,__SIZE_TYPE__);\n',
        }
        for name, content in headers.items():
            (source.parent / name).write_text('#pragma once\n' + content)
        production = (ROOT / 'launcher/loader/source/MoonshineData.c').read_text()
        production = production.replace('#include <stdio.h>', '').replace('#include <string.h>', '')
        source.write_text('#include "data_migration_fixture.h"\n' + r'''
#define f_rename_char migration_rename
#define f_close migration_close
#define f_closedir migration_closedir
#define f_opendir_char migration_opendir
#define f_stat_char migration_stat
#define f_mkdir_char migration_mkdir
''' + production + r'''
API int prepare(const char*device){memset(stats,0,sizeof(stats));diskWrites[0]=diskWrites[1]=0;return MoonshineDataPrepare(device);}
''', encoding='utf-8')
        fatfs = ROOT / 'launcher/fatfs'
        library = source.with_suffix('.dll')
        result = subprocess.run([str(compiler), '--target=x86_64-pc-windows-msvc', '-U_WIN32',
            '-D__PPC__', '-shared', '-nostdlib', '-fno-builtin', '-mno-stack-arg-probe', '-O2',
            '-fuse-ld=lld', '-Wl,/noentry', '-I', str(source.parent), '-I', str(fatfs), '-I', str(ROOT / 'scripts'),
            '-I', str(ROOT / 'include'), '-I', str(ROOT / 'launcher/loader/include'),
            str(source), str(fatfs / 'ff.c'), str(fatfs / 'ff_utf8.c'),
            str(fatfs / 'option/ccsbcs.c'), '-o', str(library)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.lib = C.CDLL(str(library))
        cls.addClassCleanup(lambda: C.windll.kernel32.FreeLibrary(C.c_void_p(cls.lib._handle)))
        cls.lib.put.argtypes = [C.c_char_p, C.c_void_p, C.c_uint, C.c_uint]
        cls.lib.get.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]
        cls.lib.entries.argtypes = [C.c_char_p, C.c_void_p, C.c_uint]
        cls.lib.prepare.argtypes = [C.c_char_p]
        cls.lib.attributes.argtypes = cls.lib.mkdirs.argtypes = [C.c_char_p]
        cls.lib.fail.argtypes = [C.c_uint, C.c_uint]
        cls.lib.failRenamePath.argtypes = [C.c_char_p]

    def setUp(self):
        self.assertEqual(self.lib.reset(), 0)

    def put(self, path, data=b'preserved bytes', hidden=False):
        self.assertEqual(self.lib.put(path.encode(), data, len(data), hidden), 0, path)

    def get(self, path):
        data = C.create_string_buffer(65536)
        count = self.lib.get(path.encode(), data, len(data))
        return data.raw[:count] if count >= 0 else None

    def exists(self, path):
        return self.lib.attributes(path.encode()) >= 0

    def prepare(self, device='sd'):
        return self.lib.prepare(device.encode())

    def tree(self, path):
        names = C.create_string_buffer(65536)
        count = self.lib.entries(path.encode(), names, len(names))
        if count < 0:
            return {path: self.get(path)}
        out = {}
        for name in names.raw[:count].decode().splitlines():
            out.update(self.tree(path.rstrip('/') + '/' + name))
        return out

    def test_fresh_disk_and_marker_make_repeated_boot_read_only(self):
        for device in ('sd', 'usb'):
            with self.subTest(device=device):
                self.assertEqual(self.prepare(device), 0)
                self.assertEqual(self.get(device + ':' + MARKER), b'MSD1')
                self.assertEqual(self.lib.reboot(), 0)
                self.assertEqual(self.prepare(device), 0)
                self.assertEqual([self.lib.stat(i) for i in (0, 1, 2, 4, 5, 6)], [0] * 6)

    def test_all_recognized_journals_ini_chain_and_crash_files_keep_contents(self):
        names = ['susamune.ini' + suffix for suffix in ('', '.bak', '.tmp')]
        for copy in 'ab':
            names += [f'susamune_pbs_v{v}_{r}_{copy}.bin' for v in (1, 2) for r in ('jp', 'us', 'pal')]
            names += [f'susamune_stage_targets_{r}_{copy}.bin' for r in ('jp', 'us', 'pal')]
            names += [f'susamune_il_stats_v{v}_{copy}.bin' for v in range(1, 10)]
            names += [f'susamune_stage_playlists_v{v}_{copy}.bin' for v in (1, 2)]
            names += [f'susamune_progress_v1_{copy}.bin']
            names += [f'susamune_crash_{copy}.{ext}' for ext in ('txt', 'bin', 'core')]
        for name in names:
            self.put('sd:/' + name, name.encode() + b'\0\xff')
        self.assertEqual(self.prepare(), 0)
        self.assertEqual(self.lib.reboot(), 0)
        for name in names:
            destination = DATA + ('/crashes/' if '_crash_' in name else '/') + name.replace('susamune_', 'moonshine_').replace('susamune.ini', 'moonshine.ini')
            self.assertEqual(self.get('sd:' + destination), name.encode() + b'\0\xff')
            self.assertFalse(self.exists('sd:/' + name))

    def test_nested_hidden_and_unicode_files_merge_and_keep_unrelated_data(self):
        mappings = {'Moonshine_Theme': 'theme', 'susamune_backups': 'backups'}
        for old, new in mappings.items():
            self.put(f'sd:/{old}/nested/.hidden', old.encode(), hidden=True)
            self.put(f'sd:/{old}/nested/日本語.smsghost', new.encode())
            self.put(f'sd:{DATA}/{new}/nested/already.txt', b'new data')
        unrelated = {'sd:/Darkmoonshine/save.bin': b'luigi', 'sd:/games/Sunshine/game.iso': b'game',
                     'sd:/not_susamune_pbs_v2_pal_a.bin': b'unrelated', 'sd:/apps/other/boot.dol': b'app'}
        for path, contents in unrelated.items():
            self.put(path, contents)
        self.assertEqual(self.prepare(), 0)
        for old, new in mappings.items():
            base = f'sd:{DATA}/{new}/nested/'
            self.assertEqual(self.get(base + '.hidden'), old.encode())
            self.assertTrue(self.lib.attributes((base + '.hidden').encode()) & 2)
            self.assertEqual(self.get(base + '日本語.smsghost'), new.encode())
            self.assertEqual(self.get(base + 'already.txt'), b'new data')
            self.assertFalse(self.exists('sd:/' + old))
        for path, contents in unrelated.items():
            self.assertEqual(self.get(path), contents)

    def test_usb_migration_does_not_read_move_or_write_sd_data(self):
        self.put('sd:/susamune.ini', b'sd old')
        self.put('usb:/susamune.ini', b'usb old')
        self.put('usb:/moonshine_states/state_00000001.mss', b'usb state')
        self.assertEqual(self.prepare('usb'), 0)
        self.assertEqual(self.lib.writes(0), 0)
        self.assertEqual(self.get('sd:/susamune.ini'), b'sd old')
        self.assertFalse(self.exists('sd:' + DATA))
        self.assertEqual(self.get('usb:' + DATA + '/moonshine.ini'), b'usb old')
        self.assertEqual(self.get('usb:' + DATA + '/states/state_00000001.mss'), b'usb state')

    def test_collisions_preserve_new_files_and_all_old_ini_generations(self):
        expected = {}
        for suffix in ('.bak', '.tmp', ''):
            self.put('sd:/susamune.ini' + suffix, ('old' + suffix).encode())
            self.put('sd:' + DATA + '/moonshine.ini' + suffix, ('new' + suffix).encode())
            expected['susamune.ini' + suffix] = ('old' + suffix).encode()
        self.put('sd:/susamune_ghosts/import/same.smsghost', b'old ghost')
        self.put('sd:' + DATA + '/ghosts/import/same.smsghost', b'new ghost')
        expected['same.smsghost'] = b'old ghost'
        self.assertEqual(self.prepare(), 0)
        backups = {Path(path).name: data for path, data in self.tree('sd:' + DATA + '/backups').items()}
        self.assertEqual(backups, expected)
        for suffix in ('.bak', '.tmp', ''):
            self.assertEqual(self.get('sd:' + DATA + '/moonshine.ini' + suffix), ('new' + suffix).encode())
        self.assertEqual(self.get('sd:' + DATA + '/ghosts/import/same.smsghost'), b'new ghost')

    def test_failed_move_resumes_after_reboot_without_loss_or_early_marker(self):
        self.put('sd:' + DATA + '/theme/new.png', b'new')
        for i in range(4):
            self.put(f'sd:/Moonshine_Theme/image{i}.png', bytes([i]))
        self.lib.fail(1, 3)
        self.assertNotEqual(self.prepare(), 0)
        self.assertFalse(self.exists('sd:' + MARKER))
        self.assertEqual(self.get('sd:' + DATA + '/theme/image0.png'), b'\0')
        self.assertEqual(self.lib.reboot(), 0)
        self.lib.fail(0, 0)
        self.assertEqual(self.prepare(), 0)
        for i in range(4):
            self.assertEqual(self.get(f'sd:{DATA}/theme/image{i}.png'), bytes([i]))
        self.assertFalse(self.exists('sd:/Moonshine_Theme'))

    def test_existing_libraries_keep_each_legacy_catalog_coherent_in_backup(self):
        libraries = (
            ('susamune_ghosts', 'ghosts', ('jp/p0/g00a.sgh', 'jp/p0/g00b.sgh')),
            ('moonshine_states', 'states', ('state_00000001.mss', 'state_00000001.name0')),
            ('moonshine_tas', 'tas', ('tas_00000001/project.a', 'tas_00000001/project.b',
                                     'tas_00000001/state_00000001.mss')),
        )
        for old, new, leaves in libraries:
            with self.subTest(library=new):
                self.assertEqual(self.lib.reset(), 0)
                for leaf in leaves:
                    self.put(f'sd:/{old}/{leaf}', ('old ' + leaf).encode())
                self.put(f'sd:/{old}/.hidden', b'hidden catalog data', hidden=True)
                self.put(f'sd:{DATA}/{new}/{leaves[0]}', b'new catalog')
                self.assertEqual(self.prepare(), 0)
                self.assertEqual(self.tree(f'sd:{DATA}/{new}'),
                                 {f'sd:{DATA}/{new}/{leaves[0]}': b'new catalog'})
                backup = f'sd:{DATA}/backups/migration_0001/{old}'
                self.assertEqual(self.tree(backup),
                                 {**{backup + '/' + leaf: ('old ' + leaf).encode() for leaf in leaves},
                                  backup + '/.hidden': b'hidden catalog data'})
                self.assertTrue(self.lib.attributes((backup + '/.hidden').encode()) & 2)
                self.assertFalse(self.exists(f'sd:/{old}'))

    def test_empty_library_destinations_accept_whole_old_tree_and_retry_failed_rename(self):
        for old, new in (('susamune_ghosts', 'ghosts'), ('moonshine_states', 'states'),
                         ('moonshine_tas', 'tas')):
            with self.subTest(library=new):
                self.assertEqual(self.lib.reset(), 0)
                self.put(f'sd:/{old}/nested/日本語.bin', b'whole library')
                self.assertEqual(self.lib.mkdirs(f'sd:{DATA}/{new}'.encode()), 0)
                self.lib.failRenamePath(f'sd:/{old}'.encode())
                self.assertNotEqual(self.prepare(), 0)
                self.assertFalse(self.exists('sd:' + MARKER))
                self.assertEqual(self.get(f'sd:/{old}/nested/日本語.bin'), b'whole library')
                self.assertEqual(self.lib.reboot(), 0)
                self.lib.failRenamePath(b'')
                self.assertEqual(self.prepare(), 0)
                self.assertEqual(self.get(f'sd:{DATA}/{new}/nested/日本語.bin'), b'whole library')
                self.assertFalse(self.exists(f'sd:/{old}'))

    def test_existing_destination_ini_backup_cannot_be_shadowed_by_old_main(self):
        self.put('sd:' + DATA + '/moonshine.ini.bak', b'new layout settings')
        self.put('sd:/susamune.ini', b'legacy settings')
        self.assertEqual(self.prepare(), 0)
        self.assertNotEqual(self.get('sd:' + DATA + '/moonshine.ini'), b'legacy settings')
        files = self.tree('sd:' + DATA)
        self.assertIn(b'new layout settings', files.values())
        self.assertIn(b'legacy settings', files.values())

    def test_existing_destination_ini_temporary_cannot_mix_with_old_backup(self):
        self.put('sd:' + DATA + '/moonshine.ini.tmp', b'new pending settings')
        self.put('sd:/susamune.ini.bak', b'legacy backup')
        self.assertEqual(self.prepare(), 0)
        self.assertNotEqual(self.get('sd:' + DATA + '/moonshine.ini.bak'), b'legacy backup')
        files = self.tree('sd:' + DATA)
        self.assertIn(b'new pending settings', files.values())
        self.assertIn(b'legacy backup', files.values())

    def test_interrupted_old_ini_family_finishes_its_own_main_on_retry(self):
        self.put('sd:/susamune.ini.bak', b'legacy previous')
        self.put('sd:/susamune.ini', b'legacy latest')
        self.lib.failRenamePath(b'sd:/susamune.ini')
        self.assertNotEqual(self.prepare(), 0)
        self.assertFalse(self.exists('sd:' + MARKER))
        self.assertEqual(self.lib.reboot(), 0)
        self.lib.failRenamePath(b'')
        self.assertEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:' + DATA + '/moonshine.ini'), b'legacy latest')
        self.assertEqual(self.get('sd:' + DATA + '/moonshine.ini.bak'), b'legacy previous')

    def test_interrupted_family_publication_retains_its_decision_after_reboot(self):
        families = (
            ('ini', 'susamune.ini', 'moonshine.ini', ('.bak', '')),
            ('pbs_v2_jp', 'susamune_pbs_v2_jp', 'moonshine_pbs_v2_jp', ('_a.bin', '_b.bin')),
        )
        for family, old, new, suffixes in families:
            with self.subTest(family=family):
                self.assertEqual(self.lib.reset(), 0)
                for suffix in suffixes:
                    self.put('sd:/' + old + suffix, ('legacy ' + suffix).encode())
                source = f'sd:{DATA}/backups/legacy_{family}/{old}{suffixes[1]}'
                self.lib.failRenamePath(source.encode())
                self.assertNotEqual(self.prepare(), 0)
                self.assertEqual(self.get(f'sd:{DATA}/{new}{suffixes[0]}'),
                                 ('legacy ' + suffixes[0]).encode())
                self.assertFalse(self.exists('sd:' + MARKER))
                self.assertEqual(self.lib.reboot(), 0)
                self.lib.failRenamePath(b'')
                self.assertEqual(self.prepare(), 0)
                for suffix in suffixes:
                    self.assertEqual(self.get(f'sd:{DATA}/{new}{suffix}'), ('legacy ' + suffix).encode())

    def test_one_existing_journal_sibling_preserves_whole_old_family_in_backup(self):
        self.put(f'sd:{DATA}/moonshine_pbs_v2_jp_a.bin', b'new active A')
        for suffix in ('a', 'b'):
            self.put(f'sd:/susamune_pbs_v2_jp_{suffix}.bin', ('old ' + suffix).encode())
        self.assertEqual(self.prepare(), 0)
        self.assertEqual(self.get(f'sd:{DATA}/moonshine_pbs_v2_jp_a.bin'), b'new active A')
        self.assertFalse(self.exists(f'sd:{DATA}/moonshine_pbs_v2_jp_b.bin'))
        backup = f'sd:{DATA}/backups/legacy_pbs_v2_jp'
        self.assertEqual(self.tree(backup),
                         {f'{backup}/susamune_pbs_v2_jp_{suffix}.bin': ('old ' + suffix).encode()
                          for suffix in ('a', 'b')})

    def test_failed_directory_close_stops_before_moving_that_child(self):
        self.put('sd:/susamune_ghosts/old.smsghost', b'old')
        self.put('sd:' + DATA + '/ghosts/new.smsghost', b'new')
        self.lib.fail(3, 1)
        self.assertNotEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:/susamune_ghosts/old.smsghost'), b'old')
        self.assertFalse(self.exists('sd:' + MARKER))
        self.lib.fail(0, 0)
        self.assertEqual(self.prepare(), 0)

    def test_conflicting_file_and_directory_types_are_preserved_in_backup(self):
        self.put('sd:' + DATA + '/theme', b'existing file')
        self.put('sd:/Moonshine_Theme/night/background.png', b'old artwork')
        self.put('sd:/susamune_ghosts', b'old root file')
        self.put('sd:' + DATA + '/ghosts/import/new.smsghost', b'new ghost')
        self.assertEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:' + DATA + '/theme'), b'existing file')
        self.assertEqual(self.get('sd:' + DATA + '/ghosts/import/new.smsghost'), b'new ghost')
        self.assertCountEqual(self.tree('sd:' + DATA + '/backups').values(),
                              [b'old artwork', b'old root file'])

    def test_failed_read_marker_close_does_not_restart_migration_or_write(self):
        self.assertEqual(self.prepare(), 0)
        self.lib.fail(2, 1)
        self.assertNotEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:' + MARKER), b'MSD1')
        self.assertEqual([self.lib.stat(i) for i in (0, 1, 2, 4, 5, 6)], [0] * 6)

    def test_failed_marker_close_or_publication_never_marks_complete(self):
        for mode in (1, 2):
            with self.subTest(mode=mode):
                self.assertEqual(self.lib.reset(), 0)
                self.lib.fail(mode, 1)
                self.assertNotEqual(self.prepare(), 0)
                self.assertFalse(self.exists('sd:' + MARKER))
                self.assertEqual(self.lib.reboot(), 0)
                self.lib.fail(0, 0)
                self.assertEqual(self.prepare(), 0)
                self.assertEqual(self.get('sd:' + MARKER), b'MSD1')

    def test_invalid_marker_retries_and_root_file_collision_is_preserved(self):
        self.put('sd:' + MARKER, b'bad marker')
        self.put('sd:/susamune.ini', b'retry me')
        self.assertEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:' + DATA + '/moonshine.ini'), b'retry me')
        self.assertEqual(self.lib.reset(), 0)
        self.put('sd:' + DATA, b'user file')
        self.put('sd:/susamune.ini', b'keep old')
        self.assertNotEqual(self.prepare(), 0)
        self.assertEqual(self.get('sd:' + DATA), b'user file')
        self.assertEqual(self.get('sd:/susamune.ini'), b'keep old')


if __name__ == '__main__':
    unittest.main()
