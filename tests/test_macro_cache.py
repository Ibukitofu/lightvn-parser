# -*- coding: utf-8 -*-
"""Regression test: the macro cache must switch between two real directories."""
import os
import unittest

from .fixtures import ScratchDirTest, Q


class MacroCacheTwoDirsTest(ScratchDirTest):
    """Two directories with different macro sets must not leak into each other."""

    def setUp(self):
        super().setUp()
        import lvparse
        self._lvparse = lvparse
        self._original = lvparse.jp_dir
        self.dir_a = os.path.join(self._tmp, 'a')
        self.dir_b = os.path.join(self._tmp, 'b')
        os.makedirs(self.dir_a, exist_ok=True)
        os.makedirs(self.dir_b, exist_ok=True)
        with open(os.path.join(self.dir_a, 'm.txt'), 'w', encoding='utf-8') as fh:
            fh.write('マクロ ' + Q + '~AlphaOnly' + Q + ' ' + Q + '~jump_a' + Q + chr(10))
        with open(os.path.join(self.dir_b, 'm.txt'), 'w', encoding='utf-8') as fh:
            fh.write('マクロ ' + Q + '~BetaOnly' + Q + ' ' + Q + '~jump_b' + Q + chr(10))

    def tearDown(self):
        self._lvparse.jp_dir = self._original
        import schema
        schema._PROJECT_MACRO_NAMES = None
        schema._PROJECT_MACRO_KEY = None
        super().tearDown()

    def test_two_directories_have_different_macros(self):
        import schema

        self._lvparse.jp_dir = lambda: self.dir_a
        names_a = schema._project_macro_names()
        self.assertIn('AlphaOnly', names_a)
        self.assertNotIn('BetaOnly', names_a)

        self._lvparse.jp_dir = lambda: self.dir_b
        names_b = schema._project_macro_names()
        self.assertIn('BetaOnly', names_b)
        self.assertNotIn('AlphaOnly', names_b)

        # and switching back must recompute again, not keep B
        self._lvparse.jp_dir = lambda: self.dir_a
        again_a = schema._project_macro_names()
        self.assertIn('AlphaOnly', again_a)
        self.assertNotIn('BetaOnly', again_a)

    def test_macro_call_parses_as_command_after_switch(self):
        import schema
        import field_parser as FP

        self._lvparse.jp_dir = lambda: self.dir_b
        schema._project_macro_names()
        parsed = FP.parse_line('~BetaOnly')
        self.assertEqual(parsed.kind, 'command')

        self._lvparse.jp_dir = lambda: self.dir_a
        schema._project_macro_names()
        parsed = FP.parse_line('~BetaOnly')
        self.assertEqual(parsed.kind, 'unknown',
                         'BetaOnly must stop being a command once dir B is gone')


if __name__ == '__main__':
    unittest.main()
