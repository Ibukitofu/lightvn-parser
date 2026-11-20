# -*- coding: utf-8 -*-
"""The index must expose protected (visible but non-translatable) fields."""
import json
import os
import unittest

from .fixtures import ScratchDirTest, Q


class ProtectedIndexTest(ScratchDirTest):

    def test_protected_section_carries_evidence(self):
        import lvindex

        self.write('e.txt', [
            '保存変数 武器表示 = ' + Q + '剣' + Q,
            '文字 t 1 2 3 a.ttf 20 ' + Q + '{{武器表示}}' + Q,
            'もし (武器表示 == ' + Q + '剣' + Q + ') ジャンプ a.txt b',
        ])
        out = os.path.join(self._tmp, '_idx')
        result = lvindex.build(self._tmp, out)
        self.assertGreater(result['protected'], 0)

        with open(os.path.join(out, 'protected.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
        self.assertGreater(payload['count'], 0)
        item = payload['items'][0]
        self.assertEqual(item['role'], 'DISPLAY_UNSAFE')
        self.assertFalse(item['translatable'])
        self.assertEqual(item['variable'], '武器表示')
        self.assertIn('compared', item['reasons'])

    def test_protected_is_not_in_display(self):
        import lvindex

        self.write('e.txt', [
            '保存変数 武器表示 = ' + Q + '剣' + Q,
            '文字 t 1 2 3 a.ttf 20 ' + Q + '{{武器表示}}' + Q,
            'もし (武器表示 == ' + Q + '剣' + Q + ') ジャンプ a.txt b',
        ])
        out = os.path.join(self._tmp, '_idx2')
        lvindex.build(self._tmp, out)
        with open(os.path.join(out, 'display.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
        roles = [i['role'] for i in payload['items']]
        self.assertNotIn('DISPLAY_UNSAFE', roles,
                         'protected fields must not be counted as translatable display')


if __name__ == '__main__':
    unittest.main()
