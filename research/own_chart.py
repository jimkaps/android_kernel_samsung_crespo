import numpy as np, pandas as pd, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import own
t, eq, yr = own.out['DOUBLE<0.35, exit next close']
dd = eq - eq.cummax()
print('chosen: $/yr', round(eq.iloc[-1]/((eq.index[-1]-eq.index[0]).days/365.25)), 'worstDD', round(dd.min()), 'from', eq[:dd.idxmin()].idxmax().date(), 'to', dd.idxmin().date(),
      '| since 2016 DD', round((eq[eq.index>='2016']-eq[eq.index>='2016'].cummax()).min()), '| losing years', int((yr<0).sum()), 'of', len(yr))
print('by year', yr.round().astype(int).rename(lambda x: x.year).to_dict())
r = t.r * own.NOT; print('5 worst trades', r.nsmallest(5).round().tolist(), 'worst losing streak $', round((pd.Series(r.values).cumsum() - pd.Series(r.values).cumsum().cummax()).min()))
INK, INK2, GRID, BLUE, RED = '#0b0b0b', '#52514e', '#e4e3df', '#2a78d6', '#e34948'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.edgecolor':GRID,'axes.labelcolor':INK2,'xtick.color':INK2,'ytick.color':INK2,'axes.spines.top':False,'axes.spines.right':False})
fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), dpi=200, facecolor='#fcfcfb', sharex=True, gridspec_kw=dict(height_ratios=[2.2, 1]))
for a in (a1, a2): a.set_facecolor('#fcfcfb'); a.grid(axis='y', color=GRID, lw=.8); a.axhline(0, color=INK2, lw=.8)
a1.plot(eq.index, eq.values, color=BLUE, lw=2)
a1.set_title('Double IBS (2 days IBS<0.35) on NQ, overnight: cumulative P&L per 1 MNQ at today\'s prices', loc='left', color=INK, fontsize=11.5, fontweight='bold')
a1.set_ylabel('Cumulative $ (1 MNQ)')
a2.fill_between(dd.index, dd.values, 0, color=RED, alpha=.35, lw=0); a2.plot(dd.index, dd.values, color=RED, lw=1)
a2.set_ylabel('Drawdown $'); a2.set_title('Drawdown from previous high', loc='left', color=INK, fontsize=11, fontweight='bold')
i = dd.idxmin(); a2.annotate(f'worst {dd.min():,.0f}', (i, dd.min()), xytext=(10, 4), textcoords='offset points', color=INK2, fontsize=9)
fig.text(.01, .005, 'Buy 1 MNQ at the close after two days in a row with IBS<0.35, sell at the next close. $4 round-trip costs. '
         'All years scaled to NQ = 25,000 (\\$50k notional).', fontsize=7.5, color=INK2)
fig.tight_layout(rect=(0, .02, 1, 1)); fig.savefig('own_account_pnl.png', facecolor='#fcfcfb')
