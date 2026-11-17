package com.jimkaps.ibs.core

import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.temporal.TemporalAdjusters

/** NYSE trading days and closing times, from the exchange's holiday rules. */
object Nyse {
    val NY: ZoneId = ZoneId.of("America/New_York")
    private val SPECIAL_CLOSED = setOf(LocalDate.of(2025, 1, 9))   // national days of mourning
    private val cache = HashMap<Int, Set<LocalDate>>()

    private fun easter(y: Int): LocalDate {
        val a = y % 19; val b = y / 100; val c = y % 100; val d = b / 4; val e = b % 4
        val f = (b + 8) / 25; val g = (b - f + 1) / 3; val h = (19 * a + b - d - g + 15) % 30
        val i = c / 4; val k = c % 4; val l = (32 + 2 * e + 2 * i - h - k) % 7
        val m = (a + 11 * h + 22 * l) / 451
        val month = (h + l - 7 * m + 114) / 31; val day = (h + l - 7 * m + 114) % 31 + 1
        return LocalDate.of(y, month, day)
    }

    private fun nth(y: Int, month: Int, dow: DayOfWeek, n: Int) =
        LocalDate.of(y, month, 1).with(TemporalAdjusters.dayOfWeekInMonth(n, dow))

    private fun last(y: Int, month: Int, dow: DayOfWeek) =
        LocalDate.of(y, month, 1).with(TemporalAdjusters.lastInMonth(dow))

    private fun observed(d: LocalDate) = when (d.dayOfWeek) {
        DayOfWeek.SATURDAY -> d.minusDays(1)
        DayOfWeek.SUNDAY -> d.plusDays(1)
        else -> d
    }

    fun holidays(y: Int): Set<LocalDate> = synchronized(cache) {
        cache.getOrPut(y) {
            val h = mutableSetOf<LocalDate>()
            val ny = LocalDate.of(y, 1, 1)
            if (ny.dayOfWeek != DayOfWeek.SATURDAY) h += observed(ny)   // NYSE doesn't close on Dec 31 for a Saturday New Year
            h += nth(y, 1, DayOfWeek.MONDAY, 3)
            h += nth(y, 2, DayOfWeek.MONDAY, 3)
            h += easter(y).minusDays(2)
            h += last(y, 5, DayOfWeek.MONDAY)
            if (y >= 2022) h += observed(LocalDate.of(y, 6, 19))
            h += observed(LocalDate.of(y, 7, 4))
            h += nth(y, 9, DayOfWeek.MONDAY, 1)
            h += nth(y, 11, DayOfWeek.THURSDAY, 4)
            h += observed(LocalDate.of(y, 12, 25))
            h += SPECIAL_CLOSED.filter { it.year == y }
            h
        }
    }

    fun isSession(d: LocalDate) =
        d.dayOfWeek != DayOfWeek.SATURDAY && d.dayOfWeek != DayOfWeek.SUNDAY && d !in holidays(d.year)

    private fun isEarlyClose(d: LocalDate): Boolean {
        val weekdayMonThu = d.dayOfWeek.value in 1..4
        return (d.monthValue == 7 && d.dayOfMonth == 3 && weekdayMonThu) ||
            (d.monthValue == 12 && d.dayOfMonth == 24 && weekdayMonThu) ||
            d == nth(d.year, 11, DayOfWeek.THURSDAY, 4).plusDays(1)
    }

    fun close(d: LocalDate): Instant =
        ZonedDateTime.of(d, if (isEarlyClose(d)) LocalTime.of(13, 0) else LocalTime.of(16, 0), NY).toInstant()

    fun sessionOnOrAfter(d: LocalDate): LocalDate {
        var x = d
        while (!isSession(x)) x = x.plusDays(1)
        return x
    }

    fun nextSession(d: LocalDate) = sessionOnOrAfter(d.plusDays(1))

    fun nyDate(t: Instant): LocalDate = t.atZone(NY).toLocalDate()
}
