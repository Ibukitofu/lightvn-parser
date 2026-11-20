# -*- coding: utf-8 -*-
"""Guards the field-count caliber: DISPLAY_UNSAFE must never be counted as DISPLAY."""
import unittest

from .fixtures import ScratchDirTest, Q


class DisplayCaliberTest(ScratchDirTest):

    def setUp(self):
        super().setUp()
        import lvparse
        self._lvparse = lvparse
        self._original = lvparse.jp_dir

    def tearDown(self):
        self._lvparse.jp_dir = self._original
        import schema
        schema._PROJECT_MACRO_NAMES = None
        schema._PROJECT_MACRO_KEY = None
        super().tearDown()

    def _make_file(self):
        # 武器表示 is displayed through {{...}} and also feeds a resource path,
        # so its assignment must be DISPLAY_UNSAFE, not DISPLAY.
        return self.write('c.txt', [
            '保存変数 武器表示 = ' + Q + '剣' + Q,
            '文字 t 1 2 3 a.ttf 20 ' + Q + '{{武器表示}}' + Q,
            '保存変数 パス = ' + Q + '{{武器表示}}' + Q,
            '画像 cg cg/{{パス}}.png',
        ])

    def test_unsafe_assignment_is_not_display(self):
        import lvscan

        self._make_file()
        roles = []
        for pf in lvscan.iter_files(self._tmp):
            for _pl, field, _line in pf.fields():
                roles.append(field.role)

        self.assertIn('DISPLAY_UNSAFE', roles)
        self.assertNotIn('DISPLAY_UNSAFE', lvscan.FP.DISPLAY_ROLES)

    def test_display_roles_constant_is_explicit(self):
        import field_parser as FP

        self.assertEqual(
            set(FP.DISPLAY_ROLES),
            {'DISPLAY', 'DISPLAY_CONTINUATION', 'DISPLAY_INFERRED'},
        )
        self.assertNotIn('DISPLAY_UNSAFE', FP.DISPLAY_ROLES)


if __name__ == '__main__':
    unittest.main()
