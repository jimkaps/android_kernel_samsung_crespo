package com.jimkaps.ibs

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.jimkaps.ibs.core.Channel
import com.jimkaps.ibs.core.Nyse
import java.time.Instant

class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val done = goAsync()
        Thread {
            val job = Alarms.jobFrom(intent)
            val attempt = intent.getIntExtra("attempt", 0)
            try {
                val e = engine(ctx)
                Store.edit(ctx) { e.runJob(it, job) }
            } catch (ex: Exception) {
                Log.e(TAG, "job ${job.kind} failed", ex)
                val beforeClose = Instant.now().plusSeconds(90) < Nyse.close(job.session)
                if (job.kind == "decide" && attempt < 5 && beforeClose) Alarms.retry(ctx, job, attempt + 1)
                else if (job.kind == "decide") Notifier.show(ctx, "IBS: couldn't check the signal",
                    "No price data (${ex.message}). Open the app and tap Check signal now, or check your connection.", Channel.SIGNAL)
            } finally {
                runCatching { if (attempt == 0) Alarms.schedule(ctx) }
                done.finish()
            }
        }.start()
    }
}

/** Alarms are cleared on reboot, app update and clock changes, so set them again. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        runCatching { Alarms.schedule(ctx) }.onFailure { Log.e(TAG, "reschedule failed", it) }
    }
}
