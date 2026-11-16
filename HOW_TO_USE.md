# How to use the IBS Assistant

The app tells you when to buy and sell the **US Tech 100** CFD in Trading 212, keeps your trade log,
and checks whether your real results match the backtest. You place the trades yourself. It takes about a minute,
on roughly 3 days a month.

---

## 1. One-time setup (10 minutes)

1. **Install Python** from python.org (version 3.10 or newer).
   On Windows, tick **"Add Python to PATH"** on the first installer screen.
2. **Unzip** the `ibs_assistant` folder somewhere permanent, such as Documents.
3. **Start it:**
   - Windows: double-click `start_windows.bat`
   - Mac: right-click `start_mac.command` → Open (only the first time; after that, double-click)

   A black window opens (leave it open) and your browser opens the page **http://localhost:8765**.
4. On the page, click **Enable alerts** and allow notifications.
5. **Computer settings:** make sure the computer doesn't sleep in the evening.
   The daily check runs at about **20:50 UK time** (19:50 for a few weeks in March and Oct/Nov, earlier on US half-days).

**To start it again later**, for example after a restart, double-click the start file again. Your history is kept.

---

## 2. Before your first trade: check the order box in Trading 212

Open the US Tech 100 order screen and type the size the app gives you:

- **Best:** type the **number of units** (trial: **0.02**; later about **0.09–0.10**) and check that the
  position value shown is about **£500** (trial) or **£2,000** (later).
- If you can only type a **£ amount**, find out whether it means position value or **margin**. Type £500 and look at the units:
  about 0.02 means position value (fine). About 0.4–0.5 means it's margin, and you'd be 20× too big.
  In that case type **£25** (trial) or **£100** (later).

---

## 3. Every trading day

At ~20:50 UK, if there's something to do, you'll get a **pop-up and a sound**. Go to the page:

| The page shows | Do this in Trading 212 | Then on the page |
|---|---|---|
| 🟩 **BUY** | Open a **long (Buy)** US Tech 100 position of the units shown. **No stop loss, no take profit.** | Type the price you got → **I did it** |
| 🟥 **SELL** | **Close** the whole position. | Type the price you got → **I did it** |
| 🟦 **HOLD** | Nothing. Keep the position one more day. | Nothing |
| ⬜ **Nothing today** | Nothing. | Nothing |

- Couldn't trade? Click **I skipped it**. If you're holding a position, close it as soon as you can.
- **Overnight fees:** when Trading 212 shows an overnight (swap) charge for your position, type it into
  **Add overnight fee** and click the button.
- Do it **within ~10 minutes of the alert**, before the US close at 21:00 UK.

### The three rules that matter
1. **Take every signal.** Skipping trades you "don't like" breaks the statistics.
2. **Always close at the next close** (unless the page says HOLD). Never hold a loser longer "to get back to even".
3. **No stops, no targets, no extra size.** The backtest only works if you follow it exactly.

---

## 4. The trial (automatic)

- The first **30 days** use **£500 per trade**.
- After that, the app compares your real fills and fees with the official closing prices:
  - real cost **≤ 0.05% per trade** → it moves you to **£2,000 per trade** and tells you;
  - higher → it stays at £500 and tells you why (usually a wide spread, late orders or high fees).
- You can change the size yourself any time: **Change size**.

---

## 5. Reading the page

- **Your P&L:** what you've made after fees.
- **Model P&L:** what the same trades would have made at the exact closing prices with no costs.
- **Your real cost / trade:** the gap between the two. **This is the number to watch.** Green is fine (≤ 0.05%), red means costs are eating the edge.
- **Missed buys:** signals you skipped or didn't confirm.

**What to expect** (backtest 2010–2026, £2,000 per trade):
about 34 trades a year, 58% winners, about **+£180 a year**. Worst drawdown about **−£380**; worst single night about −£126.
One month is profitable only about 6 times in 10, and a year about 9 times in 10. **Don't judge it on a few weeks.**

---

## 6. If something goes wrong

| Problem | Fix |
|---|---|
| Page says "Can't reach the assistant" | The black window was closed. Double-click the start file again. |
| No alert at 20:50 | Was the computer asleep or the window closed? Open the page and click **Check signal now** (it acts for real only in the last 20 minutes before the close). |
| Wrong number of units | Check in Trading 212 that 1 unit = $1 per index point (US Tech 100 at ~27,700 means 1 unit ≈ $27,700). Otherwise ask your AI assistant to change `UNIT_VALUE`. |
| Moving to a new computer | Copy the whole folder, including `assistant_state.json` (your history). |

*Past results don't guarantee future ones. Only trade money you can afford to lose.*
