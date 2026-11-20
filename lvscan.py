# -*- coding: utf-8 -*-
r'''lvscan.py -- document-level parsing entry point

Design:
  parse_line()         single-row parse (no document context)
  parse_file()         file parse: classify, then rows, then corpus inference
  ParsedFile.fields()  row-level fields + document-level continuation fragments
  infer_context()      corpus evidence (display params + variable roles), once per dir
  iter_files()         batch

History:
  (a)   Tiled JSON / shader / xml no longer produce fake DISPLAY fields
  (d)   Block comments /* */ are recognised as comment rows
  (b)   Display arguments of スクリプト calls are promoted to DISPLAY
  (#3)  fields() now includes DISPLAY_CONTINUATION / DISPLAY_INFERRED
  (#4)  Variable-role inference is wired in: when 保存変数 X = "..." is rendered
        through {{X}}, the assigned value becomes DISPLAY instead of UNKNOWN_VALUE.
'''
import logging
import os
import sys
from dataclasses import dataclass, field as dc_field
from typing import Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from . import field_parser as FP
except ImportError:
    import field_parser as FP

COMMENT_OPEN = '/*'
COMMENT_CLOSE = '*/'


@dataclass
class ParsedFile:
    path: str
    name: str
    file_type: str
    rows: list
    parsed: list
    is_script: bool
    _windows: Optional[list] = dc_field(default=None, repr=False)

    def windows(self) -> list:
        '''Document-level dialogue windows with fragments (cached).'''
        if self._windows is None:
            self._windows = FP.parse_document(self.rows, self.parsed) if self.is_script else []
        return self._windows

    def fields(self) -> Iterator[tuple]:
        '''Yield (parsed_line, field, line_number) for every field of the file.

        Includes the DISPLAY_CONTINUATION / DISPLAY_INFERRED fragments that only
        parse_document can produce.  This is the single entry point every
        downstream consumer must use; walking self.parsed directly drops about
        3.4k continuation fragments on the main corpus.
        '''
        for index, pl in enumerate(self.parsed):
            for f in pl.fields:
                yield pl, f, index + 1
        for window in self.windows():
            for frag in window['fragments']:
                line_no = frag['line']
                field = frag['field']
                row_parsed = self.parsed[line_no - 1] if 0 < line_no <= len(self.parsed) else None
                if row_parsed is not None and any(
                        f.start == field.start and f.end == field.end and f.value == field.value
                        for f in row_parsed.fields if f.role in FP.DISPLAY_ROLES):
                    continue
                yield None, field, line_no

    def line_fields(self) -> Iterator[tuple]:
        '''Row-level fields only (no document-level fragments).'''
        for index, pl in enumerate(self.parsed):
            for f in pl.fields:
                yield pl, f, index + 1


def split_lines(text: str) -> list:
    return text.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10)).split(chr(10))


def parse_rows(rows: list, display_params: Optional[dict] = None) -> list:
    '''Per-row parse, plus block comments, plus cross-script display arguments.'''
    parsed = []
    in_block = False
    for r in rows:
        s = r.strip()
        if s == COMMENT_OPEN:
            in_block = True
            fld = FP.Field(role='COMMENT', start=0, end=len(r), raw=r, value=r, translatable=False)
            parsed.append(FP.ParsedLine(raw=r, kind='comment', fields=[fld], confidence='high'))
            continue
        if in_block:
            fld = FP.Field(role='COMMENT', start=0, end=len(r), raw=r, value=r, translatable=False)
            parsed.append(FP.ParsedLine(raw=r, kind='comment', fields=[fld], confidence='high'))
            if s == COMMENT_CLOSE:
                in_block = False
            continue
        parsed.append(FP.parse_line(r))
    if display_params:
        for pl in parsed:
            try:
                FP.promote_inferred_display_arguments(pl, display_params)
            except Exception as exc:
                logger.warning('display argument promotion failed: %s', exc)
    return parsed


def parse_file(path: str, name: str = '', display_params: Optional[dict] = None,
               display_vars: Optional[set] = None,
               unsafe_vars: Optional[set] = None) -> ParsedFile:
    '''Parse one file into fields.

    display_vars / unsafe_vars carry corpus-wide evidence about which variables
    end up on screen.  Without them an indirect display stays a plain
    UNKNOWN_VALUE: an assignment followed by {{name}} inside a text object would
    look untranslatable even though the player sees it.  Callers that only need
    syntax may leave them out.
    '''
    with open(path, 'r', encoding='utf-8', errors='surrogateescape', newline='') as fh:
        content = fh.read()
    file_type = FP.classify_source_content(content)
    rows = split_lines(content)
    is_script = (file_type == 'script_candidate')
    parsed = parse_rows(rows, display_params) if is_script else []
    if is_script and display_vars is not None:
        for pl in parsed:
            try:
                FP.promote_inferred_display_assignments(pl, display_vars, unsafe_vars or set())
            except Exception as exc:
                logger.warning('display assignment promotion failed for %s: %s', path, exc)
    return ParsedFile(path=path, name=name or os.path.basename(path),
                      file_type=file_type, rows=rows, parsed=parsed, is_script=is_script)


def infer_context(directory: str, use_inference: bool = True) -> dict:
    '''Corpus-wide evidence needed before any single file can be judged.

    Both scans walk the corpus, so they run once per directory rather than once
    per file.  A failure is logged and yields empty sets, which is the
    conservative answer: no variable is claimed to be displayed.
    '''
    empty = {
        'display_params': None, 'display_vars': None, 'unsafe_vars': None,
        'compared_vars': set(), 'path_vars': set(),
    }
    if not use_inference:
        return empty
    try:
        params = FP.infer_display_parameter_indices(directory)
    except Exception as exc:
        logger.warning('infer_display_parameter_indices failed for %s: %s', directory, exc)
        params = {}
    compared = set()
    path = set()
    try:
        roles = FP.infer_display_variable_roles(directory)
        safe = roles['safe']
        unsafe = roles['unsafe']
        compared = set(roles.get('compared', ()))
        path = set(roles.get('path', ()))
    except Exception as exc:
        logger.warning('infer_display_variable_roles failed for %s: %s', directory, exc)
        safe = set()
        unsafe = set()
    return {
        'display_params': params, 'display_vars': safe, 'unsafe_vars': unsafe,
        'compared_vars': compared, 'path_vars': path,
    }


def iter_files(directory: str, use_inference: bool = True, *,
               context: Optional[dict] = None) -> Iterable[ParsedFile]:
    '''Scan files, optionally reusing context inferred for this directory.

    A supplied context is used only when inference is enabled. It belongs to
    the caller's current corpus snapshot; no persistent cache is introduced.
    '''
    ctx = context if use_inference and context is not None else infer_context(directory, use_inference)
    for fn in sorted(os.listdir(directory)):
        if not fn.lower().endswith('.txt'):
            continue
        yield parse_file(os.path.join(directory, fn), fn,
                         ctx['display_params'], ctx['display_vars'], ctx['unsafe_vars'])


def main(argv=None):
    import argparse
    from collections import Counter
    ap = argparse.ArgumentParser(description='Light.vn script corpus scanner')
    ap.add_argument('directory')
    a = ap.parse_args(argv)
    types = Counter()
    scripts = lines = disp = frag = 0
    for pf in iter_files(a.directory):
        types[pf.file_type] += 1
        if pf.is_script:
            scripts += 1
            lines += sum(1 for r in pf.rows if r.strip())
            line_n = sum(1 for pl, f, n in pf.line_fields() if f.role in FP.DISPLAY_ROLES)
            all_n = sum(1 for pl, f, n in pf.fields() if f.role in FP.DISPLAY_ROLES)
            disp += line_n
            frag += all_n - line_n
    print('目录: %s' % a.directory)
    for k, v in types.most_common():
        print('  %-20s %d' % (k, v))
    print('  脚本 %d / 非空行 %d' % (scripts, lines))
    print('  行级 DISPLAY %d / 文档级续写 %d / 合计 %d' % (disp, frag, disp + frag))
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', write_through=True)
    raise SystemExit(main())
