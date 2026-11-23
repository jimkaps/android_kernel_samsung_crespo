# Research findings, November 2026

These are plain-English results of the research done after the IBS assistant app was built. Short version:

- **No intraday pattern method beat chance on NQ.** That covers the Strat, Trader Kane's "Lab Model", ICT setups, fibs, and every combination of them with other filters.
- **The current IBS rule is still the best system found.** None of the new ideas improved it in both test periods.

All costs are included. Intraday results are per **MNQ** contract ($2 per point) with 1.5 points round-trip cost. Fills are conservative: if the stop and target trade in the same bar, the stop counts first.

"R" = profit or loss as a multiple of the amount risked. "t" = how unlikely a result is to be luck; about 2 or more is the usual bar for a single test.

## 1. The Strat on NQ (`intraday/strat_*.py`, `confluence.py`, `timewin.py`)

- **Setups tested:**
  - patterns 2-1-2, 3-1-2, 2-2 reversal and 3-2-2 reversal;
  - on 5m, 15m, 30m, 1h, 4h, daily, weekly and monthly bars;
  - exits at the next bar, 1R or 2R, with and without FTFC (full timeframe continuity);
  - Yahoo data plus the user's NQ 5-minute file covering 2020–2026.
- **Two backtest biases were found and fixed:**
  - bars that broke both triggers had been skipped instead of counted as losses;
  - ambiguous bars had all been assigned to longs.

  Both had created fake edges.
- **Result:** no edge on any timeframe, confluence filter or time-of-day window.
  - The least bad was 4h 2-1-2, 2R, FTFC: +0.15R / +0.11R, about +$830/yr per MNQ, drawdown −$2,070. Not trusted.
  - The "15m afternoon" idea lost money.

## 2. Trader Kane / "Lab Model" (`intraday/kane_bt.py`)

- **Source:** public summaries only. His own material wasn't reachable, so the rules are an approximation.
- **The approximation:**
  - A, "50% rebalance": trade the 50% or 61.8% pullback of a range (4h 06–10 NY, overnight, first hour, or previous day);
  - B, "sweep + iFVG": price sweeps the range, then breaks back through a price gap.
- **Result:** 84 variants, no reliable edge. The best was B on the 4h range, held to the close: +0.02R per trade, about +$2.5k/yr per MNQ, drawdown −$6.7k. Its profit came from a few volatile days.
- **Not tested:** the ES/SMT check, because there's no intraday ES data.

## 3. ICT setups with non-ICT confluence (`intraday/ict_conf.py`, `sb_robust.py`, `sb_base.py`)

- **Setups:** Silver Bullet (10–11am), 4h-range sweep + iFVG, overnight-range sweep + iFVG, midnight-open reclaim, and a raid on the previous day's high or low.
- **Filters:** 14 non-ICT filters (trend, IBS, RSI2, volatility, VIX, gap, daily SMT, NQ vs ES strength, long or short), alone and in pairs. 1,293 combinations in total.
- **Result:**
  - 52 combinations had t above 2 in 2020–23, about what chance alone produces. None had t above 2 in 2024–26.
  - The only one that held in both periods was Silver Bullet + 20-day trend, 2R: +0.21R then +0.16R.
  - But random entries on the same days, with the same direction and stop, also made +0.14R (range +0.05 to +0.23). So the ICT entry adds nothing; the profit comes from trading the morning with the trend.

## 4. Everything combined (`intraday/mega.py`, `results/mega_results_top2000.csv`)

- **Scale:** 187 methods × 21 filters (up to 3 at a time), giving 70,586 testable strategies.
- **Method:** search on 2020–24, then a final test on 2025–26 that the search never saw.
- **Luck benchmark:** the identical search run on scrambled outcomes, which have no edge by construction.
- **Result:**
  - The best real t-stat was 4.62. Scrambled runs scored 3.85–5.22, so the best real result looks like luck.
  - The top 10 from 2020–24 averaged +0.33R per trade, then −0.03R in 2025–26. The top 50 averaged about 0.
  - The few that stayed positive mostly contained "IBS agrees + longs", which is the existing IBS edge showing through.

## 5. Fibs as confluence (`intraday/fib.py`, `results/fib_results.csv.gz`)

- **Filters:**
  - entries within 3% of the range from the 38.2, 50, 61.8, 70.5 or 78.6% level of the previous day's or previous week's range;
  - the ICT optimal trade entry zone (0.62–0.79);
  - premium/discount.

  Each was tried alone and with one other filter: 5,811 strategies.
- **Result:**
  - Fewer strong results than the luck runs produced (3 with t above 3, against about 12 by chance).
  - Adding a fib filter changed results by about 0R per trade.
  - The top 50 went from +0.29R to −0.10R in 2025–26.

## 6. Trying to improve the IBS rule (`ibs_v2/improve2.py`, `port.py`, `results.txt`)

QQQ, £2,000 per trade, Trading 212 CFD costs. Train 2001–14, test 2015–26. Score = £/yr per £1,000 of worst drawdown.

| Idea | Score train | Score test | Verdict |
|---|---|---|---|
| **Current rule** | **815** | **908** | **keep** |
| Size by volatility | 806 | 689 | worse |
| 1.5× when very oversold | 750 | 1,039 | mixed |
| 1.5× below the 200-day average | 761 | 1,156 | mixed |
| Exit at the next open | 199 | 598 | much worse |
| Allow Friday entries | 472 | 846 | worse (keeps the no-weekend rule) |
| Shorts on overbought days | 67 | 0 | no edge |
| + lower Bollinger band entries | 819 | 939 | about the same |
| + turn of the month | 931 | 969 | the turn-of-month trade alone lost money in 2015–26 |
| 1.5× when SPY and IWM also signal | 785 | 1,334 | mixed |

- **Other markets, same rule, 2015–26:**
  - US markets work: SPY +£183/yr, IWM +£150/yr, DIA +£111/yr.
  - Europe, UK and Hong Kong lose money: DAX −£53/yr, FTSE −£37/yr, Euro Stoxx −£93/yr, Hang Seng −£34/yr.
  - Nikkei and gold are weak.
- **QQQ + IWM:** roughly double the trades and profit, but drawdowns grow nearly in proportion. It's a risk choice, not an improvement.
- **Conclusion:** no renamed "better" system. Keep the current rule, the £500 trial and the £2,000 plan.

## Data and how to rerun

- **Data not committed:**
  - The user's NQ 5-minute file (`NQ_5m_2020.csv`, from HistData) is their own download.
  - The Yahoo CSVs can be re-downloaded with `ibs_v2/fetch.py`, plus `QQQ.csv`, `SPY.csv`, `VIX.csv`, `NQ_F.csv` and `ES_F.csv` from yfinance.
- **Folder layout:** the scripts expect `upload/NQ_5m_2020.csv`, `work/*.csv` (daily Yahoo files), `nqy/` and `kane/` (outputs), and `idx/` (other indices), all relative to where they're run.
