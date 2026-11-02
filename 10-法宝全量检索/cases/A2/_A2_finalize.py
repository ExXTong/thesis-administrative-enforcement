#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 收尾：不发任何检索请求，只按盘上数据重算 _manifest.json / _未拿全清单.md
（修正批量同源判定口径：同一法院 且 不同审结日期 <=2 即视为 batch）"""
import json, os, datetime

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
D = os.path.join(ROOT, 'cases/A2')
CAP = 75


def P(s):
    return datetime.date(*map(int, s.split('.')))


def contained(a, b):
    if a['kw'] != b['kw'] or a['court'] != b['court']:
        return False
    if not a['start'] or not a['end'] or not b['start'] or not b['end']:
        return False
    return (P(a['start']) <= P(b['start']) and P(b['end']) <= P(a['end'])) and \
           (a['start'], a['end']) != (b['start'], b['end'])


m = json.load(open(os.path.join(D, '_manifest.json')))
sl = m['slices']
leaves = [a for a in sl if not any(contained(a, b) for b in sl)]

not_full, batches, merged = [], [], []
for a in sorted(leaves, key=lambda x: -(x['total'] or 0)):
    if (a['total'] or 0) <= 20:
        continue
    p = os.path.join(ROOT, a['file'])
    cs = json.load(open(p))['cases'] if os.path.exists(p) else []
    nc = len(set(c['法院'] for c in cs))
    nd = len(set(c['审结日期'] for c in cs))
    mode = 0
    if cs:
        from collections import Counter
        mode = Counter((c['法院'], c['审结日期']) for c in cs).most_common(1)[0][1]
    batch = bool(cs) and nc == 1 and nd <= 2
    if batch:
        batches.append(f"{a['kw']} {a['start']}-{a['end']}（total={a['total']}，样本 "
                       f"{len(cs)} 条全部来自同一法院、审结日期仅 {nd} 个，众数 {mode}/{len(cs)}）")
    not_full.append({"kw": a['kw'], "span": f"{a['start']}-{a['end']}", "court": a['court'],
                     "total": a['total'], "got": min(a['count'], 20), "batch": batch,
                     "court_n": nc, "date_n": nd,
                     "note": ("批量同源（同一法院+同一日期批量案件），按主智能体广播规则④"
                              "记为未展开，不向下钻取"
                              if batch else
                              f"仅取回 {a['count']}/{a['total']} 条，调用上限已用尽未再细分")})

holes = []
for kw in ['已死亡', '身亡', '死亡证明', '死者']:
    iv = sorted([(P(x['start']), P(x['end'])) for x in leaves
                 if x['kw'] == kw and x['start'] and x['end']])
    cur, end = datetime.date(2008, 1, 1), datetime.date(2026, 12, 31)
    for (a, b) in iv:
        if a > cur:
            holes.append(f"{kw} {cur}~{a - datetime.timedelta(days=1)} 未检索")
        cur = max(cur, b + datetime.timedelta(days=1))
    if cur <= end:
        holes.append(f"{kw} {cur}~{end} 未检索")

cov = {}
for kw in ['已死亡', '身亡', '死亡证明', '死者']:
    L = [x for x in leaves if x['kw'] == kw]
    c = sum(min(x['total'] or 0, x['count']) for x in L)
    t = sum(x['total'] or 0 for x in L)
    cov[kw] = f"{c}/{t} ({c / t * 100:.1f}%)"

out = {"agent": "A2", "keywords": ['已死亡', '身亡', '死亡证明', '死者'],
       "calls_used": m['calls_used'], "call_cap": CAP,
       "files": len(sl), "cases_sum": sum(x['count'] for x in sl),
       "range": "2008.1.1~2026.12.31",
       "method": ("自适应 best-first 时间二分切片，每片 <=20 即视为拿全；"
                  "第二轮用父片已落盘样本的月度分布挑切点（月边界），使两侧估计均 <=20。"
                  "★ 法院层级维度实测非穷尽（对 total=51 的片按四档法院切分，四片合计仅 3 条），"
                  "故全程未再使用；★ 批量同源片按主智能体广播规则④不展开。"),
       "coverage_by_keyword": cov,
       "slices": sl, "not_fully_retrieved": not_full, "coverage_holes": holes,
       "batches_not_expanded": batches, "errors": m.get('errors', [])}
json.dump(out, open(os.path.join(D, '_manifest.json'), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=1)

L = ["# A2 未拿全清单", "",
     f"- 调用：{out['calls_used']}/{CAP}（已用满）",
     f"- 落盘文件：{out['files']}；记录条数（未去重）：{out['cases_sum']}",
     f"- 未拿全切片：{len(not_full)}（其中批量同源未展开 {len(batches)}）",
     f"- 日期空洞：{len(holes)}", "",
     "## 关键词覆盖", "", "| 关键词 | 已取回/区间内总数 | 覆盖率 |", "|---|---|---|"]
for k, v in cov.items():
    L.append(f"| {k} | {v.split(' ')[0]} | {v.split(' ')[1]} |")
L += ["", "## 未拿全切片", "",
      "| 关键词 | 区间 | total | 已得 | 法院数 | 日期数 | 原因 |", "|---|---|---|---|---|---|---|"]
for n in not_full:
    L.append(f"| {n['kw']} | {n['span']} | {n['total']} | {n['got']} | {n['court_n']} | "
             f"{n['date_n']} | {n['note']} |")
L += ["", "## 批量同源未展开（广播规则④）", ""] + ([f"- {b}" for b in batches] or ["- 无"])
L += ["", "## 未检索的日期空洞", ""] + ([f"- {h}" for h in holes] or ["- 无"])
L += ["", "## 异常与已知限制", "",
      "1. **法院层级筛选非穷尽**：对 死者 2018.9.9-9.15（total=51）按四档法院切分，"
      "最高人民法院=0、高级人民法院=0、中级人民法院=3、基层人民法院=0，合计仅 3 条（漏 48 条）。"
      "该维度全程未再使用；受影响的 4 个文件已标注在 manifest 中。",
      "2. 区间过滤后 total 与全局普查差 5 条：已死亡 208 vs 210、死者 283 vs 286，"
      "应在 2008 年前或 2026 年后，未纳入本轮范围。",
      "3. 每次调用只返回 20 条且无翻页；同一父片与其子片返回的记录有重叠，"
      "因此 count 之和（1223）大于去重后的实际案例数。"]
L += [f"4. {e}" for e in out['errors']] or ["4. 无其他报错"]
open(os.path.join(D, '_未拿全清单.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print("FINAL:", out['calls_used'], CAP, "files", out['files'], "cases", out['cases_sum'],
      "notfull", len(not_full), "batches", len(batches), "holes", len(holes), cov)
