# -*- coding: utf-8 -*-
"""Regression tests for the five issues found in review.

1. Project macros must load, so ~自由行動外 and friends are commands, not unknown.
2. A single space after a condition is normal syntax, not error recovery.
3. An indirect display (assignment rendered through {{name}}) must be translatable.
4. The role report must agree with the corpus-wide inference.
5. The index must contain document-level continuation fragments.
"""
import json
import os
import unittest

from .fixtures import ScratchDirTest, Q


class MacroLoadingTest(ScratchDirTest):

    def test_project_macros_become_commands(self):
        import schema
        import field_parser as FP

        names = schema._project_macro_names()
        if not names:
            self.skipTest('LV_JP not set or corpus has no macros')
        probe = sorted(names)[0]
        parsed = FP.parse_line('~' + probe)
        self.assertEqual(parsed.kind, 'command',
                         'project macro %r parsed as %r' % (probe, parsed.kind))
        self.assertEqual(parsed.fields[1].role, 'COMMAND')

    def test_macro_cache_tracks_the_source_directory(self):
        import schema

        before = schema._project_macro_names()
        schema._PROJECT_MACRO_KEY = '__different__'
        after = schema._project_macro_names()
        self.assertEqual(before, after)
        self.assertNotEqual(schema._PROJECT_MACRO_KEY, '__different__')


class ConfidenceTest(ScratchDirTest):

    def test_space_after_condition_is_normal(self):
        import field_parser as FP
        parsed = FP.parse_line('もし (x == 1) 保存変数 y = 2')
        self.assertEqual(parsed.confidence, 'high')

    def test_unmatched_paren_is_low(self):
        import field_parser as FP
        parsed = FP.parse_line('もし (x == 1)) 画像 a b.png')
        self.assertEqual(parsed.confidence, 'low')


class IndirectDisplayTest(ScratchDirTest):

    def test_assignment_rendered_in_text_is_translatable(self):
        import lvscan

        path = self.write('a.txt', [
            '保存変数 説明文 = ' + Q + 'こんにちは' + Q,
            '文字 t 1 2 3 a.ttf 20 ' + Q + '{{説明文}}' + Q,
        ])
        seen = []
        for pf in lvscan.iter_files(self._tmp):
            for _pl, field, line_no in pf.fields():
                if 'こんにちは' in field.value:
                    seen.append((field.role, field.translatable))
        self.assertTrue(seen, 'the assigned value was not surfaced at all')
        role, translatable = seen[0]
        self.assertEqual(role, 'DISPLAY')
        self.assertTrue(translatable)


class RoleReportAgreementTest(ScratchDirTest):

    def test_report_defers_to_corpus_inference(self):
        import field_parser as FP
        import role_report as RR

        self.write('b.txt', [
            '保存変数 武器表示 = ' + Q + '剣' + Q,
            '文字 t 1 2 3 a.ttf 20 ' + Q + '{{武器表示}}' + Q,
            '保存変数 パス = ' + Q + '{{武器表示}}' + Q,
            '画像 cg cg/{{パス}}.png',
        ])
        roles = FP.infer_display_variable_roles(self._tmp)
        if not roles['unsafe']:
            self.skipTest('inference found no unsafe variable in this fixture')
        report = RR.build_report(self._tmp)
        by_name = {v['name']: v for v in report['variables']}
        for name in roles['unsafe']:
            entry = by_name.get(name)
            if entry is None:
                continue
            self.assertNotEqual(entry['classification'], 'DISPLAY_ONLY',
                                '%s is unsafe per inference but reported DISPLAY_ONLY' % name)


class IndexContinuationTest(ScratchDirTest):

    def test_index_contains_continuation_fragments(self):
        import lvindex

        self.write('a.txt', [
            '~【リン】',
            Q + '1ページ目' + chr(92) + 'w',
            '2行目の続き',
            '3行目の続き',
        ])
        out = os.path.join(self._tmp, '_idx')
        lvindex.build(self._tmp, out)
        with open(os.path.join(out, 'display.json'), encoding='utf-8') as fh:
            payload = json.load(fh)
        roles = [item['role'] for item in payload['items']]
        self.assertIn('DISPLAY_CONTINUATION', roles,
                      'continuation fragments missing from the index')
        self.assertEqual(roles.count('DISPLAY_CONTINUATION'), 2)


if __name__ == '__main__':
    unittest.main()
