# -*- coding: utf-8 -*-
r"""Shared fixtures: a synthetic Commands.xml and scratch directories."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
if PKG not in sys.path:
    sys.path.insert(0, PKG)

Q = chr(34)


class ScratchDirTest(unittest.TestCase):
    """Give every test an empty temp directory that is cleaned up afterwards."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="lvparse_t_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, name, lines):
        path = os.path.join(self._tmp, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(chr(10).join(lines))
        return path