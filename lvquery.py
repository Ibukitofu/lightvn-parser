# -*- coding: utf-8 -*-
r'''lvquery.py -- 查询工具：按说话人/未译/变量/文件查'''
import sys, io, os, re, json, argparse


SCHEMA_VERSION = 1


def load(out_dir):
    d = {}
    for n in ('display', 'dialogue', 'struct', 'variables'):
        p = os.path.join(out_dir, n + '.json')
        if not os.path.exists(p):
            d[n] = []
            continue
        payload = json.load(open(p, encoding='utf-8'))
        if isinstance(payload, dict) and 'items' in payload:
            ver = payload.get('schema_version')
            if ver != SCHEMA_VERSION:
                raise SystemExit(
                    'index %s has schema_version=%r, this tool expects %d; '
                    'rebuild it with lvindex.py.' % (n, ver, SCHEMA_VERSION))
            d[n] = payload['items']
        else:
            d[n] = payload          # legacy bare-array index
    return d


def main():
    ap = argparse.ArgumentParser('lvquery')
    ap.add_argument('--index', default=None)
    ap.add_argument('--speaker')
    ap.add_argument('--untranslated', action='store_true')
    ap.add_argument('--var')
    ap.add_argument('--file')
    ap.add_argument('--role')
    ap.add_argument('--grep')
    ap.add_argument('--limit', type=int, default=20)
    a = ap.parse_args()
    idx = a.index or os.path.join(os.path.dirname(os.path.abspath(__file__)), '_index')
    d = load(idx)
    print('索引: display %d / dialogue %d / struct %d / variables %d' % (
        len(d['display']), len(d['dialogue']), len(d['struct']), len(d['variables'])))
    print()
    if a.speaker:
        hits = [x for x in d['dialogue'] if x.get('speaker') == a.speaker]
        print('说话人 %r: %d 条台词' % (a.speaker, len(hits)))
        for x in hits[:a.limit]:
            print('  %s L%-5d %s' % (x['file'], x['line'], x['text'][:70]))
        return
    if a.untranslated:
        hits = [x for x in d['display'] if x.get('hasKana')]
        print('显示字段仍含假名: %d 条' % len(hits))
        for x in hits[:a.limit]:
            print('  %s L%-5d [%s] %s' % (x['file'], x['line'], x['role'][:12], x['value'][:60]))
        return
    if a.var:
        v = next((x for x in d['variables'] if x['name'] == a.var), None)
        if not v:
            print('变量 %r 不在索引里' % a.var)
            return
        print('变量 %r' % a.var)
        print('  赋值点 %d: %s' % (len(v['assign']), v['assign'][:8]))
        print('  值 %d 种:' % len(v['values']))
        for x in v['values'][:a.limit]:
            print('    %r' % x[:70])
        return
    if a.file:
        hits = [x for x in d['display'] if x['file'] == a.file]
        print('文件 %r: %d 个显示字段' % (a.file, len(hits)))
        for x in hits[:a.limit]:
            print('  L%-5d [%s] %s' % (x['line'], x['role'][:12], x['value'][:70]))
        return
    if a.role:
        hits = [x for x in d['struct'] if x['role'] == a.role]
        print('角色 %r: %d 条' % (a.role, len(hits)))
        for x in hits[:a.limit]:
            print('  %s L%-5d %r' % (x['file'], x['line'], x['value'][:60]))
        return
    if a.grep:
        pat = re.compile(a.grep)
        n = 0
        for x in d['display']:
            if pat.search(x['value']):
                print('  %s L%-5d [%s] %s' % (x['file'], x['line'], x['role'][:12], x['value'][:70]))
                n += 1
                if n >= a.limit:
                    break
        print('grep %r: %d 条（最多显示 %d）' % (a.grep, n, a.limit))
        return
    print('用法:')
    print('  --speaker 琳        按说话人查台词')
    print('  --untranslated      查仍含假名的显示字段')
    print('  --var スキル効果     查变量')
    print('  --file 66756        查文件')
    print('  --role LABEL        查某角色的所有字段')
    print('  --grep 正則         正则搜索显示文本')


if __name__ == '__main__':
    main()