# -*- coding: utf-8 -*-
"""lvparse_tool -- Light.vn script parser and corpus indexer.

Module map (dependency order, acyclic):
    field_types   Field / ParsedLine and the immutable lexeme constants
    grammar       quotes, segments, tokens, display-token children
    schema        engine metadata: command sets, argument slots, slot roles
    line_parser   single-line parser, public entry parse_line()
    documents     file classification, dialogue windows, continuations
    inference     corpus inference: display text vs logic key
    audit         corpus scan and CLI
    field_parser  compatibility facade over the seven modules above

Quick start:
    from lvparse_tool import lvscan
    parsed_file = lvscan.parse_file('66756.txt')
    for _parsed, field, line_no in parsed_file.fields():
        if field.translatable:
            print(line_no, field.value)
"""

__version__ = '0.1.0'

try:
    from . import lvroot, field_parser, lvscan, lvindex, lvverify  # noqa: F401
except ImportError:  # direct-script mode: sys.path already holds this directory
    pass

__all__ = [
    '__version__',
    'lvroot',
    'field_parser',
    'lvscan',
    'lvindex',
    'lvverify',
]
