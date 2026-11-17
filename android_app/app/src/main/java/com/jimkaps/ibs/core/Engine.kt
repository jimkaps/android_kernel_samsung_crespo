package com.jimkaps.ibs.core

import org.json.JSONArray
import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs

/** Channels the engine notifies on; the app maps them to Android notification channels. */
enum class Channel { SIGNAL, REMINDER, INFO }

data class Job(val time: Instant, val kind: String, val session: LocalDate)

/**
 * The trading assistant's logic, ported from ibs_assistant.py. State is a JSONObject with the
 * same layout as the desktop app's assistant_state.json.
 */
class Engine(
    private val market: Market,
    private val notify: (title: String, text: String, channel: Channel) -> Unit,
    private val clock: () -> Instant = { Instant.now() },
    private val zone: ZoneId = ZoneId.systemDefault(),
) {
    companion object {
        const val UNIT_VALUE = 1.0            // USD per index point for 1 unit of the US 100 CFD
        const val TRIAL_EXPOSURE = 500.0
        const val FULL_EXPOSURE = 2000.0
        const val TRIAL_DAYS = 30L
        const val MINUTES_BEFORE_CLOSE = 10L
        const val MAX_COST_PCT = 0.05
        const val HEADSUP_HOURS = 3L
        const val LAST_CALL_MINUTES = 4L
        const val OVERDUE_MINUTES = 5L
        val UK: ZoneId = ZoneId.of("Europe/London")
        private val HHMM = DateTimeFormatter.ofPattern("HH:mm")
        private val DAY = DateTimeFormatter.ofPattern("EEE dd MMM", Locale.UK)
        private val STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
    }

    // ---------------- state ----------------
    fun newState(): JSONObject = JSONObject()
        .put("started", clock().atZone(zone).toLocalDate().toString()).put("phase", "trial")
        .put("exposure", TRIAL_EXPOSURE).put("position", JSONObject.NULL).put("pending", JSONObject.NULL)
        .put("trades", JSONArray()).put("events", JSONArray()).put("alert", JSONObject.NULL)
        .put("last_run", JSONObject.NULL).put("trial_checked", false).put("next_check", JSONObject.NULL)
        .put("reminder", JSONObject.NULL)

    fun event(s: JSONObject, kind: String, text: String, missed: String? = null) {
        val e = JSONObject().put("time", clock().atZone(zone).format(STAMP)).put("kind", kind).put("text", text)
        if (missed != null) e.put("missed", missed)
        val old = s.getJSONArray("events")
        val out = JSONArray().put(e)
        for (i in 0 until minOf(old.length(), 299)) out.put(old.get(i))
        s.put("events", out)
    }

    private fun JSONObject.obj(k: String): JSONObject? = optJSONObject(k)
    private fun money(v: Double) = String.format(Locale.UK, "%,.0f", v)
    private fun pts(v: Double) = String.format(Locale.UK, "%,.1f", v)

    fun ukTime(t: Instant): String = t.atZone(UK).format(HHMM)

    fun unitsFor(exposure: Double, level: Double, gbpusd: Double) =
        maxOf(0.01, Rules.round(exposure * gbpusd / (level * UNIT_VALUE), 2))

    // ---------------- the daily decision ----------------
    fun nextCloseAfter(date: String): Instant = Nyse.close(Nyse.nextSession(LocalDate.parse(date)))

    fun exitPlan(date: String): String {
        val close = nextCloseAfter(date)
        val decide = close.minus(Duration.ofMinutes(MINUTES_BEFORE_CLOSE))
        val day = close.atZone(UK).format(DAY)
        return "Exit plan: no stop loss, no take profit. Close it on $day between ${ukTime(decide)} and ${ukTime(close)} UK " +
            "(the app will remind you at ${ukTime(close.minus(Duration.ofHours(HEADSUP_HOURS)))} and alert you at ${ukTime(decide)})."
    }

    fun minutesToClose(now: Instant = clock()): Double? {
        val d = Nyse.nyDate(now)
        if (!Nyse.isSession(d)) return null
        return Duration.between(now, Nyse.close(d)).seconds / 60.0
    }

    fun dailyJob(s: JSONObject, force: Boolean = false) {
        val sig = market.signal()
        if (force) {
            val m = minutesToClose()
            if (m == null || m <= 0 || m > 20) {
                val would = when {
                    sig.signal -> "BUY-type signal so far"
                    sig.raw -> "buy signal so far, but it's Friday (no weekend holds)"
                    else -> "no signal so far"
                }
                event(s, "preview", "Preview only (${sig.date}): IBS today ${sig.ibsToday}, yesterday ${sig.ibsYesterday}, " +
                    "RSI(2) ${sig.rsi2}: $would. Real decisions are made in the last 10–20 min before the US close.")
                return
            }
        }
        if (s.optString("last_run") == sig.date) return
        s.put("last_run", sig.date)
        s.obj("pending")?.let { p ->
            if (p.getString("action") == "SELL")
                event(s, "warn", "The SELL from ${p.getString("date")} was never confirmed. If you still hold the position, " +
                    "today's alert tells you what to do; if you did close it, enter the price below.", missed = "SELL")
            else event(s, "warn", "Previous ${p.getString("action")} was never confirmed. Logged as missed.", missed = p.getString("action"))
            s.put("pending", JSONObject.NULL)
        }
        val (level, gbpusd) = market.levels()
        s.put("gbpusd", gbpusd)
        val info = "IBS today ${sig.ibsToday}, yesterday ${sig.ibsYesterday}, RSI(2) ${sig.rsi2}"
        val pos = s.obj("position")
        val closeToday = Nyse.close(LocalDate.parse(sig.date))
        val action: String; val text: String
        when {
            pos != null && sig.signal -> {
                pos.put("exit_plan", exitPlan(sig.date))
                action = "HOLD"; text = "Signal fired again. Keep your ${pos.getDouble("units")} units open. " + pos.getString("exit_plan")
            }
            pos != null -> {
                s.put("pending", JSONObject().put("action", "SELL").put("date", sig.date).put("units", pos.getDouble("units")).put("model_px", level))
                action = "SELL"
                text = (if (sig.friday) "It's Friday: never hold over the weekend. " else "") +
                    "Close your US 100 position (${pos.getDouble("units")} units) now, before ${ukTime(closeToday)} UK. Index ≈ ${pts(level)}."
            }
            sig.signal -> {
                val units = unitsFor(s.getDouble("exposure"), level, gbpusd)
                s.put("pending", JSONObject().put("action", "BUY").put("date", sig.date).put("units", units).put("model_px", level))
                action = "BUY"
                text = "Open a long US 100 position of $units units now (≈ £${money(s.getDouble("exposure"))}, index ≈ ${pts(level)}). " +
                    "No stop, no target. " + exitPlan(sig.date)
            }
            sig.raw && sig.friday -> {
                action = "NONE"; text = "Buy signal, but it's Friday: the rule never buys on a Friday (no weekend holds). Nothing to do today."
            }
            else -> { action = "NONE"; text = "Nothing to do today." }
        }
        s.put("alert", JSONObject().put("action", action).put("text", text).put("date", sig.date).put("info", info)
            .put("id", "${sig.date}-$action").put("deadline", closeToday.toString()))
        s.put("reminder", JSONObject.NULL)
        event(s, action.lowercase(), "${sig.date}: $action. $text ($info)")
        if (action != "NONE") notify("IBS: $action", text, Channel.SIGNAL)
    }

    fun headsupJob(s: JSONObject, sess: LocalDate) {
        val pos = s.obj("position") ?: return
        val close = Nyse.close(sess); val decide = close.minus(Duration.ofMinutes(MINUTES_BEFORE_CLOSE))
        val text = "Exit day: you hold ${pos.getDouble("units")} US 100 units. At ${ukTime(decide)} UK the app will tell you to close them " +
            "(or to hold if the signal fires again). Be at your screen ${ukTime(decide)}–${ukTime(close)} UK. " +
            "Can't be there? Close it yourself any time before then; closing a few hours early is fine, leaving it open is not."
        s.put("reminder", JSONObject().put("id", "$sess-HEADSUP").put("text", text))
        event(s, "reminder", text); notify("IBS: exit day", text, Channel.REMINDER)
    }

    fun lastCallJob(s: JSONObject) {
        val p = s.obj("pending") ?: return
        val a = s.obj("alert") ?: return
        if (a.optBoolean("done")) return
        a.put("last_call", true).put("id", a.getString("id").substringBefore("#") + "#last")
        val text = "LAST CALL: ${p.getString("action")} ${p.getDouble("units")} units is still not confirmed. The US close is in $LAST_CALL_MINUTES minutes."
        event(s, "warn", text); notify("IBS: LAST CALL ${p.getString("action")}", text, Channel.SIGNAL)
    }

    fun overdue(s: JSONObject, now: Instant = clock()): String? {
        val p = s.obj("pending") ?: return null
        val a = s.obj("alert") ?: return null
        val deadline = a.optString("deadline").ifEmpty { return null }
        if (now < Instant.parse(deadline)) return null
        return if (p.getString("action") == "SELL")
            "You didn't confirm the SELL before the close. If you still hold the position, close it now: the US 100 CFD " +
                "trades almost around the clock, and a late close is much better than leaving it open. Then enter your price. " +
                "If you did close it, just enter the price."
        else "The BUY wasn't confirmed before the close. Don't buy late: tap I skipped it (or enter the price if you did buy)."
    }

    fun overdueJob(s: JSONObject) {
        val o = overdue(s) ?: return
        if (s.getJSONObject("pending").getString("action") == "SELL") notify("IBS: SELL not confirmed", o, Channel.SIGNAL)
    }

    /** Runs a scheduled job; `late` guards against firing stale reminders after the phone was off. */
    fun runJob(s: JSONObject, job: Job) {
        val lateMin = Duration.between(job.time, clock()).seconds / 60.0
        when (job.kind) {
            "decide" -> { dailyJob(s); runCatching { trialCheck(s) } }
            "headsup" -> if (lateMin < 60) headsupJob(s, job.session)
            "lastcall" -> if (lateMin < LAST_CALL_MINUTES) lastCallJob(s)
            "overdue" -> if (lateMin < 30) overdueJob(s)
        }
    }

    // ---------------- user actions ----------------
    fun filled(s: JSONObject, price: Double) {
        val p = s.obj("pending") ?: throw IllegalStateException("Nothing is waiting for a fill.")
        if (p.getString("action") == "BUY") {
            s.put("position", JSONObject().put("entry_date", p.getString("date")).put("units", p.getDouble("units")).put("fill", price)
                .put("model_px", p.getDouble("model_px")).put("fees", 0.0).put("exposure", s.getDouble("exposure"))
                .put("fx", s.optDouble("gbpusd", 1.30)).put("exit_plan", exitPlan(p.getString("date"))))
            event(s, "fill", "Bought ${p.getDouble("units")} units at ${pts(price)}")
        } else {
            val pos = s.getJSONObject("position")
            val fx = pos.optDouble("fx", s.optDouble("gbpusd", 1.30))
            val pnl = (price - pos.getDouble("fill")) * pos.getDouble("units") * UNIT_VALUE / fx - pos.getDouble("fees")
            val t = JSONObject(pos.toString()).put("exit_date", p.getString("date")).put("exit_fill", price)
                .put("exit_model_px", p.getDouble("model_px")).put("pnl_gbp", Rules.round(pnl, 2))
            s.getJSONArray("trades").put(t)
            s.put("position", JSONObject.NULL)
            event(s, "fill", "Sold at ${pts(price)}. Trade P&L ≈ £${String.format(Locale.UK, "%+.2f", pnl)}")
        }
        s.put("pending", JSONObject.NULL)
        s.obj("alert")?.put("done", true)
    }

    fun skip(s: JSONObject) {
        val p = s.obj("pending") ?: throw IllegalStateException("Nothing to skip.")
        event(s, "warn", "Skipped ${p.getString("action")} on ${p.getString("date")}", missed = p.getString("action"))
        s.put("pending", JSONObject.NULL)
        s.obj("alert")?.put("done", true)
    }

    fun fee(s: JSONObject, amount: Double) {
        val a = abs(amount)
        val pos = s.obj("position"); val trades = s.getJSONArray("trades")
        val where = when {
            pos != null -> { pos.put("fees", pos.getDouble("fees") + a); "open position" }
            trades.length() > 0 -> {
                val t = trades.getJSONObject(trades.length() - 1)
                t.put("fees", t.getDouble("fees") + a).put("pnl_gbp", Rules.round(t.getDouble("pnl_gbp") - a, 2)); "last trade"
            }
            else -> throw IllegalStateException("No trade to attach the fee to.")
        }
        event(s, "fee", "£${String.format(Locale.UK, "%.2f", a)} fee added to $where")
    }

    fun setExposure(s: JSONObject, amount: Double) {
        require(amount >= 20) { "Size must be at least £20." }
        s.put("exposure", amount); event(s, "info", "Exposure set to £${money(amount)}")
    }

    // ---------------- reporting & trial ----------------
    fun fillCloses(s: JSONObject) {
        val tr = s.getJSONArray("trades")
        for (i in 0 until tr.length()) {
            val t = tr.getJSONObject(i)
            runCatching {
                if (!t.has("close_entry") || t.isNull("close_entry")) market.officialClose(t.getString("entry_date"))?.let { t.put("close_entry", it) }
                if (!t.has("close_exit") || t.isNull("close_exit")) market.officialClose(t.getString("exit_date"))?.let { t.put("close_exit", it) }
            }
        }
    }

    fun report(s: JSONObject): JSONObject {
        val tr = s.getJSONArray("trades"); val ev = s.getJSONArray("events")
        val all = (0 until tr.length()).map { tr.getJSONObject(it) }
        val missed = (0 until ev.length()).count { ev.getJSONObject(it).optString("missed") == "BUY" }
        val out = JSONObject().put("n", all.size).put("wins", all.count { it.getDouble("pnl_gbp") > 0 })
            .put("pnl", Rules.round(all.sumOf { it.getDouble("pnl_gbp") }, 2)).put("fees", Rules.round(all.sumOf { it.getDouble("fees") }, 2))
            .put("missed", missed).put("model", JSONObject.NULL).put("cost_per", JSONObject.NULL)
            .put("cost_pct", JSONObject.NULL).put("slip", JSONObject.NULL)
        val full = all.filter { it.has("close_entry") && !it.isNull("close_entry") && it.has("close_exit") && !it.isNull("close_exit") }
        if (full.isNotEmpty()) {
            fun gbpPt(t: JSONObject) = t.getDouble("units") * UNIT_VALUE / t.optDouble("fx", 1.30)
            val model = full.sumOf { (it.getDouble("close_exit") - it.getDouble("close_entry")) * gbpPt(it) }
            val real = full.sumOf { it.getDouble("pnl_gbp") }
            val slip = full.sumOf { ((it.getDouble("fill") - it.getDouble("close_entry")) - (it.getDouble("exit_fill") - it.getDouble("close_exit"))) * gbpPt(it) } / full.size
            val size = full.sumOf { it.getDouble("close_entry") * gbpPt(it) } / full.size
            val cost = (model - real) / full.size
            out.put("model", Rules.round(model, 2)).put("cost_per", Rules.round(cost, 2))
                .put("cost_pct", Rules.round(cost / size * 100, 3)).put("slip", Rules.round(slip, 2))
        }
        return out
    }

    fun trialCheck(s: JSONObject) {
        if (s.getString("phase") != "trial" || s.optBoolean("trial_checked")) return
        val days = Duration.between(LocalDate.parse(s.getString("started")).atStartOfDay(zone).toInstant(), clock()).toDays()
        if (days < TRIAL_DAYS) return
        fillCloses(s); val r = report(s)
        if (r.isNull("cost_pct") || r.getInt("n") < 3) {
            event(s, "info", "Trial: fewer than 3 complete trades. Keeping the small size, will check again."); return
        }
        s.put("trial_checked", true)
        val pct = r.getDouble("cost_pct")
        val msg = if (pct <= MAX_COST_PCT) {
            s.put("phase", "full").put("exposure", FULL_EXPOSURE)
            "Trial passed: your real cost is $pct% per trade, in line with the backtest. Moving to £${money(FULL_EXPOSURE)} per trade from the next signal."
        } else "Trial: your real cost is $pct% per trade, above the $MAX_COST_PCT% the strategy can afford. " +
            "Staying small. Check the spread/overnight fee and place orders closer to the close."
        event(s, "trial", msg); notify("IBS trial result", msg, Channel.INFO)
    }

    // ---------------- schedule ----------------
    fun nextJob(after: Instant, kinds: Set<String> = setOf("headsup", "decide", "lastcall", "overdue")): Job {
        var sess = Nyse.sessionOnOrAfter(Nyse.nyDate(after))
        repeat(4) {
            val close = Nyse.close(sess)
            val times = mapOf(
                "headsup" to close.minus(Duration.ofHours(HEADSUP_HOURS)),
                "decide" to close.minus(Duration.ofMinutes(MINUTES_BEFORE_CLOSE)),
                "lastcall" to close.minus(Duration.ofMinutes(LAST_CALL_MINUTES)),
                "overdue" to close.plus(Duration.ofMinutes(OVERDUE_MINUTES)),
            )
            times.filter { it.key in kinds && it.value > after }.minByOrNull { it.value }?.let { return Job(it.value, it.key, sess) }
            sess = Nyse.nextSession(sess)
        }
        error("no session found")
    }

    fun nextDecision(after: Instant) = nextJob(after, setOf("decide")).time
}
