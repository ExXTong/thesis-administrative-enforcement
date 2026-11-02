#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A6 收尾: 走磁盘上的日期切片树, 精确算出缺口, 生成 _manifest.json 与 _未拿全清单.md"""
import json, os, glob
from datetime import date, timedelta
from collections import defaultdict

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
OUTDIR = os.path.join(ROOT, 'cases/A6')
KW = '死亡'
CAP = 160
TARGET = 15
YEARS = {2008: 0, 2009: 1, 2010: 3, 2011: 2, 2012: 11, 2013: 25,
         2014: 156, 2015: 150, 2016: 668, 2017: 800}


def lbl(d1, d2, y):
    if d1 == date(y, 1, 1) and d2 == date(y, 12, 31):
        return 'all'
    return 'D%02d%02d-%02d%02d' % (d1.month, d1.day, d2.month, d2.day)


def path(y, d1, d2):
    return os.path.join(OUTDIR, '%s__%d__all__%s.json' % (KW, y, lbl(d1, d2, y)))


def load(y, d1, d2):
    p = path(y, d1, d2)
    if not os.path.exists(p):
        return None
    try:
        j = json.load(open(p, encoding='utf-8'))
    except Exception:
        return None
    return j


def split(d1, d2, total):
    ndays = (d2 - d1).days + 1
    k = max(2, min(-(-total // TARGET), ndays))
    out, a = [], d1
    for i in range(k):
        b = d1 + timedelta(days=(ndays * (i + 1)) // k - 1)
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


slices, gaps, per_year = [], [], {}
nsl = defaultdict(int)
seen_links, seen_pairs = set(), set()
raw_count = 0

for y in sorted(YEARS):
    d1, d2 = date(y, 1, 1), date(y, 12, 31)
    got = [0]                      # 该年已取到的"叶内"条数
    stack = [(d1, d2)]
    ygaps = []
    while stack:
        a, b = stack.pop()
        j = load(y, a, b)
        rel = 'cases/A6/' + os.path.basename(path(y, a, b))
        if j is None:
            ygaps.append({'start': '%d.%d.%d' % (y, a.month, a.day),
                          'end': '%d.%d.%d' % (y, b.month, b.day),
                          'total': None, 'note': '该日期片未检索（预算耗尽）'})
            continue
        t, c = j.get('total'), j.get('count') or 0
        slices.append({'kw': KW, 'start': j['query']['startLastInstanceDate'],
                       'end': j['query']['endLastInstanceDate'], 'court': '',
                       'total': t, 'count': c, 'file': rel})
        for cs in j.get('cases') or []:
            raw_count += 1
            lk = cs.get('法宝链接')
            if lk:
                seen_links.add(lk)
            seen_pairs.add((cs.get('案号'), lk))
        if t is None:
            ygaps.append({'start': '%d.%d.%d' % (y, a.month, a.day),
                          'end': '%d.%d.%d' % (y, b.month, b.day),
                          'total': None, 'note': '调用报错，无 total'})
            continue
        if t <= 20:
            got[0] += c
        else:
            if a == b:
                ygaps.append({'start': '%d.%d.%d' % (y, a.month, a.day),
                              'end': '%d.%d.%d' % (y, b.month, b.day),
                              'total': t,
                              'note': '单日片 total=%d>20，法宝单次硬上限 20，无法再按日期细分'
                                      '（疑同院同日批量同源）' % t})
            else:
                stack.extend(split(a, b, t))
    nsl[y] = sum(1 for s2 in slices if s2['start'].startswith('%d.' % y))
    per_year[y] = {'total': YEARS[y], 'leaf_count': got[0],
                   'complete': got[0] == YEARS[y], 'gaps': ygaps}
    gaps.extend([dict(g, year=y) for g in ygaps])

# ---- manifest ----
manifest = {
    'agent': 'A6',
    'keywords': [KW],
    'year_range': '2008-2017',
    'calls_used': 159,
    'call_cap': CAP,
    'note': ('court 层级切片实测无效（"最高人民法院/高级人民法院/中级人民法院/基层人民法院"'
             '是真实法院名子串匹配，四档合计 2 件 vs 2013 年 total 25），已弃用；'
             'doc 亦非穷尽（2014 年 裁定书 103 / total 156）。'
             '最终只用【审结日期】做 k 路等比切分（k=ceil(total/15)），是唯一可保证不漏的分区维度。'),
    'slices': slices,
    'not_fully_retrieved': gaps,
    'per_year': {str(k): {'total': v['total'], 'retrieved': v['leaf_count'],
                          'complete': v['complete'],
                          'gap_slices': len(v['gaps']),
                          'gap_cases': sum(g['total'] or 0 for g in v['gaps'])}
                 for k, v in per_year.items()},
}
json.dump(manifest, open(os.path.join(OUTDIR, '_manifest.json'), 'w',
                         encoding='utf-8'), ensure_ascii=False, indent=1)

# ---- 人可读清单 ----
L = []
L.append('# A6 未拿全清单（关键词：死亡，年份 2008–2017）\n')
L.append('- 调用 **159 / 160** 次；落盘切片文件 **%d** 个；落盘案例条目（未去重）**%d** 条；'
         '按法宝链接去重后 **%d** 条。' % (len(slices), raw_count, len(seen_links)))
L.append('- 方法：只用【审结日期】切分。`court` 层级四档实测**不是分区**'
         '（2013 年 total=25，四档合计仅 2 件），已弃用；`doc` 亦非穷尽（2014 年 156 件中仅 103 件裁定书）。\n')
L.append('## 各年覆盖\n')
L.append('| 年 | 法宝 total | 已检索切片数 | 已取全（叶内） | 状态 | 缺口片数 | 缺口件数 |')
L.append('|---|---|---|---|---|---|---|')
for y in sorted(per_year):
    v = per_year[y]
    st = '★ 完整' if v['complete'] else '**未拿全**'
    L.append('| %d | %d | %d | %d | %s | %d | %s |' % (
        y, v['total'], nsl[y], v['leaf_count'], st, len(v['gaps']),
        sum(g['total'] or 0 for g in v['gaps']) if v['gaps'] else 0))
tot_all = sum(YEARS.values())
tot_got = sum(v['leaf_count'] for v in per_year.values())
L.append('| **合计** | **%d** | **%d** | **%d** | 覆盖 %.1f%% | %d | %s |\n' % (
    tot_all, len(slices), tot_got, 100.0 * tot_got / tot_all, len(gaps),
    sum(g['total'] or 0 for g in gaps)))
L.append('**2008–2015 八年已 100%% 拿全（348 件）**，缺口全部集中在 2016、2017 两个大年。\n'
         % ())
L.append('## 具体缺口切片\n')
L.append('| 年 | 起 | 止 | 该片 total | 原因 |')
L.append('|---|---|---|---|---|')
for g in sorted(gaps, key=lambda x: (x['year'], x['start'])):
    L.append('| %d | %s | %s | %s | %s |' % (
        g['year'], g['start'], g['end'],
        g['total'] if g['total'] is not None else '未知', g['note']))
L.append('\n## 其他说明\n')
L.append('- `cases/A6/_rejected/`：4 个已作废的法院层级切片（证明 court 维度不可用）。')
L.append('- `cases/A6/_diagnostics/`：3 个维度诊断调用结果（court/doc/基准），非数据集。')
L.append('- 法宝 Total 含重复计数（A1 实测）；去重请用**法宝链接**，勿用案号。')
L.append('- 缺口 2016 缺 %d 件、2017 缺 %d 件，主智能体可据此判断样本完整性边界。' % (
    per_year[2016]['total'] - per_year[2016]['leaf_count'],
    per_year[2017]['total'] - per_year[2017]['leaf_count']))
open(os.path.join(OUTDIR, '_未拿全清单.md'), 'w', encoding='utf-8').write('\n'.join(L))

print('slices=%d files, entries=%d, unique_links=%d, gaps=%d' % (
    len(slices), raw_count, len(seen_links), len(gaps)))
for y in sorted(per_year):
    v = per_year[y]
    print('%d total=%-4d got=%-4d %s gap_slices=%d' % (
        y, v['total'], v['leaf_count'], 'OK' if v['complete'] else 'PARTIAL', len(v['gaps'])))
