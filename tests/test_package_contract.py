# -*- coding: utf-8 -*-
"""Package-level contracts: exports, layering, live globals."""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

CORE = [
    'field_types', 'grammar', 'schema', 'line_parser',
    'documents', 'inference', 'audit',
]


class PackageContractTest(unittest.TestCase):

    def test_version_present(self):
        import lvparse_tool
        self.assertTrue(hasattr(lvparse_tool, "__version__"))

    def test_is_a_real_package(self):
        import lvparse_tool
        self.assertTrue(lvparse_tool.__file__)
        self.assertTrue(lvparse_tool.__file__.endswith("__init__.py"))

    def test_no_import_cycles(self):
        graph = {}
        for name in CORE:
            path = os.path.join(PKG, name + ".py")
            tree = ast.parse(open(path, encoding="utf-8").read())
            deps = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    if node.module in CORE:
                        deps.add(node.module)
            graph[name] = deps
        state = {}
        def visit(n, stack):
            if state.get(n) == 1:
                return stack[stack.index(n):] + [n]
            if state.get(n) == 2:
                return None
            state[n] = 1
            stack.append(n)
            for dep in sorted(graph.get(n, ())):
                found = visit(dep, stack)
                if found:
                    return found
            stack.pop()
            state[n] = 2
            return None
        for name in CORE:
            self.assertIsNone(visit(name, []), "import cycle through " + name)

    def test_facade_reexports_everything(self):
        import lvparse_tool.field_parser as facade
        missing = [n for n in facade.__all__ if not hasattr(facade, n)]
        self.assertEqual(missing, [])

    def test_facade_covers_each_module_top_level(self):
        import importlib
        import lvparse_tool.field_parser as facade
        for name in CORE:
            path = os.path.join(PKG, name + ".py")
            tree = ast.parse(open(path, encoding="utf-8").read())
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    self.assertTrue(hasattr(facade, node.name),
                                    name + "." + node.name + " not exported")

    def test_lazy_globals_are_live(self):
        from lvparse_tool import field_parser as facade
        import lvparse_tool.schema as schema
        facade.official_option_flags()
        self.assertIs(facade._OPTION_FLAGS, schema._OPTION_FLAGS)
        self.assertTrue(facade._OPTION_FLAGS)


if __name__ == "__main__":
    unittest.main()
