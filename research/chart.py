import numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from lucid_ibs import build, simulate, GBP, FEE_GBP
import lucid_ibs
STOP, RISK = 0.01, 500
q = build(sig_x=0.3, single_x=0.1)
# --- historical path with event log
events = []
orig = simulate
curve, ev = simulate(q, STOP, RISK, start='2013-01-01')
d = curve.diff().fillna(curve.iloc[0])
fees = d[d < 0]; pays = d[d > 0]
print(ev, 'net', round(curve.iloc[-1]), 'fees', round(-fees.sum()), 'payouts', round(pays.sum()))
print('by year', curve.resample('YE').last().diff().fillna(curve.resample('YE').last().iloc[0]).round().astype(int).to_dict())
# --- Monte Carlo fan: bootstrap the 2013+ trading days (whole days, so non-signal days kept), 3 years, rerun accounts back-to-back
qq = q[q.index >= '2013']; days = 252*3; paths = []
rng = np.random.default_rng(7)
for k in range(400):
    idx = rng.integers(0, len(qq) - 20, days // 20 + 1)          # 20-day blocks keep volatility clusters
    samp = pd.concat([qq.iloc[i:i+20] for i in idx]).iloc[:days].copy()
    samp.index = pd.bdate_range('2027-01-01', periods=len(samp))
    c, _ = simulate(samp, STOP, RISK, start='2000', end='2100')
    paths.append(c.values)
P = np.array(paths); x = np.arange(P.shape[1]) / 252
pc = {p: np.percentile(P, p, axis=0) for p in (10, 25, 50, 75, 90)}
print('mean %.0f' % P[:,-1].mean()); print('MC after 3y: p10 %.0f p25 %.0f median %.0f p75 %.0f p90 %.0f  P(loss)=%.0f%%' % tuple([pc[p][-1] for p in (10,25,50,75,90)] + [100*np.mean(P[:,-1] < 0)]))

INK, INK2, GRID, BLUE, ORANGE, AQUA = '#0b0b0b', '#52514e', '#e4e3df', '#2a78d6', '#eb6834', '#1baf7a'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'axes.spines.top': False, 'axes.spines.right': False})
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 8.4), dpi=200, facecolor='#fcfcfb')
for a in (a1, a2): a.set_facecolor('#fcfcfb'); a.grid(axis='y', color=GRID, lw=0.8); a.axhline(0, color=INK2, lw=0.8)
a1.plot(curve.index, curve.values, color=BLUE, lw=2, label='Net cash (payouts after 90% split − £150 eval fees)')
a1.scatter(fees.index, curve[fees.index], s=36, color=ORANGE, edgecolor='#fcfcfb', lw=1.5, zorder=3, label=f'New eval bought (£150) ×{len(fees)}')
a1.scatter(pays.index, curve[pays.index], s=36, color=AQUA, edgecolor='#fcfcfb', lw=1.5, zorder=3, label=f'Payout received ×{len(pays)}')
a1.set_title('Historical run 2013–2026: one LucidFlex 50K account at a time', loc='left', color=INK, fontsize=12, fontweight='bold')
a1.set_ylabel('Cumulative £'); a1.legend(frameon=False, loc='upper left', fontsize=9)
a2.fill_between(x, pc[10], pc[90], color='#b7d3f6', lw=0, label='10th–90th percentile')
a2.fill_between(x, pc[25], pc[75], color='#6da7ec', lw=0, label='25th–75th percentile')
a2.plot(x, pc[50], color='#184f95', lw=2, label='Median')
a2.set_title('Next 3 years, 400 simulated histories (resampled 2013–2026 days)', loc='left', color=INK, fontsize=12, fontweight='bold')
a2.set_xlabel('Years'); a2.set_ylabel('Cumulative £'); a2.legend(frameon=False, loc='upper left', fontsize=9)
fig.text(0.01, 0.005, 'Signal: two RTH days in a row with IBS<0.3, or one day IBS<0.1 → buy 1 MNQ at next 09:30 NY open, stop 1% below, exit at close (flat EOD). '
         'Costs \\$4/contract + 1pt stop slippage. £1 = \\$1.30.', fontsize=7.5, color=INK2)
fig.tight_layout(rect=(0, 0.02, 1, 1)); fig.savefig('ibs_lucid_pnl.png', facecolor='#fcfcfb')
