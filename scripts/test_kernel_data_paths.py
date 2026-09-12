"""Check journal path bounds against every format used by the ARM worker."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class KernelDataPathTests(unittest.TestCase):
    def test_all_journal_names_fit_both_storage_prefixes(self):
        source = (ROOT / 'launcher/kernel/SusamuneCfg.c').read_text()
        capacity = int(re.search(r'#define SUSAMUNE_PB_PATH_SIZE\s+(\d+)', source)[1])
        paths = set(re.findall(r'"(%s/moonshine_[^"]+)"', source))
        self.assertEqual(len(paths), 30)
        for prefix in ('/Moonshine data', '1:/Moonshine data'):
            for template in paths:
                arguments = (prefix, 'pal') if template.count('%s') == 2 else (prefix,)
                path = template % arguments
                with self.subTest(path=path):
                    self.assertLess(len(path), capacity)
                    self.assertTrue(path.startswith(prefix + '/moonshine_'))
        self.assertNotIn('"%s/susamune_', source)


if __name__ == '__main__':
    unittest.main()
