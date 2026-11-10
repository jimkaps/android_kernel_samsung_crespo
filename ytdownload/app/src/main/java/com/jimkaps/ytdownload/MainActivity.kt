package com.jimkaps.ytdownload

import android.Manifest
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.jimkaps.ytdownload.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var b: ActivityMainBinding
    private var pendingAfterPermission: (() -> Unit)? = null

    private val storagePermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) pendingAfterPermission?.invoke()
            else Toast.makeText(this, R.string.storage_denied, Toast.LENGTH_LONG).show()
            pendingAfterPermission = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)

        handleShareIntent(intent)

        b.pasteButton.setOnClickListener {
            val clip = getSystemService(ClipboardManager::class.java)?.primaryClip
            val text = clip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(this)?.toString()
            if (!text.isNullOrBlank()) b.urlInput.setText(extractUrl(text) ?: text.trim())
        }
        b.downloadButton.setOnClickListener { startDownload() }
        b.cancelButton.setOnClickListener { Downloader.cancel() }
        b.updateButton.setOnClickListener { Downloader.updateYtDlp(this) }

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                Downloader.state.collect { render(it) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent)
    }

    private fun handleShareIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return
            b.urlInput.setText(extractUrl(text) ?: text.trim())
        }
    }

    private fun extractUrl(text: String): String? =
        Regex("""https?://\S+""").find(text)?.value

    private fun startDownload() {
        val url = b.urlInput.text?.toString()?.trim().orEmpty()
        if (!url.startsWith("http")) {
            b.urlLayout.error = getString(R.string.invalid_url)
            return
        }
        b.urlLayout.error = null
        val mode = if (b.modeAudio.isChecked) Mode.AUDIO else Mode.VIDEO
        val go = { Downloader.download(this, url, mode) }

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE)
            != PackageManager.PERMISSION_GRANTED
        ) {
            pendingAfterPermission = go
            storagePermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        } else {
            go()
        }
    }

    private fun render(s: UiState) {
        b.status.text = s.status
        b.log.text = s.log
        b.log.visibility = if (s.log.isBlank()) View.GONE else View.VISIBLE

        b.progress.visibility = if (s.busy) View.VISIBLE else View.INVISIBLE
        b.progress.isIndeterminate = s.progress < 0
        if (s.progress >= 0) b.progress.setProgressCompat(s.progress, true)

        b.downloadButton.isEnabled = s.ready && !s.busy
        b.updateButton.isEnabled = s.ready && !s.busy
        b.cancelButton.visibility = if (s.busy) View.VISIBLE else View.GONE
        b.urlInput.isEnabled = !s.busy
        b.modeGroup.isEnabled = !s.busy

        // Keep the screen on while downloading so the system doesn't kill us.
        if (s.busy) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}
