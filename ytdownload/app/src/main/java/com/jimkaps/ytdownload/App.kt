package com.jimkaps.ytdownload

import android.app.Application

class App : Application() {
    override fun onCreate() {
        super.onCreate()
        Downloader.initialize(this)
    }
}
