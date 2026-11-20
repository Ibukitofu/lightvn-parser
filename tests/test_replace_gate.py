# -*- coding: utf-8 -*-
r"""replace_field must refuse structural injection."""
import unittest
from tests.fixtures import ScratchDirTest, Q
import field_parser as FP


class ReplaceGateTest(ScratchDirTest):

    def _display_field(self):
        parsed = FP.parse_line("文字 t 1 2 3 a.ttf 20 " + Q + "abc" + Q)
        return parsed, [f for f in parsed.fields if f.role == "DISPLAY"][0]

    def test_normal_translation_accepted(self):
        parsed, field = self._display_field()
        out = parsed.replace_field(field, "你好世界")
        self.assertIn("你好世界", out)

    def test_segment_separator_refused(self):
        parsed, field = self._display_field()
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "a | ジャンプ x.txt y")

    def test_nul_refused(self):
        parsed, field = self._display_field()
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "a" + chr(0) + "b")

    def test_leading_dash_refused(self):
        parsed, field = self._display_field()
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "-abc")

    def test_speaker_marker_refused(self):
        parsed, field = self._display_field()
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "【abc")

    def test_quote_refused(self):
        parsed, field = self._display_field()
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "a" + Q + "b")

    def test_variable_token_change_refused(self):
        parsed = FP.parse_line("文字 t 1 2 3 a.ttf 20 " + Q + "{{x}}hi" + Q)
        field = [f for f in parsed.fields if f.role == "DISPLAY"][0]
        with self.assertRaises(ValueError):
            parsed.replace_field(field, "hi")


if __name__ == "__main__":
    unittest.main()