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

if __name__ == "__main__":
    test_cycle(); test_skip_and_missed(); test_unconfirmed_logged(); test_trial_upgrade(); test_check_now_is_preview_midday()
    test_exit_reminders(); test_schedule_order(); print("all tests passed")
