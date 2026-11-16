"""Intraday (flat-EOD) double-IBS on MNQ through a LucidFlex 50K eval -> funded pipeline.
Signal: IBS of the regular-session day bar (QQQ RTH OHLC as proxy for NQ RTH) for 2 days in a row < X
Trade : buy at next RTH open (09:30 NY), exit at close (15:59) or at a stop of s% below entry.
Size  : MNQ contracts = floor(risk_usd / (s * price * $2)), so risk per trade is ~constant in $.
Rules (from lucidflex_50k_rules.md; several are [VERIFY]):
  eval   : start 50,000, pass at +3,000, EOD-trailing floor = max EOD bal - 2,000 (cap 50,100); fee GBP150
  funded : same floor logic; payout when >=5 days of >=$150 profit in the cycle and cycle net > 0;
           amount = min(2000, 50% cycle profit), >=500; 90% split; floor locks at 50,100 on payout;
           after 5 payouts the account is retired (counted as done) and a new eval is bought.
  breach : checked against the intraday worst point of the trade (conservative).
"""
import sys, numpy as np, pandas as pd
GBP = 0.77           # USD -> GBP
FEE_GBP = 150.0
COST_PER_MNQ = 4.0   # commission + 1 tick slippage each side, $ per round trip
STOP_SLIP_PTS = 1.0  # extra slippage on a stop, NQ points

def build(sig_x=0.3, single_x=None):
    q = pd.read_csv('QQQ.csv', index_col=0, parse_dates=True)[['Open','High','Low','Close']]
    nq = pd.read_csv('NQ_F.csv', index_col=0, parse_dates=True)['Close'].rename('nq')
    q = q.join(nq, how='inner').dropna(); q = q[q.High > q.Low]
    q['ibs'] = (q.Close - q.Low) / (q.High - q.Low)
    sig = (q.ibs < sig_x) & (q.ibs.shift() < sig_x)
    if single_x is not None: sig |= q.ibs < single_x
    q['sig'] = sig.shift().fillna(False).astype(bool)     # trade TODAY if yesterday's close gave the signal
    q['oc'] = q.Close / q.Open - 1; q['ol'] = q.Low / q.Open - 1
    q['px'] = q.nq.shift().bfill()                         # NQ price level known at entry
    return q

def simulate(q, stop=0.01, risk=400, keep=1000, start='2010-01-01', end='2027'):
    q = q[(q.index >= start) & (q.index < end)]
    rows = []; cash = 0.0; ev = dict(evals=0, passed=0, failed_eval=0, failed_funded=0, payouts=0, retired=0)
    def new_acct():
        nonlocal cash; cash -= FEE_GBP; ev['evals'] += 1
        return dict(phase='eval', bal=50000.0, peak=50000.0, floor=48000.0, cyc_days=0, cyc_pnl=0.0, npay=0)
    a = new_acct()
    for dt, r in q.iterrows():
        pnl = 0.0; worst = 0.0
        if r.sig:
            n = max(1, int(risk / (stop * r.px * 2)))
            if r.ol <= -stop:
                pts = -stop * r.px - STOP_SLIP_PTS; worst = pts
            else:
                pts = r.oc * r.px; worst = r.ol * r.px
            pnl = n * (2 * pts - COST_PER_MNQ); worst = n * (2 * worst - COST_PER_MNQ)
        if pnl != 0.0:
            if a['bal'] + worst <= a['floor']:             # breached during the day
                ev['failed_eval' if a['phase'] == 'eval' else 'failed_funded'] += 1
                a = new_acct(); rows.append((dt, cash)); continue
            a['bal'] += pnl
            a['peak'] = max(a['peak'], a['bal'])
            if a['floor'] < 50100: a['floor'] = min(50100.0, max(a['floor'], a['peak'] - 2000))
            if a['phase'] == 'eval':
                if a['bal'] >= 53000:
                    ev['passed'] += 1
                    a = dict(phase='funded', bal=50000.0, peak=50000.0, floor=48000.0, cyc_days=0, cyc_pnl=0.0, npay=0)
            else:
                a['cyc_pnl'] += pnl; a['cyc_days'] += pnl >= 150
                amt = min(2000.0, 0.5 * a['cyc_pnl'])
                if a['cyc_days'] >= 5 and a['cyc_pnl'] > 0 and amt >= 500 and a['bal'] - amt - 50100 >= keep:
                    a['bal'] -= amt; a['floor'] = 50100.0; a['peak'] = a['bal']
                    cash += 0.9 * amt * GBP; ev['payouts'] += 1; a['npay'] += 1
                    a['cyc_days'] = 0; a['cyc_pnl'] = 0.0
                    if a['npay'] >= 5: ev['retired'] += 1; a = new_acct()
        rows.append((dt, cash))
    curve = pd.Series(dict(rows))
    return curve, ev

if __name__ == '__main__':
    print('variant                         stop  risk$ | evals pass failE failF payouts retired | net GBP  GBP/yr  worstDD GBP')
    for name, kw in [('DOUBLE<0.3', dict(sig_x=0.3)), ('DOUBLE<0.35', dict(sig_x=0.35)),
                     ('DOUBLE<0.3 or IBS<0.1', dict(sig_x=0.3, single_x=0.1))]:
        q = build(**kw)
        for stop in (0.0075, 0.01, 0.015):
            for risk in (250, 400, 600):
                c, e = simulate(q, stop, risk)
                yrs = (c.index[-1] - c.index[0]).days / 365.25
                print(f'{name:30s} {stop*100:4.2f}% {risk:5d} | {e["evals"]:5d} {e["passed"]:4d} {e["failed_eval"]:5d} {e["failed_funded"]:5d} '
                      f'{e["payouts"]:7d} {e["retired"]:7d} | {c.iloc[-1]:7.0f} {c.iloc[-1]/yrs:7.0f} {(c - c.cummax()).min():8.0f}')
