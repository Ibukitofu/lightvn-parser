# -*- coding: utf-8 -*-
r"""lvverify must FAIL when a logic key is translated."""
import os
import unittest
from tests.fixtures import ScratchDirTest, Q
import lvverify


class VerifyLogicKeyTest(ScratchDirTest):

    def _pair(self, jp_lines, zh_lines):
        jp = os.path.join(self._tmp, "jp"); zh = os.path.join(self._tmp, "zh")
        os.makedirs(jp, exist_ok=True); os.makedirs(zh, exist_ok=True)
        open(os.path.join(jp, "9.txt"), "w", encoding="utf-8", newline="").write(chr(10).join(jp_lines))
        open(os.path.join(zh, "9.txt"), "w", encoding="utf-8", newline="").write(chr(10).join(zh_lines))
        return jp, zh

    def test_condition_literal_translation_fails(self):
        """A comparison operand translated away must be caught by the domain check."""
        jp, zh = self._pair(
            [
                "保存変数 スキル効果 = " + Q + "なし" + Q,
                "もし (スキル効果 == " + Q + "なし" + Q + ") ジャンプ a.txt b",
            ],
            [
                "保存変数 スキル効果 = " + Q + "无" + Q,
                "もし (スキル効果 == " + Q + "なし" + Q + ") ジャンプ a.txt b",
            ],
        )
        result = lvverify.check_logic_domains(jp, zh)
        self.assertTrue(result["fails"], "translated comparison value must FAIL")

    def test_assignment_value_translation_fails(self):
        """Assignment translated, comparison kept Japanese: the domain check must fail."""
        jp, zh = self._pair(
            [
                "保存変数 スキル効果 = " + Q + "なし" + Q,
                "もし (スキル効果 == " + Q + "なし" + Q + ") ジャンプ a.txt b",
            ],
            [
                "保存変数 スキル効果 = " + Q + "无" + Q,
                "もし (スキル効果 == " + Q + "なし" + Q + ") ジャンプ a.txt b",
            ],
        )
        result = lvverify.check_logic_domains(jp, zh)
        self.assertTrue(result["fails"], "assignment value change must FAIL")

    def test_display_only_assignment_may_change(self):
        """A value that is never compared is display text: translating it must PASS."""
        jp, zh = self._pair(
            ["保存変数 説明文 = " + Q + "こんにちは" + Q],
            ["保存変数 説明文 = " + Q + "你好" + Q],
        )
        result = lvverify.verify_structure(jp, zh, line_wl=set())
        self.assertFalse(result["structural_fails"], "display-only assignment change must PASS")

    def test_display_translation_passes(self):
        jp, zh = self._pair(
            ["文字 t 1 2 3 f.ttf 20 " + Q + "こんにちは" + Q],
            ["文字 t 1 2 3 f.ttf 20 " + Q + "你好" + Q],
        )
        result = lvverify.verify_structure(jp, zh, line_wl=set())
        self.assertFalse(result["structural_fails"], "plain display change must PASS")

    def test_a3_class_accident_detected(self):
        """Assignment translated, comparison left Japanese -> the branch can never hit."""
        jp, zh = self._pair(
            [
                "保存変数 bt_eff = " + Q + "ブロック付与" + Q,
                "もし (bt_eff == " + Q + "ブロック付与" + Q + ") ジャンプ a.txt b",
            ],
            [
                "保存変数 bt_eff = " + Q + "格挡赋予" + Q,
                "もし (bt_eff == " + Q + "ブロック付与" + Q + ") ジャンプ a.txt b",
            ],
        )
        result = lvverify.check_logic_domains(jp, zh)
        self.assertTrue(result["fails"], "A3-class translation must be detected")

    def test_both_sides_translated_is_consistent(self):
        jp, zh = self._pair(
            [
                "保存変数 bt_eff = " + Q + "ブロック付与" + Q,
                "もし (bt_eff == " + Q + "ブロック付与" + Q + ") ジャンプ a.txt b",
            ],
            [
                "保存変数 bt_eff = " + Q + "格挡赋予" + Q,
                "もし (bt_eff == " + Q + "格挡赋予" + Q + ") ジャンプ a.txt b",
            ],
        )
        result = lvverify.check_logic_domains(jp, zh)
        self.assertFalse(result["fails"], "consistent translation must not be reported")

    def test_missing_zh_file_fails(self):
        jp = os.path.join(self._tmp, "jp"); zh = os.path.join(self._tmp, "zh")
        os.makedirs(jp, exist_ok=True); os.makedirs(zh, exist_ok=True)
        open(os.path.join(jp, "1.txt"), "w", encoding="utf-8").write("栞 a")
        result = lvverify.verify_structure(jp, zh, line_wl=set())
        self.assertTrue(result["structural_fails"])

    def test_empty_directories_fail(self):
        jp = os.path.join(self._tmp, "jp"); zh = os.path.join(self._tmp, "zh")
        os.makedirs(jp, exist_ok=True); os.makedirs(zh, exist_ok=True)
        result = lvverify.verify_structure(jp, zh, line_wl=set())
        self.assertTrue(result["structural_fails"])


if __name__ == "__main__":
    unittest.main()