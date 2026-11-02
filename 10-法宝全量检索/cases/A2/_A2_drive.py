#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2 自适应切片驱动器（best-first 二分切片）
- 唯一检索工具：scripts/pku.py search（本脚本只做调度，不另发请求）
- 硬预算：CAP 次调用，达到即停
- 每次调用一个 --out 文件，命名遵守作业协议
- 每调用一次即刷新 _manifest.json / _未拿全清单.md
"""
import json, os, subprocess, sys, heapq, datetime, time

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
OUTDIR = os.path.join(ROOT, 'cases/A2')
LOGDIR = os.path.join(ROOT, 'logs')
KEYWORDS = ['已死亡', '身亡', '死亡证明', '死者']
GLOBAL_TOTALS = {'已死亡': 210, '身亡': 61, '死亡证明': 124, '死者': 286}
CAP = 75
RANGE_START = datetime.date(2008, 1, 1)
RANGE_END = datetime.date(2026, 12, 31)
COURTS = ['最高人民法院', '高级人民法院', '中级人民法院', '基层人民法院']
MIN_SPAN_DAYS = 12

calls = 1   # 已用 1 次：开跑前用 pku.py 试跑过一次「身亡」整区间（_probe.json）
slices_log = []
not_full = []
errors = []
seq = 0


def fmt(d):
    return f"{d.year}.{d.month}.{d.day}"


def span_label(s, e):
    if s is None and e is None:
        return 'all'
    if s is not None and e is not None:
        if s.month == 1 and s.day == 1 and e.month == 12 and e.day == 31 and s.year == e.year:
            return str(s.year)
    return f"{fmt(s) if s else 'earliest'}-{fmt(e) if e else 'latest'}"


def run_search(kw, s, e, court):
    """调用 pku.py search 一次；返回 (total, count, outfile, err)"""
    global calls, seq
    seq += 1
    lab = span_label(s, e)
    clab = court if court else 'all'
    fn = f"{kw}__{lab}__{clab}__all.json"
    out = os.path.join(OUTDIR, fn)
    cmd = ['python3', os.path.join(ROOT, 'scripts/pku.py'), 'search', '--keyword', kw,
           '--out', out]
    if s is not None:
        cmd += ['--start', fmt(s)]
    if e is not None:
        cmd += ['--end', fmt(e)]
    if court:
        cmd += ['--court', court]
    env = dict(os.environ, AGENT_TAG='A2')
    calls += 1
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=240, env=env)
        r = json.loads((p.stdout or '').strip().splitlines()[-1])
        total, count, err = r.get('total'), r.get('count'), r.get('error')
    except Exception as ex:
        total, count, err = None, 0, f"driver-exc: {ex}"
    print(f"[{calls:02d}/{CAP}] {kw} {lab} {clab} -> total={total} count={count} err={err}",
          flush=True)
    return total, count, out, err


def query(kw, s, e, court):
    """带 1 次重试的查询；返回 (total,count,out,err)"""
    total, count, out, err = run_search(kw, s, e, court)
    if err is not None or total is None:
        if calls < CAP:
            print(f"    retry after err={err}", flush=True)
            total, count, out, err = run_search(kw, s, e, court)
    return total, count, out, err


def split_date(s, e):
    """按二分点切分日期区间，切点吸附到年/月边界"""
    days = (e - s).days
    if days < MIN_SPAN_DAYS:
        return []
    mid = s + datetime.timedelta(days=days // 2)
    cut = None
    if days >= 365 * 4:            # 吸附到年末
        cands = []
        for y in (mid.year - 1, mid.year, mid.year + 1):
            cands.append(datetime.date(y, 12, 31))
        cut = min([c for c in cands if s < c < e] or [mid], key=lambda c: abs((c - mid).days))
    elif days >= 45:               # 吸附到月末
        cands = []
        d = datetime.date(mid.year, mid.month, 1)
        for k in (-1, 0, 1):
            y = mid.year + (mid.month - 1 + k) // 12
            m = (mid.month - 1 + k) % 12 + 1
            nm = datetime.date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
            cands.append(nm - datetime.timedelta(days=1))
        cut = min([c for c in cands if s < c < e] or [mid], key=lambda c: abs((c - mid).days))
    else:
        cut = mid
    if not (s < cut < e):
        return []
    return [(s, cut), (cut + datetime.timedelta(days=1), e)]


def children(sl):
    s, e, court = sl['s'], sl['e'], sl['court']
    kids = []
    if s is not None and e is not None:
        for (a, b) in split_date(s, e):
            kids.append({'kw': sl['kw'], 's': a, 'e': b, 'court': court})
    if not kids and not court:      # 时间切不动 -> 按法院层级切
        for c in COURTS:
            kids.append({'kw': sl['kw'], 's': s, 'e': e, 'court': c})
    return kids


def flush_manifest():
    man = {
        "agent": "A2",
        "keywords": KEYWORDS,
        "calls_used": calls,
        "call_cap": CAP,
        "method": ("自适应 best-first 二分切片：先整区间探测，再对 total>20 的最大片按时间二分"
                   "（切点吸附年/月末）；时间切到 <12 天仍 >20 时改按法院层级切 4 片。"
                   "每片 <=20 即视为拿全。"),
        "range": "2008.1.1~2026.12.31",
        "slices": slices_log,
        "not_fully_retrieved": not_full,
    }
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, '_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    lines = ["# A2 未拿全清单", "",
             f"- 调用：{calls}/{CAP}", f"- 未拿全切片数：{len(not_full)}", "",
             "| 关键词 | 区间 | 法院 | total | 已得 | 原因 |", "|---|---|---|---|---|---|"]
    for n in not_full:
        lines.append(f"| {n['kw']} | {n['span']} | {n['court'] or 'all'} | {n['total']} | "
                     f"{n['got']} | {n['note']} |")
    lines += ["", "## 异常", ""]
    lines += [f"- {x}" for x in errors] or ["- 无"]
    with open(os.path.join(OUTDIR, '_未拿全清单.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def add_slice_log(kw, s, e, court, total, count, out, fully):
    slices_log.append({"kw": kw, "start": fmt(s) if s else "", "end": fmt(e) if e else "",
                       "court": court or "", "total": total, "count": count,
                       "file": os.path.relpath(out, ROOT), "fully": fully})


def main():
    t0 = time.time()
    heap = []
    counter = 0
    # 阶段一：每个关键词整区间探测
    for kw in KEYWORDS:
        total, count, out, err = query(kw, RANGE_START, RANGE_END, '')
        if err is not None or total is None:
            errors.append(f"{kw} 整区间探测失败: {err}")
            add_slice_log(kw, RANGE_START, RANGE_END, '', total, count, out, False)
            not_full.append({"kw": kw, "span": "2008.1.1-2026.12.31", "court": "",
                             "total": total, "got": count, "note": f"探测失败 {err}"})
            flush_manifest()
            continue
        exp = GLOBAL_TOTALS.get(kw)
        if exp is not None and total != exp:
            errors.append(f"{kw} 区间 total={total} 与全局普查 {exp} 不一致（可能有区间外数据）")
        ok = total <= 20
        add_slice_log(kw, RANGE_START, RANGE_END, '', total, count, out, ok)
        if not ok:
            counter += 1
            heapq.heappush(heap, (-total, counter, {'kw': kw, 's': RANGE_START,
                                                    'e': RANGE_END, 'court': ''}))
        flush_manifest()
    # 阶段二：best-first 细化
    while heap:
        negt, _, sl = heapq.heappop(heap)
        if calls + 2 > CAP:
            not_full.append({"kw": sl['kw'], "span": f"{fmt(sl['s'])}-{fmt(sl['e'])}",
                             "court": sl['court'], "total": -negt, "got": 20,
                             "note": "预算耗尽，未继续切分"})
            flush_manifest()
            continue
        kids = children(sl)
        if not kids:
            not_full.append({"kw": sl['kw'], "span": f"{fmt(sl['s'])}-{fmt(sl['e'])}",
                             "court": sl['court'], "total": -negt, "got": 20,
                             "note": "时间+法院两个维度均已切到底，仍 >20"})
            flush_manifest()
            continue
        for k in kids:
            if calls >= CAP:
                not_full.append({"kw": k['kw'], "span": f"{fmt(k['s'])}-{fmt(k['e'])}",
                                 "court": k['court'], "total": None, "got": 0,
                                 "note": "预算耗尽，该子片未查询"})
                flush_manifest()
                continue
            total, count, out, err = query(k['kw'], k['s'], k['e'], k['court'])
            if err is not None or total is None:
                errors.append(f"{k['kw']} {fmt(k['s'])}-{fmt(k['e'])} {k['court']} 失败: {err}")
                add_slice_log(k['kw'], k['s'], k['e'], k['court'], total, count, out, False)
                not_full.append({"kw": k['kw'], "span": f"{fmt(k['s'])}-{fmt(k['e'])}",
                                 "court": k['court'], "total": total, "got": count,
                                 "note": f"查询失败 {err}"})
                flush_manifest()
                continue
            ok = total <= 20
            add_slice_log(k['kw'], k['s'], k['e'], k['court'], total, count, out, ok)
            if not ok:
                counter += 1
                heapq.heappush(heap, (-total, counter, k))
            flush_manifest()
    flush_manifest()
    tot = sum(s['count'] for s in slices_log)
    print(f"DONE calls={calls}/{CAP} files={len(slices_log)} cases={tot} "
          f"not_full={len(not_full)} elapsed={time.time()-t0:.0f}s", flush=True)


if __name__ == '__main__':
    main()
