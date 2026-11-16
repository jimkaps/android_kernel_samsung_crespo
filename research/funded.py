"""Funded-account version of the IBS strategy (flat EOD), with parameter search + walk-forward.
Day t signal (from RTH day bars, QQQ as NQ-RTH proxy):  IBS<dbl two days running  OR  IBS<single
Trade t+1: buy at 09:30 open, take-profit +tp (0 = none), stop -stop, else exit at close.
           Daily bars can't tell which came first if both TP and stop are inside the day -> assume STOP (conservative).
Sizing  : risk per trade = k * cushion (cushion = balance - drawdown floor), contracts = floor(risk / stop$), min 1.
Account : LucidFlex 50K per lucidflex_50k_rules.md (eval +3000; EOD trailing 2000 floor capped 50,100; payout after
          5 days >= $150 & cycle>0, amount min(2000, 50% cycle), >=500, keep `keep` cushion after; 90% split; 5 payouts max).
All returns in %, MNQ notional fixed at NQ 25,000 ($50k/contract) so old years are comparable to today.
"""
import numpy as np, pandas as pd, itertools, sys
from numba import njit
NOTIONAL = 50000.0          # $ per MNQ (2 x 25,000)
COST = 4.0                  # $ per MNQ round trip
SLIP = 2.0                  # extra $ per MNQ on a stop (1 point)
GBP, FEE = 0.77, 150.0

def load():
    q = pd.read_csv('QQQ.csv', index_col=0, parse_dates=True)[['Open','High','Low','Close']].dropna()
    q = q[q.High > q.Low]; q['ibs'] = (q.Close - q.Low) / (q.High - q.Low)
    q['oh'] = (q.High / q.Open - 1).shift(-1); q['ol'] = (q.Low / q.Open - 1).shift(-1); q['oc'] = (q.Close / q.Open - 1).shift(-1)
    return q.dropna()      # row t: today's IBS + NEXT day's open-relative high/low/close

@njit(cache=True)
def run_accounts(sig, oh, ol, oc, tp, stop, k, keep, n_acc, seed, block, n_eval, n_fund):
    np.random.seed(seed); N = len(sig)
    pays = np.zeros(n_acc); days = np.zeros(n_acc); passed = np.zeros(n_acc)
    for a in range(n_acc):
        phase = 0; bal = 50000.0; peak = 50000.0; floor = 48000.0; cd = 0; cp = 0.0; npay = 0; paid = 0.0
        d = 0; pos = np.random.randint(0, N - block); left = block
        while True:
            if left == 0: pos = np.random.randint(0, N - block); left = block
            i = pos; pos += 1; left -= 1; d += 1
            if d > 252 * 15: break
            if not sig[i]: continue
            cushion = bal - floor
            n = int(k * cushion / (stop * NOTIONAL + SLIP))
            if n < 1: n = 1
            if k == 0.0: n = n_eval if phase == 0 else n_fund
            if ol[i] <= -stop:
                r = -stop * NOTIONAL - SLIP; w = r
            elif tp > 0 and oh[i] >= tp:
                r = tp * NOTIONAL; w = max(ol[i], -stop) * NOTIONAL
            else:
                r = oc[i] * NOTIONAL; w = ol[i] * NOTIONAL
            pnl = n * (r - COST); worst = n * (min(w, r) - COST)
            if bal + worst <= floor: break
            bal += pnl
            if bal > peak: peak = bal
            if floor < 50100.0:
                floor = max(floor, min(50100.0, peak - 2000.0))
            if phase == 0:
                if bal >= 53000.0:
                    phase = 1; passed[a] = 1; bal = 50000.0; peak = 50000.0; floor = 48000.0
            else:
                cp += pnl
                if pnl >= 150.0: cd += 1
                amt = min(2000.0, 0.5 * cp)
                if cd >= 5 and cp > 0 and amt >= 500.0 and bal - amt - 50100.0 >= keep:
                    bal -= amt; floor = 50100.0; peak = bal; paid += amt; npay += 1; cd = 0; cp = 0.0
                    if npay >= 5: break
        pays[a] = paid; days[a] = d
    return pays, days, passed

def evaluate(q, dbl, single, tp, stop, k, keep, n_acc=3000, seed=1, n_eval=1, n_fund=1):
    sig = (((q.ibs < dbl) & (q.ibs.shift() < dbl)) | (q.ibs < single)).values
    p, d, ps = run_accounts(sig, q.oh.values, q.ol.values, q.oc.values, tp, stop, k, keep, n_acc, seed, 20, n_eval, n_fund)
    yrs = d.mean() / 252; ev = p.mean() * 0.9 * GBP - FEE
    return dict(pass_=ps.mean(), any_pay=(p > 0).mean(), pay=p.mean(), ev=ev, yrs=yrs, ev_yr=ev / yrs,
                tpy=sig.mean() * 252)

GRID = dict(dbl=[0.3, 0.4, 0.5], single=[0.0, 0.1, 0.2], tp=[0.0, 0.004, 0.006, 0.01],
            stop=[0.004, 0.006, 0.01], k=[0.1, 0.2, 0.35], keep=[500.0, 1000.0])

if __name__ == '__main__':
    q = load(); IS = q[(q.index >= '2005') & (q.index < '2017')]; OOS = q[q.index >= '2017']
    rows = []
    for combo in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, combo)); r = evaluate(IS, **kw, n_acc=1500); rows.append({**kw, **r})
    res = pd.DataFrame(rows).sort_values('ev_yr', ascending=False)
    res.to_csv('funded_grid_IS.csv', index=False)
    pd.set_option('display.width', 200)
    print('top 15 in-sample (2005-2016) by GBP/yr per account slot:')
    print(res.head(15).round(3).to_string(index=False))
    print('\nsame configs, OUT-OF-SAMPLE 2017-2026:')
    out = []
    for _, r in res.head(15).iterrows():
        kw = {c: r[c] for c in GRID}; o = evaluate(OOS, **kw, n_acc=4000, seed=2); out.append({**kw, **o})
    print(pd.DataFrame(out).round(3).to_string(index=False))
    base = dict(dbl=0.3, single=0.1, tp=0.0, stop=0.01, k=0.0, keep=1000.0)   # k=0 -> always 1 MNQ (previous version)
    print('\nprevious version (1 MNQ, no TP, 1% stop) OOS:', {k: round(v, 3) for k, v in evaluate(OOS, **base, n_acc=4000, seed=2).items()})
