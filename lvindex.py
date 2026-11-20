# -*- coding: utf-8 -*-
r'''lvindex.py -- structured index: parse results -> queryable JSON

The index must expose the same field set the parser does.  Row-level iteration
misses the DISPLAY_CONTINUATION fragments that parse_document produces, so this
module walks ParsedFile.fields() instead of ParsedFile.parsed.
'''
import argparse
import json
import os
import re
import time

try:
    from . import field_parser as FP
except ImportError:
    import field_parser as FP
try:
    from . import lvscan
except ImportError:
    import lvscan


SCHEMA_VERSION = 1

DISPLAY_ROLES = FP.DISPLAY_ROLES

STRUCT_ROLES = {
    'COMMAND', 'LABEL', 'RESOURCE_PATH', 'FILENAME', 'VARIABLE_NAME',
    'ASSIGN_OPERATOR', 'NUMBER', 'OPTION_FLAG', 'CONDITION',
    'CONDITIONAL_COMMAND', 'SPEAKER_MARKER', 'PREFIX', 'DIALOGUE_MARKER',
    'PIPE_SEPARATOR', 'ASSET_ID', 'ENGINE_KEYWORD', 'OPAQUE_NESTED_CODE',
    'ASSET_GLOB', 'FILENAME_OR_LABEL',
}


def build(src_dir: str, out_dir: str) -> dict:
    t0 = time.perf_counter()
    os.makedirs(out_dir, exist_ok=True)
    display = []
    dialogue = []
    struct = []
    protected = []
    variables = {}
    ctx = lvscan.infer_context(src_dir)
    compared_vars = ctx.get('compared_vars') or set()
    path_vars = ctx.get('path_vars') or set()
    kana = re.compile(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]')
    var_re = re.compile(r'\{\{[^{}]*\}\}')
    files = 0

    def speakable(value):
        return bool(kana.search(var_re.sub('', value)))

    for pf in lvscan.iter_files(src_dir, context=ctx):
        if not pf.is_script:
            continue
        files += 1
        fid = pf.name[:-4] if pf.name.endswith('.txt') else pf.name

        # Speaker context is resolved per physical row first, so a continuation
        # fragment inherits the speaker of the row that opened its window.
        row_speaker = {}
        cur_spk = ''
        for index, pl in enumerate(pf.parsed):
            if any(f.role == 'COMMAND' and f.value == '栞' for f in pl.fields):
                cur_spk = ''
            for f in pl.fields:
                if f.role == 'SPEAKER_NAME':
                    cur_spk = f.value
                    break
            row_speaker[index + 1] = cur_spk

        for parsed, field, line_no in pf.fields():
            rec = {'file': fid, 'line': line_no, 'role': field.role,
                   'value': field.value}
            if field.role in DISPLAY_ROLES:
                speaker = row_speaker.get(line_no, '')
                rec['speaker'] = speaker
                rec['hasKana'] = speakable(field.value)
                display.append(rec)
                is_dialogue = (
                    field.role in ('DISPLAY_CONTINUATION', 'DISPLAY_INFERRED')
                    or (parsed is not None and parsed.kind == 'dialogue')
                    or (speaker and parsed is not None and parsed.kind == 'command')
                )
                if is_dialogue:
                    dialogue.append({'file': fid, 'line': line_no,
                                     'speaker': speaker, 'text': field.value})
            elif field.role == 'SPEAKER_NAME':
                rec['hasKana'] = speakable(field.value)
                display.append(rec)
            elif field.role == 'DISPLAY_UNSAFE':
                # Visible value whose stored form is also used as a logic key,
                # a resource path, or a jump label.  Kept in its own section with
                # translatable=False so it can be audited but never translated.
                var = ''
                if parsed is not None:
                    for f in parsed.fields:
                        if f.role == 'VARIABLE_NAME':
                            var = f.value
                            break
                reasons = []
                if var in compared_vars:
                    reasons.append('compared')
                if var in path_vars:
                    reasons.append('resource_or_label')
                rec['variable'] = var
                rec['translatable'] = False
                rec['reasons'] = reasons or ['variable_flagged_unsafe']
                protected.append(rec)
            elif field.role in STRUCT_ROLES:
                struct.append(rec)
            if field.role == 'VARIABLE_NAME':
                variables.setdefault(field.value, {'assign': [], 'value': []})
        # Assignment values need the owning variable, which is a row-level fact.
        for index, pl in enumerate(pf.parsed):
            varname = ''
            for f in pl.fields:
                if f.role == 'VARIABLE_NAME':
                    varname = f.value
                    break
            if not varname:
                continue
            for f in pl.fields:
                if f.role in ('ASSIGNMENT_VALUE', 'UNKNOWN_VALUE'):
                    entry = variables.setdefault(varname, {'assign': [], 'value': []})
                    entry['value'].append(f.value[:120])
                    if len(entry['assign']) < 50:
                        entry['assign'].append('%s:%d' % (fid, index + 1))

    def dump(name, items):
        path = os.path.join(out_dir, name)
        payload = {
            'schema_version': SCHEMA_VERSION,
            'source': os.path.abspath(src_dir),
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'parser_version': getattr(FP, '__version__', 'unknown'),
            'count': len(items),
            'items': items,
        }
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        return len(items), os.path.getsize(path)

    n1, s1 = dump('display.json', display)
    n2, s2 = dump('dialogue.json', dialogue)
    n3, s3 = dump('struct.json', struct)
    n4, s4 = dump('variables.json', [
        {'name': key, 'assign': val['assign'], 'values': val['value'][:30]}
        for key, val in variables.items()
    ])
    n5, s5 = dump('protected.json', protected)
    return {'files': files, 'display': n1, 'dialogue': n2, 'struct': n3,
            'variables': n4, 'protected': n5,
            'bytes': s1 + s2 + s3 + s4 + s5,
            'secs': round(time.perf_counter() - t0, 1)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the structured corpus index')
    ap.add_argument('src')
    ap.add_argument('-o', '--out', default=None)
    a = ap.parse_args(argv)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), '_index')
    r = build(a.src, out)
    print('索引目录: %s' % out)
    print('  脚本文件 %d' % r['files'])
    print('  display   %d 条' % r['display'])
    print('  dialogue  %d 条' % r['dialogue'])
    print('  struct    %d 条' % r['struct'])
    print('  variables %d 个' % r['variables'])
    print('  protected %d 条（可见但不可翻）' % r['protected'])
    print('  总大小 %.1f MB / 耗时 %.1fs' % (r['bytes'] / 1e6, r['secs']))
    return 0


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', write_through=True)
    raise SystemExit(main())
