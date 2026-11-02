#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A6 驱动器 v4 —— 仅通过 scripts/pku.py 调法宝。
关键词: 死亡   年份: 2008-2017   调用上限: 120

实测结论: court 参数是"真实法院名子串匹配"(非层级 4 分区), doc 亦非穷尽,
故唯一可靠分区维度 = 审结日期。采用 k 路等日期长度切分 (k=ceil(T/15)),
把内部节点开销压到最低; 每片 <=20 即拿全。年为顺序推进, 余额向后结转。
"""
import json, os, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
OUTDIR = os.path.join(ROOT, 'cases/A6')
KW = '死亡'
CAP = 120
CONC = 4
TARGET = 15          # 目标叶子规模(<20)
STATE = os.path.join(OUTDIR, '_state.json')

YEARS = {2008: 0, 2009: 1, 2010: 3, 2011: 2, 2012: 11,
         2013: 25, 2014: 156, 2015: 150, 2016: 668, 2017: 800}
TODO = [2013, 2014, 2015, 2016, 2017]
LIMIT = {2013: 5, 2014: 18, 2015: 18, 2016: 33, 2017: 29}

lock = threading.Lock()
state = {'calls': 0, 'slices': [], 'notfull': [], 'errors': []}
if os.path.exists(STATE):
    state = json.load(open(STATE, encoding='utf-8'))


def save():
    with lock:
        json.dump(state, open(STATE, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)


def lbl(d1, d2, y):
    if d1 == date(y, 1, 1) and d2 == date(y, 12, 31):
        return 'all'
    return 'D%02d%02d-%02d%02d' % (d1.month, d1.day, d2.month, d2.day)


def do_call(year, d1, d2, budget):
    with lock:
        if state['calls'] >= CAP or budget[0] <= 0:
            return None
    label = lbl(d1, d2, year)
    fname = '%s__%d__all__%s.json' % (KW, year, label)
    out = os.path.join(OUTDIR, fname)
    start = '%d.%d.%d' % (year, d1.month, d1.day)
    end = '%d.%d.%d' % (year, d2.month, d2.day)
    cmd = ['python3', 'scripts/pku.py', 'search', '--keyword', KW,
           '--start', start, '--end', end, '--out', out]
    env = dict(os.environ, AGENT_TAG='A6')
    res = None
    for _ in (1, 2):
        with lock:
            if state['calls'] >= CAP or budget[0] <= 0:
                return None
            state['calls'] += 1      # 每次真实执行计 1 次
            budget[0] -= 1
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            res = {'total': None, 'count': 0, 'error': (r.stdout + r.stderr)[:200]}
        if not res.get('error') and res.get('total') is not None:
            break
    rec = {'kw': KW, 'year': year, 'start': start, 'end': end, 'court': '',
           'label': label, 'total': res.get('total'), 'count': res.get('count'),
           'error': res.get('error'), 'file': 'cases/A6/' + fname}
    with lock:
        state['slices'].append(rec)
        if rec['error'] or rec['total'] is None:
            state['errors'].append(rec)
    save()
    print('  [%3d] %d %s -> total=%s count=%s %s' % (
        state['calls'], year, label, res.get('total'), res.get('count'),
        'ERR' if rec['error'] else ''))
    sys.stdout.flush()
    return rec


def split(d1, d2, total):
    """k 路等日期长度切分; 返回 [(a,b), ...]"""
    ndays = (d2 - d1).days + 1
    k = max(2, min(-(-total // TARGET), ndays))
    out, a = [], d1
    for i in range(k):
        b = d1 + timedelta(days=(ndays * (i + 1)) // k - 1)
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


def main():
    done = {s['file'] for s in state['slices']}
    for y in sorted(YEARS):
        f = 'cases/A6/%s__%d__all__all.json' % (KW, y)
        if f not in done:
            state['slices'].append({
                'kw': KW, 'year': y, 'start': '%d.1.1' % y, 'end': '%d.12.31' % y,
                'court': '', 'label': 'all', 'total': YEARS[y],
                'count': min(20, YEARS[y]), 'error': None, 'file': f})
    state['slices'] = [s for s in state['slices'] if s.get('court') in ('', None)]
    save()

    pool = ThreadPoolExecutor(max_workers=CONC)
    carry = 0
    for year in TODO:
        lim = LIMIT[year] + carry
        with lock:
            lim = min(lim, CAP - state['calls'])
        budget = [lim]
        print('===== %d (total=%d) 本年预算 %d =====' % (year, YEARS[year], lim))
        if lim <= 0:
            state['notfull'].append({'kw': KW, 'year': year, 'court': 'all',
                                     'start': '%d.1.1' % year, 'end': '%d.12.31' % year,
                                     'total': YEARS[year], 'note': '全局预算耗尽，本年未展开'})
            save()
            continue
        wave = split(date(year, 1, 1), date(year, 12, 31), YEARS[year])
        while wave:
            with lock:
                if budget[0] <= 0 or state['calls'] >= CAP:
                    for (a, b) in wave:
                        state['notfull'].append({
                            'kw': KW, 'year': year, 'court': 'all',
                            'start': '%d.%d.%d' % (year, a.month, a.day),
                            'end': '%d.%d.%d' % (year, b.month, b.day),
                            'total': None, 'note': '该年预算/全局上限耗尽，未展开'})
                    save()
                    break
            futs = [pool.submit(do_call, year, a, b, budget) for (a, b) in wave]
            nxt = []
            for f in futs:
                rec = f.result()
                if rec is None or rec['total'] is None:
                    continue
                if rec['total'] > 20:
                    a, b = _p(rec['start']), _p(rec['end'])
                    if a == b:
                        with lock:
                            state['notfull'].append({
                                'kw': KW, 'year': year, 'court': 'all',
                                'start': rec['start'], 'end': rec['end'],
                                'total': rec['total'],
                                'note': '单日仍 >20，法宝单次上限 20，无法再细分'})
                        save()
                    else:
                        nxt.extend(split(a, b, rec['total']))
            wave = nxt
        carry = max(0, budget[0])
        print('  -- %d 结束, 用 %d 次, 结转 %d, 累计 %d --'
              % (year, lim - budget[0], carry, state['calls']))
    pool.shutdown(wait=True)
    print('===== DONE =====')


def _p(s):
    y, m, d = s.split('.')
    return date(int(y), int(m), int(d))


if __name__ == '__main__':
    main()
    save()
