# -*- coding: utf-8 -*-
r"""serialize() must rebuild text, not return raw."""
import unittest
from tests.fixtures import ScratchDirTest, Q
import field_parser as FP


class SerializeRebuildTest(ScratchDirTest):

    def test_roundtrip_matches_raw(self):
        for line in [
            "文字 t 1 2 3 a.ttf 20 " + Q + "hi" + Q,
            "~【リン】",
            "",
            "// comment",
            "もし (x == " + Q + "ON" + Q + ") ジャンプ a.txt b",
        ]:
            parsed = FP.parse_line(line)
            self.assertEqual(parsed.serialize(), line, line)

    def test_rebuild_preserves_gaps(self):
        line = "abcdefgh"
        parsed = FP.parse_line(line)
        parsed.fields = [
            FP.Field(role="A", start=0, end=2, raw="ab", value="ab"),
            FP.Field(role="B", start=4, end=6, raw="ef", value="ef"),
        ]
        self.assertEqual(parsed.serialize(), line)
        self.assertEqual(parsed.unclassified_spans(), [(2, 4, "cd"), (6, 8, "gh")])

    def test_overlapping_spans_raise(self):
        parsed = FP.parse_line("abcdefgh")
        parsed.fields = [
            FP.Field(role="A", start=0, end=4, raw="abcd", value="abcd"),
            FP.Field(role="B", start=2, end=6, raw="cdef", value="cdef"),
        ]
        with self.assertRaises(ValueError):
            parsed.serialize()

    def test_stale_span_raises(self):
        parsed = FP.parse_line("abcdefgh")
        parsed.fields = [
            FP.Field(role="A", start=0, end=2, raw="zz", value="zz"),
        ]
        with self.assertRaises(ValueError):
            parsed.serialize()


if __name__ == "__main__":
    unittest.main()