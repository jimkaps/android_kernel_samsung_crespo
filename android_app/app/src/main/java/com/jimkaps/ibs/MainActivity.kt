package com.jimkaps.ibs

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.NotificationManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.jimkaps.ibs.core.Channel
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Notifier.createChannels(this)
        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true
        }
        web.addJavascriptInterface(Bridge(), "IBS")
        setContentView(web)
        web.loadUrl("file:///android_asset/index.html")
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    override fun onResume() {
        super.onResume()
        Thread {
            runCatching { Alarms.schedule(this) }
            runCatching { Store.edit(this) { engine(this).fillCloses(it) } }
            js("refresh()")
        }.start()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) = js("refresh()")

    private fun js(code: String) = runOnUiThread { web.evaluateJavascript(code, null) }

    private fun ok(block: () -> Unit): String = try {
        block(); JSONObject().put("ok", true).toString()
    } catch (e: Exception) {
        JSONObject().put("ok", false).put("error", e.message ?: e.javaClass.simpleName).toString()
    }

    private fun num(v: String) = v.trim().replace(",", "").toDoubleOrNull() ?: throw IllegalArgumentException("Enter a number.")

    inner class Bridge {
        private val ctx get() = this@MainActivity

        @JavascriptInterface fun state(): String {
            val e = engine(ctx); val s = Store.load(ctx)
            val notif = ctx.getSystemService(NotificationManager::class.java).areNotificationsEnabled()
            val battery = ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)
            return JSONObject().put("state", s).put("report", e.report(s)).put("overdue", e.overdue(s) ?: JSONObject.NULL)
                .put("perms", JSONObject().put("notifications", notif).put("exact", Alarms.canExact(ctx)).put("battery", battery))
                .toString()
        }

        @JavascriptInterface fun filled(price: String) = ok { Store.edit(ctx) { engine(ctx).filled(it, num(price)) }; Alarms.schedule(ctx) }
        @JavascriptInterface fun skip() = ok { Store.edit(ctx) { engine(ctx).skip(it) }; Alarms.schedule(ctx) }
        @JavascriptInterface fun fee(amount: String) = ok { Store.edit(ctx) { engine(ctx).fee(it, num(amount)) } }
        @JavascriptInterface fun exposure(amount: String) = ok { Store.edit(ctx) { engine(ctx).setExposure(it, num(amount)) } }

        @JavascriptInterface fun check() {
            Thread {
                val r = ok { Store.edit(ctx) { engine(ctx).dailyJob(it, force = true) } }
                js("onChecked(${JSONObject.quote(r)})")
            }.start()
        }

        @JavascriptInterface fun testAlert() =
            Notifier.show(ctx, "IBS: test alert", "Alerts work. Real ones arrive about 10 minutes before the US close.", Channel.SIGNAL)

        @JavascriptInterface fun fixNotifications() = runOnUiThread {
            if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED &&
                shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS))
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
            else startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName))
        }

        @JavascriptInterface fun fixExact() = runOnUiThread {
            if (Build.VERSION.SDK_INT >= 31)
                startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:$packageName")))
        }

        @SuppressLint("BatteryLife")
        @JavascriptInterface fun fixBattery() = runOnUiThread {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        }

        @JavascriptInterface fun export() = runOnUiThread {
            val send = Intent(Intent.ACTION_SEND).setType("application/json")
                .putExtra(Intent.EXTRA_SUBJECT, "IBS assistant trade log")
                .putExtra(Intent.EXTRA_TEXT, Store.load(ctx).toString(1))
            startActivity(Intent.createChooser(send, "Save or send your trade log"))
        }
    }
}
