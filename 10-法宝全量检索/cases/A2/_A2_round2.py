#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 第二轮：用已落盘样本的日期分布挑切点，把剩余预算（11 次）用在最可能切透的片上。
仍然只调用 scripts/pku.py search，一次调用一个 --out 文件。"""
import json, os, subprocess, datetime

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
OUTDIR = os.path.join(ROOT, 'cases/A2')
CAP = 75
USED = 64          # 已用：1 次试跑 + 63 次驱动
HOLES_EXPECTED = [('死者', '2021.1.1', '2021.12.31')]

# (关键词, start, end, 依据)  —— 切点由父片样本的月度分布挑出（两侧估计均 <=20）
PLAN = [
    ('身亡',    '2017.1.1',  '2018.12.31', '样本 2017-2018 占 11/20 → 估 15.4/12.6'),
    ('身亡',    '2019.1.1',  '2021.12.31', '同上右片'),
    ('已死亡',  '2008.1.1',  '2016.7.31',  '样本切点 2016.7.31 → 估 16.5/16.5'),
    ('已死亡',  '2016.8.1',  '2016.12.31', '同上右片'),
    ('已死亡',  '2022.1.1',  '2025.3.31',  '样本切点 2025.3.31 → 估 17.1/14.0'),
    ('已死亡',  '2025.4.1',  '2026.12.31', '同上右片'),
    ('死者',    '2022.1.1',  '2024.9.30',  '样本切点 2024.9.30 → 估 14.4/17.6'),
    ('死者',    '2024.10.1', '2026.12.31', '同上右片'),
    ('死亡证明', '2017.1.1',  '2017.5.31',  '样本切点 2017.5.31 → 估 14.5/14.5'),
    ('死亡证明', '2017.6.1',  '2018.6.30',  '同上右片'),
    ('死者',    '2021.1.1',  '2021.12.31', '补漏：2020-2021 拆分时缺的右片'),
]

calls = USED
errors = []


def fmt(s):
    return s


def run(kw, s, e):
    global calls
    lab = f"{s}-{e}"
    out = os.path.join(OUTDIR, f"{kw}__{lab}__all__all.json")
    cmd = ['python3', os.path.join(ROOT, 'scripts/pku.py'), 'search', '--keyword', kw,
           '--start', s, '--end', e, '--out', out]
    calls += 1
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, AGENT_TAG='A2'))
        r = json.loads((p.stdout or '').strip().splitlines()[-1])
        total, count, err = r.get('total'), r.get('count'), r.get('error')
    except Exception as ex:
        total, count, err = None, 0, f'round2-exc: {ex}'
    print(f"[{calls}/{CAP}] {kw} {lab} -> total={total} count={count} err={err}", flush=True)
    return total, count, os.path.relpath(out, ROOT), err


def P(s):
    return datetime.date(*map(int, s.split('.')))


def main():
    m = json.load(open(os.path.join(OUTDIR, '_manifest.json')))
    sl = m['slices']
    for kw, s, e, why in PLAN:
        if calls >= CAP:
            errors.append(f"预算耗尽，未执行 {kw} {s}-{e}")
            continue
        total, count, f, err = run(kw, s, e)
        if err:
            errors.append(f"{kw} {s}-{e} 失败: {err}")
        sl.append({"kw": kw, "start": s, "end": e, "court": "", "total": total,
                   "count": count, "file": f, "fully": bool(total is not None and total <= 20),
                   "note": why})
    # --- 重算叶子与缺口（按真实日期比较） ---
    def contained(a, b):
        if a['kw'] != b['kw'] or a['court'] != b['court']:
            return False
        if not a['start'] or not a['end'] or not b['start'] or not b['end']:
            return False
        return (P(a['start']) <= P(b['start']) and P(b['end']) <= P(a['end'])) and \
               (a['start'], a['end']) != (b['start'], b['end'])
    leaves = [a for a in sl if not any(contained(a, b) for b in sl)]
    not_full = []
    batches = []
    for a in sorted(leaves, key=lambda x: -(x['total'] or 0)):
        if (a['total'] or 0) <= 20:
            continue
        # 批量同源检测：样本 20 条是否同一法院 + 同一审结日期（主智能体广播规则④）
        p = os.path.join(ROOT, a['file'])
        batch = False
        if os.path.exists(p):
            cs = json.load(open(p))['cases']
            batch = bool(cs) and len(set(c['法院'] for c in cs)) == 1 and \
                len(set(c['审结日期'] for c in cs)) == 1
        if batch:
            batches.append(f"{a['kw']} {a['start']}-{a['end']} (total={a['total']})")
        not_full.append({"kw": a['kw'], "span": f"{a['start']}-{a['end']}", "court": a['court'],
                         "total": a['total'], "got": min(a['count'], 20),
                         "batch": batch,
                         "note": ("批量同源（同一法院+同一日期），按广播规则④记为未展开，不向下钻取"
                                  if batch else
                                  f"仅取回 {a['count']}/{a['total']} 条，预算已用尽未再细分")})
    # --- 区间空洞检查 ---
    holes = []
    for kw in ['已死亡', '身亡', '死亡证明', '死者']:
        iv = sorted([(P(x['start']), P(x['end'])) for x in leaves
                     if x['kw'] == kw and x['start'] and x['end']])
        cur = datetime.date(2008, 1, 1)
        end = datetime.date(2026, 12, 31)
        for (a, b) in iv:
            if a > cur:
                holes.append(f"{kw} {cur}~{a - datetime.timedelta(days=1)} 未检索")
            cur = max(cur, b + datetime.timedelta(days=1))
        if cur <= end:
            holes.append(f"{kw} {cur}~{end} 未检索")
    out = {"agent": "A2", "keywords": ['已死亡', '身亡', '死亡证明', '死者'],
           "calls_used": calls, "call_cap": CAP,
           "method": ("自适应 best-first 时间二分切片（每片 <=20 即拿全）；切点用父片已落盘样本的"
                      "月度分布挑选，使两侧估计均 <=20。第二轮共 11 次调用。"
                      "★ 法院层级维度不可用：对 total=51 的片按四档法院切分，四片合计仅 3 条，"
                      "该维度非穷尽，故全程未再使用。"),
           "range": "2008.1.1~2026.12.31",
           "files": len(sl), "cases_sum": sum(x['count'] for x in sl),
           "slices": sl, "not_fully_retrieved": not_full, "coverage_holes": holes,
           "batches_not_expanded": batches, "errors": errors}
    with open(os.path.join(OUTDIR, '_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    lines = ["# A2 未拿全清单", "",
             f"- 调用：{calls}/{CAP}（16 个关键词总计 681 条中，未拿全部分见下表）",
             f"- 落盘文件：{len(sl)}；count 合计（未去重）：{out['cases_sum']}",
             f"- 未拿全切片数：{len(not_full)}", "",
             "| 关键词 | 区间 | 法院 | total | 已得 | 原因 |", "|---|---|---|---|---|---|"]
    for n in not_full:
        lines.append(f"| {n['kw']} | {n['span']} | {n['court'] or 'all'} | {n['total']} | "
                     f"{n['got']} | {n['note']} |")
    lines += ["", "## 未检索的日期空洞", ""] + ([f"- {h}" for h in holes] or ["- 无"])
    lines += ["", "## 批量同源未展开（主智能体规则④）", ""] + \
             ([f"- {b}" for b in batches] or ["- 无"])
    lines += ["", "## 异常与已知限制", "",
              "- **法院层级筛选非穷尽**：对 死者 2018.9.9-9.15（total=51）按四档法院切分，"
              "最高人民法院=0、高级人民法院=0、中级人民法院=3、基层人民法院=0，合计仅 3 条。"
              "该维度会漏数据，全程未再使用（仅该 4 个文件受影响，见 files）。",
              "- 2008-2026 区间过滤后的 total 与全局普查略有差：已死亡 208 vs 210、死者 283 vs 286，"
              "差 5 条应在 2008 年之前或 2026 年之后，未纳入。"]
    lines += [f"- {e}" for e in errors] or ["- 无其他报错"]
    with open(os.path.join(OUTDIR, '_未拿全清单.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"ROUND2 DONE calls={calls}/{CAP} slices={len(sl)} cases={out['cases_sum']} "
          f"notfull={len(not_full)} holes={len(holes)}", flush=True)


if __name__ == '__main__':
    main()
