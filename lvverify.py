# -*- coding: utf-8 -*-
r'''lvverify.py -- 完整性验证：漏（显示文本仍含假名）+ 错（结构被改）'''
import sys, io, os, re, json, argparse

try:
    from . import field_parser as FP
except ImportError:
    import field_parser as FP
try:
    from . import lvscan
except ImportError:
    import lvscan

KANA = re.compile(r'[\u3041-\u3096\u30a1-\u30fa\u30fd-\u30ff]')
VAR = re.compile(r'\{\{[^{}]*\}\}')

# 引擎字面量：不是译文，是键
LITERAL = {'なし', '无', ''}

CMP_RE = re.compile(r'(?<![A-Za-z0-9_])([A-Za-z0-9_\u3040-\u9fff]+)\s*[=!]=\s*"([^"]*)"')
ASSIGN_RE = re.compile(r'(?<![A-Za-z0-9_=!<>])([A-Za-z0-9_\u3040-\u9fff]+)\s*(?<![=!<>])=\s*(?!=)"([^"]*)"')

LABEL_WL = ('説明_', 'エフェクト_')
STRUCT = {'COMMAND','VARIABLE_NAME','LABEL','RESOURCE_PATH','FILENAME','OPTION_FLAG',
          'ASSIGN_OPERATOR','NUMBER','ASSET_ID','ENGINE_KEYWORD','SPEAKER_MARKER',
          'PREFIX','DIALOGUE_MARKER','PIPE_SEPARATOR','CONDITIONAL_COMMAND',
          'FILENAME_OR_LABEL','ASSET_GLOB','OPAQUE_NESTED_CODE',

          'COMMENT','CODE_LITERAL','CODE_FRAGMENT','REGEX_LITERAL','EXTERNAL_URL',
          'BOOLEAN','COMPARE_OPERATOR','ENUM_KEY','RESOURCE_OR_OPTION','DOCUMENT_ROLE',
}


def scan_untranslated(directory: str) -> dict:
    """Miss check: translatable fields whose non-variable part is still kana.

    Uses ParsedFile.fields() so document-level continuation fragments are
    covered as well as line-level fields.
    """
    hits = []
    total = 0
    for pf in lvscan.iter_files(directory):
        if not pf.is_script:
            continue
        fid = pf.name[:-4] if pf.name.endswith('.txt') else pf.name
        for _pl, field, line_no in pf.fields():
            if not field.translatable:
                continue
            core = VAR.sub('', field.value).strip()
            total += 1
            if not core or core in LITERAL:
                continue
            if KANA.search(core):
                hits.append({
                    'file': fid,
                    'line': line_no,
                    'role': field.role,
                    'value': field.value[:120],
                })
    return {
        'total_translatable': total,
        'untranslated': hits,
    }


def _comparison_literals(directory: str) -> set:
    """Every quoted literal used as a == / != operand anywhere in the corpus."""
    found = set()
    newline = chr(10)
    pattern = re.compile('[=!]=' + r'\s*' + '"([^"' + newline + ']{1,80})"')
    for fn in sorted(os.listdir(directory)):
        if not fn.lower().endswith('.txt'):
            continue
        try:
            with open(os.path.join(directory, fn), encoding='utf-8',
                      errors='surrogateescape', newline='') as fh:
                found.update(pattern.findall(fh.read()))
        except OSError:
            continue
    return found



def check_logic_domains(jp_dir: str, zh_dir: str) -> dict:
    """Detect translated logic values by domain consistency.

    A value that is both assigned and compared for the same variable is a
    logic key.  If the translation removes it from the assignment domain while
    the comparison still references it, that branch can never match again.
    Only this shape is provable, so only this shape is reported.
    """
    def collect(directory):
        compares, assigns = {}, {}
        for fn in sorted(os.listdir(directory)):
            if not fn.lower().endswith('.txt'):
                continue
            try:
                with open(os.path.join(directory, fn), encoding='utf-8',
                          errors='surrogateescape', newline='') as fh:
                    content = fh.read()
            except OSError:
                continue
            for line in content.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10)).split(chr(10)):
                for m in CMP_RE.finditer(line):
                    compares.setdefault(m.group(1), set()).add(m.group(2))
                for m in ASSIGN_RE.finditer(line):
                    assigns.setdefault(m.group(1), set()).add(m.group(2))
        return compares, assigns

    jc, ja = collect(jp_dir)
    zc, za = collect(zh_dir)
    fails = []
    checked = 0
    for var, jvals in jc.items():
        jassign = ja.get(var)
        if not jassign:
            continue            # value comes from elsewhere; nothing provable
        zassign = za.get(var, set())
        zcompare = zc.get(var, set())
        for value in jvals:
            if value not in jassign:
                continue        # JP never assigned it either
            checked += 1
            if value in zassign:
                continue        # still assignable, branch intact
            if value not in zcompare:
                continue        # comparison moved too; consistent
            fails.append({
                'var': var,
                'value': value[:60],
                'kind': 'logic-value-mismatch',
            })
    return {
        'checked': checked,
        'fails': fails,
    }


def verify_structure(jp_dir: str, zh_dir: str, label_dir: str = '', line_wl=None) -> dict:
    '''错：结构字段必须与 JP 一致'''
    line_wl = line_wl or set()
    GUARD = re.compile(r'^\s*(//\s*zh-|もし \((特性表_ready|技能名表_ready|lvHashMapHasKey))')
    comparison_literals = _comparison_literals(jp_dir)
    fails = []
    checked = 0
    jp_names = sorted(f for f in os.listdir(jp_dir) if f.lower().endswith('.txt'))
    for fn in jp_names:
        fid = fn[:-4]
        zp = os.path.join(zh_dir, fn)
        if not os.path.exists(zp):
            fails.append({'file': fid, 'kind': 'missing-zh'})
            continue
        jpf = lvscan.parse_file(os.path.join(jp_dir, fn), fn)
        zpf = lvscan.parse_file(zp, fn)
        if not jpf.is_script:
            continue
        jr = [r for r in jpf.rows]
        zr = [r for r in zpf.rows if not GUARD.match(r)]
        while jr and not jr[-1].strip():
            jr.pop()
        while zr and not zr[-1].strip():
            zr.pop()
        if len(jr) != len(zr):
            if fid in line_wl:
                continue
            fails.append({'file': fid, 'kind': 'line-count', 'jp': len(jr), 'zh': len(zr)})
            continue
        jparsed = lvscan.parse_rows(jr)
        zparsed = lvscan.parse_rows(zr)
        for i, (ja, zb) in enumerate(zip(jparsed, zparsed)):
            if jr[i] == zr[i]:
                continue
            checked += 1
            def _st(pl):
                # Only byte-stable structural fields are compared here.  Assignment
                # values are deliberately excluded: the same literal can be display
                # text for one variable and a logic key for another, so a flat
                # comparison produces false positives.  check_logic_domains()
                # covers the provable case (same variable, both sides).
                out = []
                for f in pl.fields:
                    if f.role not in STRUCT:
                        continue
                    if f.role == 'LABEL' and any(f.value.startswith(w) for w in LABEL_WL):
                        continue
                    out.append((f.role, f.value))
                return out
            sa = _st(ja)
            sb = _st(zb)
            if sa != sb:
                fails.append({'file': fid, 'line': i + 1, 'kind': 'struct', 'jp': sa[:2], 'zh': sb[:2]})
    if not jp_names:
        fails.append({'file': '-', 'kind': 'empty-jp-dir'})
    elif checked == 0 and not fails:
        fails.append({'file': '-', 'kind': 'nothing-to-compare'})
    guarded_files = max(0, sum(1 for _ in []))
    return {'checked_lines': checked, 'structural_fails': fails}


def check_labels(jp_dir: str, zh_dir: str, label_wl=()) -> dict:
    from collections import Counter
    fails = []
    checked = 0
    for fn in sorted(f for f in os.listdir(jp_dir) if f.lower().endswith('.txt')):
        zp = os.path.join(zh_dir, fn)
        if not os.path.exists(zp):
            continue
        jpf = lvscan.parse_file(os.path.join(jp_dir, fn), fn)
        zpf = lvscan.parse_file(zp, fn)
        if not jpf.is_script:
            continue
        jl, zl = Counter(), Counter()
        for r in jpf.rows:
            m = re.match(r'\s*~?栞\s+(\S+)', r)
            if m:
                jl[m.group(1)] += 1
        for r in zpf.rows:
            m = re.match(r'\s*~?栞\s+(\S+)', r)
            if m:
                zl[m.group(1)] += 1
        for name, n in jl.items():
            if any(name.startswith(w) for w in label_wl):
                continue
            checked += 1
            if zl.get(name, 0) < n:
                fails.append({'file': fn[:-4], 'label': name, 'jp': n, 'zh': zl.get(name, 0)})
    return {'checked_labels': checked, 'label_fails': fails}


# Files allowed to differ in physical line count because the translation inserts
# lookup tables and guards.  Moving this list to a config file is tracked as a
# follow-up; keeping it here makes the exemption visible in one place.
LINE_WL = {'67467','67244','67438','66422','66425','66434','66436','66438','66562','66569'}


def main():
    ap = argparse.ArgumentParser(description='Light.vn translation verifier')
    ap.add_argument('--jp', required=True, help='Japanese source directory')
    ap.add_argument('--zh', required=True, help='Translated output directory')
    ap.add_argument('--miss', action='store_true', help='also run the untranslated-text scan')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    r1 = check_labels(a.jp, a.zh, ('説明_', 'エフェクト_'))
    r2 = verify_structure(a.jp, a.zh, line_wl=LINE_WL)
    ok = not r1['label_fails'] and not r2['structural_fails']

    print('=' * 70)
    print('Label names: checked %d, FAIL %d' % (r1['checked_labels'], len(r1['label_fails'])))
    for x in r1['label_fails'][:10]:
        print('   FAIL %s' % (x,))
    print('=' * 70)
    print('Structural fields: checked %d changed lines, FAIL %d'
          % (r2['checked_lines'], len(r2['structural_fails'])))
    for x in r2['structural_fails'][:10]:
        print('   FAIL %s' % (x,))

    r4 = check_logic_domains(a.jp, a.zh)
    print('=' * 70)
    print('Logic domain: checked %d, FAIL %d'
          % (r4['checked'], len(r4['fails'])))
    for x in r4['fails'][:20]:
        print('   FAIL %s = %r' % (x['var'], x['value']))
    if r4['fails']:
        ok = False

    r3 = None
    if a.miss:
        r3 = scan_untranslated(a.zh)
        print('=' * 70)
        print('Untranslated display text: %d translatable fields, %d still kana'
              % (r3['total_translatable'], len(r3['untranslated'])))
        for x in r3['untranslated'][:20]:
            print('   %s L%-5d [%s] %s' % (x['file'], x['line'], x['role'][:12], x['value']))
        if r3['untranslated']:
            ok = False

    print('=' * 70)
    print('Total: %s' % ('PASS' if ok else 'FAIL'))
    if a.json:
        payload = {'labels': r1, 'struct': r2, 'domain': r4}
        if r3 is not None:
            payload['miss'] = r3
        print(json.dumps(payload, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())