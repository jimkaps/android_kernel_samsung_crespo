# IBS Assistant for Android

The same assistant as `ibs_assistant/`, running entirely on your phone: no laptop or Raspberry Pi needed.
It downloads prices from Yahoo Finance itself, decides the signal about 10 minutes before each US close,
and sends a phone notification (BUY / SELL / HOLD, exit-day reminder, last call, overdue warning).

## Install
1. On your phone, open the latest **IBS Assistant app build** on the repository's Releases page and download **IBS-Assistant.apk**.
2. Open it. Android asks to allow installs from your browser or Files app: allow it, then tap **Install**.
3. Open the app and allow **notifications**. If the page shows orange boxes, tap each one:
   - **Allow alarms** (exact alarms) so alerts arrive on time;
   - **Allow background use** so battery saving doesn't delay them (on Samsung: Battery → **Unrestricted**).
4. Tap **Send a test alert** to check you get the notification and sound.

Your lock screen shows the next check (e.g. 20:50) as an alarm: that's the app's daily check, so it can't be delayed.
New builds install over the old one and keep your trade log. **Export trade log** saves a copy (JSON).

## Build
GitHub Actions builds it on every push to `android_app/` (`.github/workflows/build-ibs-app.yml`) and publishes a release.
Logic lives in `app/src/main/java/com/jimkaps/ibs/core/` (pure Kotlin, unit-tested in `app/src/test/`);
`MainActivity` shows `assets/index.html` in a WebView, `AlarmReceiver` runs the scheduled jobs.
