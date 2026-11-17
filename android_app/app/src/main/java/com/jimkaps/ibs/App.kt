package com.jimkaps.ibs

import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.jimkaps.ibs.core.Channel
import com.jimkaps.ibs.core.Engine
import com.jimkaps.ibs.core.Job
import com.jimkaps.ibs.core.YahooMarket
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.LocalDate

const val TAG = "IBS"

fun engine(ctx: Context) = Engine(YahooMarket(), { title, text, ch -> Notifier.show(ctx, title, text, ch) })

/** The assistant's state, kept in one JSON file in the app's private storage. */
object Store {
    private val lock = Any()
    private fun file(ctx: Context) = File(ctx.filesDir, "assistant_state.json")

    fun load(ctx: Context): JSONObject = synchronized(lock) {
        val f = file(ctx)
        if (f.exists()) JSONObject(f.readText()) else engine(ctx).newState().also { save(ctx, it) }
    }

    fun save(ctx: Context, s: JSONObject) = synchronized(lock) {
        val f = file(ctx); val tmp = File(f.path + ".tmp")
        tmp.writeText(s.toString(1)); tmp.renameTo(f)
    }

    fun <T> edit(ctx: Context, block: (JSONObject) -> T): T = synchronized(lock) {
        val s = load(ctx); val r = block(s); save(ctx, s); r
    }
}

object Notifier {
    private const val SIGNALS = "signals"
    private const val REMINDERS = "reminders"
    private const val INFO = "info"

    fun createChannels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(SIGNALS, "Trade signals (BUY / SELL / last call)", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Time-critical alerts about 10 minutes before the US close"; enableVibration(true)
            vibrationPattern = longArrayOf(0, 400, 200, 400, 200, 400)
        })
        nm.createNotificationChannel(NotificationChannel(REMINDERS, "Exit-day reminders", NotificationManager.IMPORTANCE_HIGH))
        nm.createNotificationChannel(NotificationChannel(INFO, "Other messages", NotificationManager.IMPORTANCE_DEFAULT))
    }

    fun show(ctx: Context, title: String, text: String, ch: Channel) {
        createChannels(ctx)
        val (id, chan) = when (ch) { Channel.SIGNAL -> 1 to SIGNALS; Channel.REMINDER -> 2 to REMINDERS; Channel.INFO -> 3 to INFO }
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(ctx, chan)
            .setSmallIcon(R.drawable.ic_notification).setContentTitle(title).setContentText(text)
            .setStyle(Notification.BigTextStyle().bigText(text)).setContentIntent(open).setAutoCancel(true)
            .setCategory(if (ch == Channel.SIGNAL) Notification.CATEGORY_ALARM else Notification.CATEGORY_REMINDER)
            .setVisibility(Notification.VISIBILITY_PUBLIC).build()
        runCatching { ctx.getSystemService(NotificationManager::class.java).notify(id, n) }
            .onFailure { Log.w(TAG, "notification not shown", it) }
    }
}

/** One alarm at a time: the next job (exit-day heads-up, decision, last call, overdue check). */
object Alarms {
    private const val MAIN = 0
    private const val RETRY = 1

    fun canExact(ctx: Context) = Build.VERSION.SDK_INT < 31 || ctx.getSystemService(AlarmManager::class.java).canScheduleExactAlarms()

    private fun intent(ctx: Context, job: Job, attempt: Int, code: Int) = PendingIntent.getBroadcast(ctx, code,
        Intent(ctx, AlarmReceiver::class.java).putExtra("kind", job.kind).putExtra("time", job.time.toEpochMilli())
            .putExtra("session", job.session.toString()).putExtra("attempt", attempt),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    // The decision uses an alarm-clock alarm (never delayed by battery saving); the others are exact alarms.
    private fun set(ctx: Context, at: Instant, pi: PendingIntent, decide: Boolean) {
        val am = ctx.getSystemService(AlarmManager::class.java)
        when {
            canExact(ctx) && decide -> {
                val show = PendingIntent.getActivity(ctx, 9, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
                am.setAlarmClock(AlarmManager.AlarmClockInfo(at.toEpochMilli(), show), pi)
            }
            canExact(ctx) -> am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at.toEpochMilli(), pi)
            else -> am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at.toEpochMilli(), pi)
        }
    }

    fun schedule(ctx: Context) {
        val e = engine(ctx); val now = Instant.now(); val s = Store.load(ctx)
        val kinds = mutableSetOf("decide")
        if (!s.isNull("position")) kinds += "headsup"
        if (!s.isNull("pending")) kinds += listOf("lastcall", "overdue")
        val job = e.nextJob(now, kinds)
        set(ctx, job.time, intent(ctx, job, 0, MAIN), job.kind == "decide")
        Store.edit(ctx) { it.put("next_check", e.nextDecision(now).toString()) }
        Log.i(TAG, "next job ${job.kind} at ${job.time}")
    }

    fun retry(ctx: Context, job: Job, attempt: Int) =
        set(ctx, Instant.now().plusSeconds(60), intent(ctx, job, attempt, RETRY), false)

    fun jobFrom(i: Intent) = Job(Instant.ofEpochMilli(i.getLongExtra("time", 0)), i.getStringExtra("kind") ?: "decide",
        LocalDate.parse(i.getStringExtra("session") ?: LocalDate.now().toString()))
}
