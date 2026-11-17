package com.jimkaps.ibs.core

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate

data class Bar(val date: LocalDate, val high: Double, val low: Double, val close: Double)

data class Signal(
    val date: String, val ibsToday: Double, val ibsYesterday: Double, val rsi2: Double,
    val friday: Boolean, val raw: Boolean, val signal: Boolean,
)

interface Market {
    fun signal(): Signal
    /** (US 100 index level, GBPUSD) */
    fun levels(): Pair<Double, Double>
    fun officialClose(date: String): Double?
}

object Rules {
    const val DBL = 0.30
    const val SINGLE = 0.10
    const val RSI_MAX = 10.0

    fun ibs(h: Double, l: Double, c: Double) = if (h > l) (c - l) / (h - l) else 0.5

    /** Wilder-style RSI(2), same as pandas ewm(alpha=0.5, adjust=True). */
    fun rsi2(closes: List<Double>): Double {
        var upN = 0.0; var dnN = 0.0; var den = 0.0
        for (i in 1 until closes.size) {
            val ch = closes[i] - closes[i - 1]
            upN = upN * 0.5 + maxOf(ch, 0.0); dnN = dnN * 0.5 + maxOf(-ch, 0.0); den = den * 0.5 + 1
        }
        if (den == 0.0) return 50.0
        val up = upN / den; val dn = dnN / den
        return if (dn == 0.0) 100.0 else 100 - 100 / (1 + up / dn)
    }

    /** past: completed sessions before [today], oldest first. */
    fun compute(past: List<Bar>, today: LocalDate, hi: Double, lo: Double, last: Double): Signal {
        val y = past.last()
        val it = ibs(hi, lo, last)
        val iy = ibs(y.high, y.low, y.close)
        val r = rsi2(past.map { it.close } + last)
        val raw = (it < DBL && iy < DBL) || it < SINGLE || r < RSI_MAX
        val friday = today.dayOfWeek == DayOfWeek.FRIDAY
        return Signal(today.toString(), round(it, 3), round(iy, 3), round(r, 1), friday, raw, raw && !friday)
    }

    fun round(v: Double, dp: Int): Double {
        var m = 1.0; repeat(dp) { m *= 10 }
        return Math.round(v * m) / m
    }
}

/** Yahoo Finance chart API (the same free data the desktop assistant uses). */
class YahooMarket(private val http: (String) -> String = ::httpGet) : Market {
    class Chart(val bars: List<Bar>, val marketTime: Instant, val price: Double, val dayHigh: Double?, val dayLow: Double?)

    fun chart(symbol: String, range: String): Chart =
        parse(http("https://query1.finance.yahoo.com/v8/finance/chart/${URLEncoder.encode(symbol, "UTF-8")}?range=$range&interval=1d"))

    override fun signal(): Signal {
        val c = chart("QQQ", "6mo")
        val today = Nyse.nyDate(c.marketTime)
        val past = c.bars.filter { it.date < today }
        val todayBar = c.bars.lastOrNull { it.date == today }
        val hi = c.dayHigh ?: todayBar?.high ?: error("no high for today")
        val lo = c.dayLow ?: todayBar?.low ?: error("no low for today")
        if (past.size < 30) error("not enough QQQ history from Yahoo")
        return Rules.compute(past, today, hi, lo, c.price)
    }

    override fun levels(): Pair<Double, Double> = chart("^NDX", "5d").price to chart("GBPUSD=X", "5d").price

    override fun officialClose(date: String): Double? {
        val d = LocalDate.parse(date)
        return chart("^NDX", "3mo").bars.firstOrNull { it.date == d }?.close
    }

    companion object {
        fun parse(body: String): Chart {
            val r = JSONObject(body).getJSONObject("chart").getJSONArray("result").getJSONObject(0)
            val meta = r.getJSONObject("meta")
            val bars = ArrayList<Bar>()
            val ts = r.optJSONArray("timestamp")
            if (ts != null) {
                val q = r.getJSONObject("indicators").getJSONArray("quote").getJSONObject(0)
                val h = q.getJSONArray("high"); val l = q.getJSONArray("low"); val c = q.getJSONArray("close")
                for (i in 0 until ts.length()) {
                    if (h.isNull(i) || l.isNull(i) || c.isNull(i)) continue
                    val bar = Bar(Nyse.nyDate(Instant.ofEpochSecond(ts.getLong(i))), h.getDouble(i), l.getDouble(i), c.getDouble(i))
                    if (bar.high > bar.low) bars += bar
                }
            }
            fun opt(k: String) = if (meta.has(k) && !meta.isNull(k)) meta.getDouble(k) else null
            return Chart(bars, Instant.ofEpochSecond(meta.getLong("regularMarketTime")),
                meta.getDouble("regularMarketPrice"), opt("regularMarketDayHigh"), opt("regularMarketDayLow"))
        }
    }
}

fun httpGet(url: String): String {
    var last: Exception? = null
    repeat(2) {
        try {
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 7000; c.readTimeout = 7000
            c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36")
            try {
                if (c.responseCode != 200) error("Yahoo answered HTTP ${c.responseCode}")
                return c.inputStream.bufferedReader().use { it.readText() }
            } finally { c.disconnect() }
        } catch (e: Exception) { last = e }
    }
    throw last ?: IllegalStateException("download failed")
}
