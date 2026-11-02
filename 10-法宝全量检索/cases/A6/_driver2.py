#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A6 驱动器 v5 (续跑) —— 仅通过 scripts/pku.py 调法宝。
对 [2016, 2017] 做"可续跑"的 k 路日期切分:
  * 每个日期片对应唯一文件名; 若文件已存在则直接读缓存(不消耗调用)
  * 仅当 total>20 才继续向下切
预算: 全局 160 次(A6 新上限)。
"""
import json, os, subprocess, sys, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

ROOT = '/home/heqihan/dsh/A4-法宝全量检索'
OUTDIR = os.path.join(ROOT, 'cases/A6')
KW = '死亡'
CAP = int(os.environ.get('A6_CAP', '160'))
CONC = 4
TARGET = 15
STATE = os.path.join(OUTDIR, '_state.json')

YEARS = {2015: 150, 2016: 668, 2017: 800}
TODO = [(2016, 2016, 11)]   # (名称,年,预算)

lock = threading.RLock()   # 可重入: save() 会在持锁时被调用
state = json.load(open(STATE, encoding='utf-8'))


def save():
    with lock:
        json.dump(state, open(STATE, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)


def lbl(d1, d2, y):
    if d1 == date(y, 1, 1) and d2 == date(y, 12, 31):
        return 'all'
    return 'D%02d%02d-%02d%02d' % (d1.month, d1.day, d2.month, d2.day)


def cache_path(year, d1, d2):
    return os.path.join(OUTDIR, '%s__%d__all__%s.json' % (KW, year, lbl(d1, d2, year)))


def read_cache(year, d1, d2):
    p = cache_path(year, d1, d2)
    if not os.path.exists(p):
        return None
    try:
        j = json.load(open(p, encoding='utf-8'))
    except Exception:
        return None
    if j.get('error') or j.get('total') is None:
        return None
    return {'kw': KW, 'year': year,
            'start': j['query']['startLastInstanceDate'],
            'end': j['query']['endLastInstanceDate'], 'court': '',
            'label': lbl(d1, d2, year), 'total': j.get('total'),
            'count': j.get('count'), 'error': None,
            'file': 'cases/A6/' + os.path.basename(p), 'cached': True}


def do_call(year, d1, d2, budget, stats):
    cached = read_cache(year, d1, d2)
    if cached is not None:
        stats['cached'] += 1
        return cached
    with lock:
        if state['calls'] >= CAP or budget[0] <= 0:
            return None
    start = '%d.%d.%d' % (year, d1.month, d1.day)
    end = '%d.%d.%d' % (year, d2.month, d2.day)
    fname = '%s__%d__all__%s.json' % (KW, year, lbl(d1, d2, year))
    out = os.path.join(OUTDIR, fname)
    cmd = ['python3', 'scripts/pku.py', 'search', '--keyword', KW,
           '--start', start, '--end', end, '--out', out]
    env = dict(os.environ, AGENT_TAG='A6')
    res = None
    for _ in (1, 2):
        with lock:
            if state['calls'] >= CAP or budget[0] <= 0:
                return None
            state['calls'] += 1
            budget[0] -= 1
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        try:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            res = {'total': None, 'count': 0, 'error': (r.stdout + r.stderr)[:200]}
        if not res.get('error') and res.get('total') is not None:
            break
    rec = {'kw': KW, 'year': year, 'start': start, 'end': end, 'court': '',
           'label': lbl(d1, d2, year), 'total': res.get('total'),
           'count': res.get('count'), 'error': res.get('error'),
           'file': 'cases/A6/' + fname, 'cached': False}
    with lock:
        state['slices'] = [s for s in state['slices'] if s['file'] != rec['file']]
        state['slices'].append(rec)
        if rec['error'] or rec['total'] is None:
            state['errors'].append(rec)
    save()
    print('  [%3d] %d %s -> total=%s count=%s %s' % (
        state['calls'], year, rec['label'], res.get('total'), res.get('count'),
        'ERR' if rec['error'] else ''))
    sys.stdout.flush()
    return rec


def split(d1, d2, total):
    ndays = (d2 - d1).days + 1
    k = max(2, min(-(-total // TARGET), ndays))
    out, a = [], d1
    for i in range(k):
        b = d1 + timedelta(days=(ndays * (i + 1)) // k - 1)
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


def main():
    pool = ThreadPoolExecutor(max_workers=CONC)
    for (name, year, lim0) in TODO:
        name = str(year)
        with lock:
            lim = min(lim0, CAP - state['calls'])
        budget = [lim]
        stats = {'cached': 0}
        print('===== %s (total=%d) 本年预算 %d =====' % (name, YEARS[year], lim))
        wave = split(date(year, 1, 1), date(year, 12, 31), YEARS[year])
        while wave:
            with lock:
                if budget[0] <= 0 or state['calls'] >= CAP:
                    for (a, b) in wave:
                        state['notfull'].append({
                            'kw': KW, 'year': year, 'court': 'all',
                            'start': '%d.%d.%d' % (year, a.month, a.day),
                            'end': '%d.%d.%d' % (year, b.month, b.day),
                            'total': None, 'note': '全局上限 160 耗尽，未展开'})
                    save()
                    break
            futs = [pool.submit(do_call, year, a, b, budget, stats) for (a, b) in wave]
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
        print('  -- %s 结束, 用 %d 次 (缓存命中 %d), 累计 %d --'
              % (name, lim - budget[0], stats['cached'], state['calls']))
    pool.shutdown(wait=True)
    print('===== DONE =====')


def _p(s):
    y, m, d = s.split('.')
    return date(int(y), int(m), int(d))


if __name__ == '__main__':
    main()
    save()
