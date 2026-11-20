# -*- coding: utf-8 -*-
r"""Document-level continuation fragments must be reachable through fields()."""
import os
import unittest
from tests.fixtures import ScratchDirTest, Q
import lvscan


class DocumentFieldsTest(ScratchDirTest):

    def test_continuation_fragments_included(self):
        path = self.write("a.txt", [
            "~【リン】",
            Q + "1ページ目" + chr(92) + "w",
            "2行目の続き",
            "3行目の続き",
        ])
        pf = lvscan.parse_file(path, "a.txt")
        line_n = sum(1 for _p, f, _n in pf.line_fields() if "DISPLAY" in f.role)
        all_n = sum(1 for _p, f, _n in pf.fields() if "DISPLAY" in f.role)
        self.assertEqual(line_n, 1)
        self.assertGreater(all_n, line_n, "continuations must be exposed")

    def test_non_script_documents_yield_nothing(self):
        path = self.write("map.txt", ["{", chr(34) + "compressionlevel" + chr(34) + ":-1,", chr(34) + "layers" + chr(34) + ":[]}"])
        pf = lvscan.parse_file(path, "map.txt")
        self.assertFalse(pf.is_script)
        self.assertEqual(list(pf.fields()), [])

    def test_block_comment_rows_are_comment_kind(self):
        path = self.write("c.txt", ["/*", "メモ書き", "*/"])
        pf = lvscan.parse_file(path, "c.txt")
        self.assertEqual([p.kind for p in pf.parsed], ["comment"] * 3)


if __name__ == "__main__":
    unittest.main()