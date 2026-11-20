# -*- coding: utf-8 -*-
r"""The package must import cleanly and must not touch sys.stdout on import."""
import io
import sys
import unittest


class PackageImportTest(unittest.TestCase):

    def test_import_succeeds(self):
        import importlib
        mod = importlib.import_module("lvparse_tool")
        self.assertTrue(hasattr(mod, "__version__"))

    def test_import_does_not_replace_stdout(self):
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            import importlib
            importlib.import_module("lvparse_tool")
        finally:
            sys.stdout = old
        self.assertIs(sys.stdout, old)


if __name__ == "__main__":
    unittest.main()