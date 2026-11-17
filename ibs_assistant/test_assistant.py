"""Offline tests with fake market data: buy -> hold -> sell cycle, skip, fees, report, trial upgrade."""
import importlib, os, sys, tempfile
os.environ.update(BOT_DIR=tempfile.mkdtemp(), TRIAL_DAYS="0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
a = importlib.import_module("ibs_assistant")
a.desktop_notify = lambda *x: None
LEVEL = {"v": 25000.0}
a.market_levels = lambda: (LEVEL["v"], 1.25)
closes = {"2026-01-05": 25000.0, "2026-01-06": 25100.0, "2026-01-07": 25300.0, "2026-01-08": 25000.0, "2026-01-09": 25050.0}
a.official_close = lambda d: closes.get(d)
def day(date, sig, s):
    a.signal_now = lambda: dict(date=date, ibs_today=0.1, ibs_yesterday=0.2, signal=sig)
    LEVEL["v"] = closes[date]; a.daily_job(s)
def test_cycle():
    s = a.new_state()
    day("2026-01-05", True, s); assert s["alert"]["action"] == "BUY" and s["pending"]["units"] == 0.03   # 500*1.25/25000
    a.act_filled(s, 25005.0); assert s["position"]["fill"] == 25005.0
    day("2026-01-06", True, s); assert s["alert"]["action"] == "HOLD" and s["pending"] is None
    day("2026-01-07", False, s); assert s["alert"]["action"] == "SELL"
    a.act_fee(s, 0.40); a.act_filled(s, 25295.0)
    t = s["trades"][0]; assert abs(t["pnl_gbp"] - ((25295 - 25005) * 0.03 / 1.25 - 0.40)) < 0.01
    a.fill_closes(s); r = a.report(s)
    assert r["n"] == 1 and r["model"] == round(300 * 0.03 / 1.25, 2)              # 7.20
    assert abs(r["cost_per"] - (7.20 - t["pnl_gbp"])) < 0.01 and abs(r["slip"] - 10 * 0.024) < 0.01   # entry 5 above close + exit 5 below close = 10 pts
    assert r["cost_per"] > 0
    # trial: needs >=3 trades
    a.trial_check(s); assert s["phase"] == "trial"
    return s
def test_skip_and_missed():
    s = a.new_state(); day("2026-01-08", True, s); a.act_skip(s)
    assert s["pending"] is None and a.report(s)["missed"] == 1
    day("2026-01-09", True, s); day_after = s["pending"]["action"]; assert day_after == "BUY"
def test_unconfirmed_logged():
    s = a.new_state(); day("2026-01-08", True, s); day("2026-01-09", False, s)   # never confirmed the buy
    assert a.report(s)["missed"] == 1 and s["position"] is None and s["alert"]["action"] == "NONE"
def test_trial_upgrade():
    s = a.new_state()
    for i, (d1, d2) in enumerate([("2026-01-05","2026-01-06"),("2026-01-07","2026-01-08"),("2026-01-08","2026-01-09")]):
        s["last_run"] = None; day(d1, True, s); a.act_filled(s, closes[d1]); s["last_run"] = None; day(d2, False, s); a.act_filled(s, closes[d2])
    a.trial_check(s); assert s["phase"] == "full" and s["exposure"] == 2000, s["events"][:2]
def test_check_now_is_preview_midday():
    s = a.new_state(); a.minutes_to_close = lambda now=None: 300
    a.signal_now = lambda: dict(date="2026-01-05", ibs_today=0.05, ibs_yesterday=0.2, signal=True)
    a.daily_job(s, force=True); assert s["pending"] is None and s["alert"] is None and s["events"][0]["kind"] == "preview"
def test_exit_reminders():
    import pandas as pd
    from datetime import datetime, timezone
    s = a.new_state(); day("2026-01-05", True, s)
    assert "Exit plan" in s["alert"]["text"] and "Tue 06 Jan" in s["alert"]["text"] and "20:50" in s["alert"]["text"]
    a.last_call_job(s); assert s["alert"]["last_call"] and s["alert"]["id"].endswith("#last")      # unconfirmed -> last call
    assert a.overdue(s, datetime(2026, 1, 5, 20, 0, tzinfo=timezone.utc)) is None                   # before the 21:00 UTC close
    assert "skipped" in a.overdue(s, datetime(2026, 1, 5, 21, 5, tzinfo=timezone.utc))              # missed buy: don't buy late
    a.act_filled(s, 25000.0); assert "Tue 06 Jan" in s["position"]["exit_plan"]
    a.headsup_job(s, pd.Timestamp("2026-01-06")); assert s["reminder"] and "18:00" not in s["reminder"]["text"] and "20:50" in s["reminder"]["text"]
    day("2026-01-06", False, s); assert s["alert"]["action"] == "SELL" and s["reminder"] is None
    assert "close it now" in a.overdue(s, datetime(2026, 1, 6, 22, 0, tzinfo=timezone.utc))         # missed sell
    a.act_filled(s, 25100.0); assert a.overdue(s) is None
    s2 = a.new_state(); a.headsup_job(s2, pd.Timestamp("2026-01-06")); assert s2["reminder"] is None  # nothing held: no reminder
def test_schedule_order():
    from datetime import datetime, timezone
    t0 = datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc); kinds = []
    for _ in range(4):
        f, k, sess = a.next_job(t0); kinds.append((f.strftime("%a %H:%M"), k)); t0 = f
    assert kinds == [("Tue 18:00", "headsup"), ("Tue 20:50", "decide"), ("Tue 20:56", "lastcall"), ("Wed 18:00", "headsup")], kinds
    assert a.next_fire(datetime(2026, 1, 6, 20, 51, tzinfo=timezone.utc)).strftime("%a %H:%M") == "Wed 20:50"

def fake_market(today, closes_hist, day_hi, day_lo, day_last, y_hi=None, y_lo=None):
    import pandas as pd
    idx = pd.bdate_range(end=pd.Timestamp(today) - pd.Timedelta(days=1), periods=len(closes_hist))
    daily = pd.DataFrame({"Close": closes_hist, "High": [c + 1 for c in closes_hist], "Low": [c - 1 for c in closes_hist]}, index=idx)
    if y_hi is not None: daily.iloc[-1, 1:] = [y_hi, y_lo]
    t = pd.date_range(f"{today} 14:30", periods=3, freq="h", tz="UTC")
    intr = pd.DataFrame({"High": [day_hi] * 3, "Low": [day_lo] * 3, "Close": [day_lo, day_lo, day_last]}, index=t)
    a._dl = lambda tk, **kw: intr if kw.get("interval") == "1m" else daily
def test_rsi_entry_and_friday():
    real = a.signal_now
    try:
        a.signal_now = SIGNAL_NOW
        hist = [400 + i for i in range(60)] + [440, 430]           # two sharp down days -> RSI(2) very low
        fake_market("2026-01-08", hist, day_hi=429, day_lo=420, day_last=428)   # Thursday, close near the high: IBS ~0.9
        g = a.signal_now(); assert g["ibs_today"] > 0.8 and g["rsi2"] < 10 and g["signal"] and not g["friday"], g
        fake_market("2026-01-09", hist, day_hi=429, day_lo=420, day_last=428)   # same on a Friday: blocked
        g = a.signal_now(); assert g["raw"] and g["friday"] and not g["signal"], g
        up = [400 + i for i in range(62)]
        fake_market("2026-01-08", up, day_hi=470, day_lo=460, day_last=469)     # steady rise: no signal
        g = a.signal_now(); assert g["rsi2"] > 50 and not g["raw"], g
        fake_market("2026-01-08", up, day_hi=470, day_lo=460, day_last=460.5, y_hi=470, y_lo=455)  # IBS rule still works
        g = a.signal_now(); assert g["ibs_today"] < 0.1 and g["signal"], g
    finally:
        a.signal_now = real
    s = a.new_state()
    day("2026-01-08", True, s); a.act_filled(s, 25000.0)                       # Thursday buy
    assert "Fri 09 Jan" in s["position"]["exit_plan"]
    a.signal_now = lambda: dict(date="2026-01-09", ibs_today=0.05, ibs_yesterday=0.2, rsi2=3.0, friday=True, raw=True, signal=False)
    LEVEL["v"] = closes["2026-01-09"]; a.daily_job(s)
    assert s["alert"]["action"] == "SELL" and "Friday" in s["alert"]["text"], s["alert"]   # held on Friday -> sell, no HOLD
    s2 = a.new_state(); a.daily_job(s2)
    assert s2["alert"]["action"] == "NONE" and "Friday" in s2["alert"]["text"] and s2["pending"] is None
SIGNAL_NOW = a.signal_now

if __name__ == "__main__":
    test_cycle(); test_skip_and_missed(); test_unconfirmed_logged(); test_trial_upgrade(); test_check_now_is_preview_midday()
    test_exit_reminders(); test_schedule_order(); test_rsi_entry_and_friday(); print("all tests passed")
