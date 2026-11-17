package com.jimkaps.ibs.core

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

class FakeMarket : Market {
    var sig = Signal("2026-01-05", 0.1, 0.2, 50.0, false, true, true)
    var level = 25000.0
    val closes = mutableMapOf("2026-01-05" to 25000.0, "2026-01-06" to 25100.0, "2026-01-07" to 25300.0, "2026-01-08" to 25000.0, "2026-01-09" to 25050.0)
    override fun signal() = sig
    override fun levels() = level to 1.25
    override fun officialClose(date: String) = closes[date]
}

class CoreTest {
    private fun res(name: String) = javaClass.classLoader!!.getResource(name)!!.readText()
    private val m = FakeMarket()
    private val notes = mutableListOf<String>()
    private var now = Instant.parse("2026-01-05T20:50:00Z")
    private val e = Engine(m, { t, _, _ -> notes += t }, { now }, ZoneId.of("Europe/London"))

    private fun day(date: String, signal: Boolean, s: JSONObject) {
        m.sig = Signal(date, 0.1, 0.2, 50.0, LocalDate.parse(date).dayOfWeek.value == 5, signal, signal)
        m.level = m.closes[date]!!
        now = Nyse.close(LocalDate.parse(date)).minusSeconds(600)
        e.dailyJob(s)
    }

    @Test fun calendarMatchesExchangeCalendars() {
        val expected = res("nyse_closes.txt").lines().filter { it.isNotBlank() }.associate {
            val (d, c) = it.split(" "); LocalDate.parse(d) to Instant.parse(c.replace("+00:00", "Z"))
        }
        var d = LocalDate.of(2019, 1, 2)
        while (d <= LocalDate.of(2030, 12, 31)) {
            val exp = expected[d]
            assertEquals("session? $d", exp != null, Nyse.isSession(d))
            if (exp != null) assertEquals("close $d", exp, Nyse.close(d))
            d = d.plusDays(1)
        }
    }

    @Test fun yahooSignalMatchesPython() {
        val exp = JSONObject(res("expected_signal.json"))
        val ym = YahooMarket { url -> if ("QQQ" in url) res("yahoo_qqq_6mo.json") else res("yahoo_ndx_3mo.json") }
        val g = ym.signal()
        assertEquals(exp.getString("today"), g.date)
        assertEquals(exp.getDouble("ibs_today"), g.ibsToday, 0.0006)
        assertEquals(exp.getDouble("ibs_yesterday"), g.ibsYesterday, 0.0006)
        assertEquals(exp.getDouble("rsi2"), g.rsi2, 0.06)
        assertEquals(27740.7890625, ym.officialClose("2026-11-10")!!, 0.01)
    }

    @Test fun rsiAndFridayRules() {
        val start = LocalDate.of(2025, 10, 1)
        val hist = (0 until 60).map { Bar(start.plusDays(it.toLong()), 401.0 + it, 399.0 + it, 400.0 + it) } +
            Bar(start.plusDays(60), 441.0, 439.0, 440.0) + Bar(start.plusDays(61), 431.0, 429.0, 430.0)
        val thu = Rules.compute(hist, LocalDate.of(2026, 1, 8), 429.0, 420.0, 428.0)
        assertTrue(thu.ibsToday > 0.8 && thu.rsi2 < 10 && thu.signal && !thu.friday)
        val fri = Rules.compute(hist, LocalDate.of(2026, 1, 9), 429.0, 420.0, 428.0)
        assertTrue(fri.raw && fri.friday && !fri.signal)
        val up = (0 until 62).map { Bar(start.plusDays(it.toLong()), 401.0 + it, 399.0 + it, 400.0 + it) }
        val none = Rules.compute(up, LocalDate.of(2026, 1, 8), 470.0, 460.0, 469.0)
        assertTrue(none.rsi2 > 50 && !none.raw)
        val dbl = Rules.compute(up.dropLast(1) + Bar(start.plusDays(61), 470.0, 455.0, 456.0), LocalDate.of(2026, 1, 8), 470.0, 460.0, 462.0)
        assertTrue(dbl.ibsToday < 0.3 && dbl.ibsYesterday < 0.3 && dbl.signal)
    }

    @Test fun buyHoldSellCycle() {
        val s = e.newState()
        day("2026-01-05", true, s)
        assertEquals("BUY", s.getJSONObject("alert").getString("action"))
        assertEquals(0.03, s.getJSONObject("pending").getDouble("units"), 1e-9)
        e.filled(s, 25005.0)
        day("2026-01-06", true, s)
        assertEquals("HOLD", s.getJSONObject("alert").getString("action")); assertTrue(s.isNull("pending"))
        day("2026-01-07", false, s)
        assertEquals("SELL", s.getJSONObject("alert").getString("action"))
        e.fee(s, 0.40); e.filled(s, 25295.0)
        val t = s.getJSONArray("trades").getJSONObject(0)
        assertEquals((25295 - 25005) * 0.03 / 1.25 - 0.40, t.getDouble("pnl_gbp"), 0.01)
        e.fillCloses(s); val r = e.report(s)
        assertEquals(1, r.getInt("n")); assertEquals(7.20, r.getDouble("model"), 1e-9)
        assertEquals(7.20 - t.getDouble("pnl_gbp"), r.getDouble("cost_per"), 0.01)
        assertEquals(10 * 0.024, r.getDouble("slip"), 0.01)
        e.trialCheck(s); assertEquals("trial", s.getString("phase"))
    }

    @Test fun skipAndUnconfirmed() {
        val s = e.newState(); day("2026-01-08", true, s); e.skip(s)
        assertTrue(s.isNull("pending")); assertEquals(1, e.report(s).getInt("missed"))
        val s2 = e.newState(); day("2026-01-08", true, s2); day("2026-01-09", false, s2)
        assertEquals(1, e.report(s2).getInt("missed")); assertTrue(s2.isNull("position"))
        assertEquals("NONE", s2.getJSONObject("alert").getString("action"))
    }

    @Test fun trialUpgrade() {
        val s = e.newState()
        for ((d1, d2) in listOf("2026-01-05" to "2026-01-06", "2026-01-07" to "2026-01-08", "2026-01-08" to "2026-01-09")) {
            s.put("last_run", JSONObject.NULL); day(d1, true, s); e.filled(s, m.closes[d1]!!)
            s.put("last_run", JSONObject.NULL); day(d2, false, s); e.filled(s, m.closes[d2]!!)
        }
        now = Instant.parse("2026-03-01T21:00:00Z"); s.put("started", "2026-01-01")
        e.trialCheck(s)
        assertEquals("full", s.getString("phase")); assertEquals(2000.0, s.getDouble("exposure"), 0.0)
    }

    @Test fun checkNowIsPreviewMidday() {
        val s = e.newState(); now = Instant.parse("2026-01-05T15:00:00Z")
        m.sig = Signal("2026-01-05", 0.05, 0.2, 50.0, false, true, true)
        e.dailyJob(s, force = true)
        assertTrue(s.isNull("pending") && s.isNull("alert"))
        assertEquals("preview", s.getJSONArray("events").getJSONObject(0).getString("kind"))
    }

    @Test fun exitRemindersAndOverdue() {
        val s = e.newState(); day("2026-01-05", true, s)
        val txt = s.getJSONObject("alert").getString("text")
        assertTrue(txt, "Exit plan" in txt && "Tue 06 Jan" in txt && "20:50" in txt)
        e.lastCallJob(s); assertTrue(s.getJSONObject("alert").getBoolean("last_call"))
        assertNull(e.overdue(s, Instant.parse("2026-01-05T20:59:00Z")))
        assertTrue("skipped" in e.overdue(s, Instant.parse("2026-01-05T21:05:00Z"))!!)
        e.filled(s, 25000.0)
        e.headsupJob(s, LocalDate.parse("2026-01-06")); assertTrue("20:50" in s.getJSONObject("reminder").getString("text"))
        day("2026-01-06", false, s); assertEquals("SELL", s.getJSONObject("alert").getString("action")); assertTrue(s.isNull("reminder"))
        now = Instant.parse("2026-01-06T21:05:00Z"); notes.clear(); e.overdueJob(s)
        assertEquals(listOf("IBS: SELL not confirmed"), notes)
        e.filled(s, 25100.0); assertNull(e.overdue(s))
        val s2 = e.newState(); e.headsupJob(s2, LocalDate.parse("2026-01-06")); assertTrue(s2.isNull("reminder"))
    }

    @Test fun fridayAlwaysSells() {
        val s = e.newState(); day("2026-01-08", true, s); e.filled(s, 25000.0)
        assertTrue("Fri 09 Jan" in s.getJSONObject("position").getString("exit_plan"))
        m.sig = Signal("2026-01-09", 0.05, 0.2, 3.0, true, true, false); m.level = 25050.0
        e.dailyJob(s)
        val a = s.getJSONObject("alert")
        assertEquals("SELL", a.getString("action")); assertTrue("Friday" in a.getString("text"))
        val s2 = e.newState(); e.dailyJob(s2)
        assertEquals("NONE", s2.getJSONObject("alert").getString("action")); assertTrue("Friday" in s2.getJSONObject("alert").getString("text"))
    }

    @Test fun scheduleOrder() {
        var t = Instant.parse("2026-01-06T12:00:00Z"); val got = mutableListOf<String>()
        repeat(5) { val j = e.nextJob(t); got += "${j.kind}@${j.time}"; t = j.time }
        assertEquals(listOf("headsup@2026-01-06T18:00:00Z", "decide@2026-01-06T20:50:00Z", "lastcall@2026-01-06T20:56:00Z",
            "overdue@2026-01-06T21:05:00Z", "headsup@2026-01-07T18:00:00Z"), got)
        assertEquals(Instant.parse("2026-01-12T20:50:00Z"), e.nextDecision(Instant.parse("2026-01-09T21:00:00Z")))   // Fri -> Mon
        assertEquals(Instant.parse("2026-11-27T17:50:00Z"), e.nextDecision(Instant.parse("2026-11-26T12:00:00Z")))   // half-day after Thanksgiving
        assertNotNull(e.unitsFor(500.0, 27000.0, 1.3))
        assertFalse(Nyse.isSession(LocalDate.of(2026, 7, 3)))
    }
}
