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

### How the exit works (reminders)
The exit is always **at the next US close**. There is **no stop loss and no take profit**: I tested both on 2010–2026 data and
every stop/target combination made less money, and most had *bigger* drawdowns (a 1% stop turned +£159/yr into about £0; a 1% target
cut it to +£70/yr). The page shows your **exit plan** under "Open position" as soon as you log a buy.

On days you hold a position, the app reminds you three times:
1. **~18:00 UK, "Exit day"**: be at your screen 20:50–21:00 UK.
2. **~20:50 UK, SELL (or HOLD)**: close the position (or keep it if the signal fired again).
3. **~20:56 UK, LAST CALL**: only if you haven't clicked *I did it* yet. The page also beeps every 3 minutes until you confirm.

If the close passes and you haven't confirmed, a **red "overdue" message** tells you to close it straight away (the CFD trades almost
around the clock, so a late close is far better than leaving it open).

**Can't be there tomorrow?** Either skip the buy, or close it yourself earlier in the day. Closing at the US open (14:30 UK)
keeps less of the edge (about +£50/yr instead of +£180/yr over all trades), but that's fine for the odd day. Don't leave it open.

The times shift by an hour for a few weeks in March and Oct/Nov, and are earlier on US half-days. The app handles this.

### The three rules that matter
1. **Take every signal.** Skipping trades you "don't like" breaks the statistics.
2. **Always close at the next close** (unless the page says HOLD). Never hold a loser longer "to get back to even".
3. **No stops, no targets, no extra size.** The backtest only works if you follow it exactly.
4. **Never hold over a weekend.** The app never says BUY on a Friday, and if you hold a position on Friday it says SELL
   (never HOLD). Weekends cost three nights of overnight fees and carry gap risk, and Friday buys did worst in testing.

**When does it say BUY?** At the US close, if any of these is true for QQQ (and it isn't Friday):
- IBS below 0.30 today **and** yesterday (the close was near the day's low two days running), or
- IBS below 0.10 today, or
- RSI(2) below 10 (a short, sharp two-day drop).

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
about 26 trades a year (about one every two weeks), 65% winners, about **+£185 a year**. Worst drawdown about **−£235**;
worst single trade about −£170. One month is profitable only about 6 times in 10, and a year about 9 times in 10. **Don't judge it on a few weeks.**

---

## 6. If something goes wrong

| Problem | Fix |
|---|---|
| Page says "Can't reach the assistant" | The black window was closed. Double-click the start file again. |
| No alert at 20:50 | Was the computer asleep or the window closed? Open the page and click **Check signal now** (it acts for real only in the last 20 minutes before the close). |
| Wrong number of units | Check in Trading 212 that 1 unit = $1 per index point (US Tech 100 at ~27,700 means 1 unit ≈ $27,700). Otherwise ask your AI assistant to change `UNIT_VALUE`. |
| Moving to a new computer | Copy the whole folder, including `assistant_state.json` (your history). |

*Past results don't guarantee future ones. Only trade money you can afford to lose.*

---

## Running it on a Raspberry Pi (always on)

A Pi can run the assistant 24/7, so your laptop doesn't have to be awake at 20:50.

1. On the Pi (Raspberry Pi OS, connected to your home network), open a terminal or SSH in and run:

   ```bash
   git clone -b claude/sharp-franklin-o9bmsa --single-branch https://github.com/jimkaps/android_kernel_samsung_crespo.git ibs_project
   ```

   ```bash
   cd ibs_project && bash ibs_assistant/raspberry_pi/install_pi.sh
   ```

   It installs what's needed, sets the assistant to start automatically whenever the Pi boots, and prints the address,
   for example `http://192.168.1.50:8765`.
2. On your laptop or phone (same Wi-Fi), open that address and click **Enable alerts**.
   Bookmark it, or add it to your phone's home screen.

**Alerts:** a Pi has no screen, so the pop-up and sound come from the browser tab where the page is open.
Keep it open on your laptop around 20:50, or open the page on your phone when you expect a signal.

**Useful commands on the Pi:**

| Command | What it does |
|---|---|
| `sudo systemctl status ibs-assistant` | is it running? |
| `sudo systemctl restart ibs-assistant` | restart it |
| `journalctl -u ibs-assistant -n 50` | last 50 log lines |
| `cd ~/ibs_project && git pull && sudo systemctl restart ibs-assistant` | update to the latest version |

Your trade history is in `~/ibs_project/ibs_assistant/assistant_state.json`. Back it up now and then.
The page has no password, so anyone on your home Wi-Fi can open it. Don't forward the port on your router.
