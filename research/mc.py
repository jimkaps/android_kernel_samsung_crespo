import numpy as np, pandas as pd
from lucid_ibs import build, COST_PER_MNQ, STOP_SLIP_PTS, GBP, FEE_GBP
rng = np.random.default_rng(1)
def trades(q, stop, start='2013'):
    q = q[(q.index >= start) & q.sig]
    stopped = q.ol <= -stop
    r = np.where(stopped, -stop - STOP_SLIP_PTS / q.px, q.oc)      # % return
    w = np.where(stopped, r, q.ol)
    return r, w, len(q) / ((q.index[-1] - q.index[0]).days / 365.25)
def one_account(r, w, n_mnq_pts, keep=1000, max_days=2000):
    """returns (passed, payouts_usd, trades_used). r,w in % ; sizing as $ per 1% move."""
    phase='eval'; bal=50000; peak=50000; floor=48000; cd=0; cp=0; paid=0; npay=0
    idx = rng.integers(0, len(r), max_days)
    for k, i in enumerate(idx):
        pnl = r[i] * n_mnq_pts; worst = min(w[i], r[i]) * n_mnq_pts
        if bal + worst <= floor: return phase != 'eval', paid, k
        bal += pnl; peak = max(peak, bal)
        if floor < 50100: floor = min(50100, max(floor, peak - 2000))
        if phase == 'eval':
            if bal >= 53000: phase='funded'; bal=50000; peak=50000; floor=48000
        else:
            cp += pnl; cd += pnl >= 150; amt = min(2000, .5 * cp)
            if cd >= 5 and cp > 0 and amt >= 500 and bal - amt - 50100 >= keep:
                bal -= amt; floor = 50100; peak = bal; paid += amt; npay += 1; cd = 0; cp = 0
                if npay >= 5: return True, paid, k
    return phase != 'eval', paid, max_days
print('signal             stop   risk$ | trades/yr  avg$/trade win  | pass%  avg payouts$/eval  EV GBP/eval  yrs/eval  GBP/yr (1 acct at a time)')
for name, kw in [('DOUBLE<0.3', dict(sig_x=0.3)), ('DOUBLE<0.4', dict(sig_x=0.4)), ('DOUBLE<0.3|IBS<0.1', dict(sig_x=0.3, single_x=0.1)), ('IBS<0.2 (single)', dict(sig_x=-1, single_x=0.2))]:
    q = build(**kw); px = q.px[q.index >= '2025'].mean()
    for stop in (0.0075, 0.01, 0.02):
        r, w, tpy = trades(q, stop)
        for risk in (300, 500, 800):
            n = max(1, int(risk / (stop * px * 2)))
            dollars_per_unit = n * 2 * px                      # $ per 100% move  -> pnl = r * this
            cost = n * COST_PER_MNQ
            rr = r - cost / dollars_per_unit; ww = w - cost / dollars_per_unit
            sims = [one_account(rr, ww, dollars_per_unit) for _ in range(3000)]
            p = np.mean([s[0] for s in sims]); pay = np.mean([s[1] for s in sims]); tr = np.mean([s[2] for s in sims])
            ev = pay * .9 * GBP - FEE_GBP; yrs = tr / tpy
            print(f'{name:18s} {stop*100:4.2f}% {risk:5d}({n:2d}MNQ) | {tpy:5.0f} {rr.mean()*dollars_per_unit:+8.0f} {np.mean(rr>0):.0%} | {p:5.0%} {pay:10.0f} {ev:+10.0f} {yrs:7.1f} {ev/yrs:+8.0f}')
