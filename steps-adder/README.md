# Steps Adder

A tiny Android app that adds manual steps (for example, for a bike ride) to
**Health Connect**, so Samsung Health can pick them up when it syncs.

## 1. Get the APK

- On GitHub, open this repository → **Actions** → **Build Steps Adder APK** →
  the latest green run → download **StepsAdder-apk** (a zip). Unzip it to get `app-debug.apk`.
- Or build it yourself: open the `steps-adder` folder in Android Studio and press Run.

## 2. Install it on your phone

Copy `app-debug.apk` to the phone and tap it. Android will ask you to allow
installing from that source (e.g. "My Files" or Chrome). Allow it, then install.

## 3. Let Samsung Health read steps from Health Connect

Settings → **Health Connect** → **App permissions** → **Samsung Health** →
make sure reading **Steps** is allowed (or turn on "Allow all").

## 4. Use it

1. Open **Steps Adder** and tap **Allow access to Health Connect** → allow Steps.
2. Enter the number of steps, pick the day and the time of your ride, tap **Add steps**.
3. Wait a few minutes and open Samsung Health. Pull down to refresh.

**Tip:** choose the time you were actually cycling. During that time Samsung
Health recorded almost no steps of its own, so the two sources don't overlap.
When step records from different apps overlap in time, Health Connect may
count only one of them.

If you make a mistake, tap **Remove steps I added on this day**. It only removes
steps this app added.

## If Samsung Health's number doesn't change

The app still writes the steps to Health Connect, and the app shows the
Health Connect total. If Samsung Health never adds them to its own count, then
your Samsung Health version doesn't import steps from other apps, and there is
no way for an outside app to change it. Google Fit, Fitbit and other apps that
read Health Connect will still see the steps.
