package com.jimkaps.ytdownload

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.provider.OpenableColumns
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import android.webkit.MimeTypeMap
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import java.io.FileInputStream
import java.util.UUID

enum class Mode { VIDEO, AUDIO }

data class UiState(
    val ready: Boolean = false,
    val busy: Boolean = false,
    val progress: Int = 0,          // 0..100, or -1 for indeterminate
    val status: String = "Preparing downloader…",
    val log: String = "",
)

/**
 * Lives for the whole process so a download keeps going across screen rotations.
 */
object Downloader {
    private const val TAG = "YTDownload"
    const val FOLDER = "YTDownload"

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    private var currentProcessId: String? = null
    private var job: Job? = null

    fun initialize(context: Context) {
        val app = context.applicationContext
        scope.launch {
            try {
                YoutubeDL.getInstance().init(app)
                FFmpeg.getInstance().init(app)
                autoUpdate(app)
                val ver = YoutubeDL.getInstance().version(app) ?: "unknown"
                _state.update { it.copy(ready = true, status = "Ready (yt-dlp $ver)") }
            } catch (e: Exception) {
                Log.e(TAG, "init failed", e)
                _state.update { it.copy(status = "Failed to initialise: ${e.message}") }
            }
        }
    }

    /**
     * YouTube changes often and old yt-dlp versions start failing (e.g. HTTP 403),
     * so check for a new yt-dlp at most once a day on startup. Failures (offline etc.) are ignored.
     */
    private fun autoUpdate(app: Context) {
        val prefs = app.getSharedPreferences("ytdownload", Context.MODE_PRIVATE)
        val last = prefs.getLong("lastYtDlpUpdateCheck", 0L)
        if (System.currentTimeMillis() - last < 24 * 60 * 60 * 1000L) return
        _state.update { it.copy(status = "Checking for yt-dlp updates…") }
        try {
            YoutubeDL.getInstance().updateYoutubeDL(app, YoutubeDL.UpdateChannel.STABLE)
            prefs.edit().putLong("lastYtDlpUpdateCheck", System.currentTimeMillis()).apply()
        } catch (e: Exception) {
            Log.w(TAG, "auto-update failed", e)
        }
    }

    fun download(context: Context, url: String, mode: Mode) {
        if (_state.value.busy || !_state.value.ready) return
        val app = context.applicationContext
        val processId = UUID.randomUUID().toString()
        currentProcessId = processId
        _state.update { it.copy(busy = true, progress = -1, status = "Starting…", log = "") }

        job = scope.launch {
            val tmpDir = File(app.cacheDir, "dl/$processId").apply { mkdirs() }
            try {
                val request = YoutubeDLRequest(url).apply {
                    addOption("--no-playlist")
                    addOption("--no-mtime")
                    addOption("-o", "${tmpDir.absolutePath}/%(title).120B [%(id)s].%(ext)s")
                    when (mode) {
                        Mode.VIDEO -> {
                            addOption("-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b")
                            addOption("--merge-output-format", "mp4")
                        }
                        Mode.AUDIO -> {
                            addOption("-f", "ba/b")
                            addOption("-x")
                            addOption("--audio-format", "mp3")
                            addOption("--audio-quality", "0")
                        }
                    }
                }

                YoutubeDL.getInstance().execute(request, processId) { progress, etaSec, line ->
                    _state.update {
                        it.copy(
                            progress = if (progress < 0) -1 else progress.toInt().coerceIn(0, 100),
                            status = if (progress >= 0) {
                                "Downloading ${progress.toInt()}%" + if (etaSec > 0) " · ${etaSec}s left" else ""
                            } else it.status,
                            log = appendLog(it.log, line),
                        )
                    }
                }

                _state.update { it.copy(progress = -1, status = "Saving to Downloads…") }
                val files = tmpDir.listFiles()?.filter { it.isFile && !it.name.endsWith(".part") }.orEmpty()
                if (files.isEmpty()) error("yt-dlp finished but produced no file")
                val saved = files.map { saveToDownloads(app, it) }
                _state.update {
                    it.copy(busy = false, progress = 100,
                        status = "Saved to Downloads/$FOLDER:\n" + saved.joinToString("\n"))
                }
            } catch (e: YoutubeDL.CanceledException) {
                _state.update { it.copy(busy = false, progress = 0, status = "Cancelled") }
            } catch (e: Exception) {
                Log.e(TAG, "download failed", e)
                val reason = e.message?.lineSequence()?.lastOrNull { l -> l.isNotBlank() } ?: e.javaClass.simpleName
                _state.update {
                    it.copy(busy = false, progress = 0,
                        status = "Failed: $reason\n\nTip: tap \"Update yt-dlp\" below and try again — " +
                            "most failures are fixed by a newer yt-dlp.",
                        log = appendLog(it.log, e.message ?: ""))
                }
            } finally {
                tmpDir.deleteRecursively()
                currentProcessId = null
            }
        }
    }

    fun cancel() {
        currentProcessId?.let { YoutubeDL.getInstance().destroyProcessById(it) }
        cancelRequested = true
        ffmpegProcess?.destroy()
        job?.cancel()
    }

    @Volatile private var ffmpegProcess: Process? = null
    @Volatile private var cancelRequested = false

    /** Converts a video/audio file picked on the phone into an MP3 in Downloads/YTDownload. */
    fun convertToMp3(context: Context, uri: Uri) {
        if (_state.value.busy || !_state.value.ready) return
        val app = context.applicationContext
        cancelRequested = false
        _state.update { it.copy(busy = true, progress = -1, status = "Reading file…", log = "") }

        job = scope.launch {
            val workDir = File(app.cacheDir, "convert/${UUID.randomUUID()}").apply { mkdirs() }
            try {
                val displayName = queryDisplayName(app, uri) ?: "audio"
                val baseName = displayName.substringBeforeLast('.', displayName)
                    .replace(Regex("""[\\/:*?"<>|]"""), "_").ifBlank { "audio" }
                val input = File(workDir, "input." + displayName.substringAfterLast('.', "bin"))
                app.contentResolver.openInputStream(uri)?.use { inp ->
                    input.outputStream().use { inp.copyTo(it) }
                } ?: error("Could not open the selected file")

                val output = File(workDir, "$baseName.mp3")
                _state.update { it.copy(status = "Converting $displayName to MP3…") }
                runFfmpeg(app, listOf(
                    "-y", "-hide_banner", "-nostdin",
                    "-i", input.absolutePath,
                    "-vn", "-map_metadata", "0",
                    "-c:a", "libmp3lame", "-q:a", "0",
                    output.absolutePath,
                ))
                if (!output.exists() || output.length() == 0L) error("ffmpeg produced no output")

                _state.update { it.copy(progress = -1, status = "Saving to Downloads…") }
                val saved = saveToDownloads(app, output)
                _state.update {
                    it.copy(busy = false, progress = 100, status = "Saved to Downloads/$FOLDER:\n$saved")
                }
            } catch (e: Exception) {
                Log.e(TAG, "conversion failed", e)
                _state.update {
                    it.copy(busy = false, progress = 0,
                        status = if (cancelRequested) "Cancelled" else "Conversion failed: ${e.message}")
                }
            } finally {
                ffmpegProcess = null
                workDir.deleteRecursively()
            }
        }
    }

    /** Runs the ffmpeg binary bundled by youtubedl-android, reporting progress from its stderr. */
    private fun runFfmpeg(context: Context, args: List<String>) {
        val ffmpeg = File(context.applicationInfo.nativeLibraryDir, "libffmpeg.so")
        val packages = File(context.noBackupFilesDir, "youtubedl-android/packages")
        val pb = ProcessBuilder(listOf(ffmpeg.absolutePath) + args).redirectErrorStream(true)
        pb.environment()["LD_LIBRARY_PATH"] =
            "${File(packages, "python/usr/lib")}:${File(packages, "ffmpeg/usr/lib")}"
        pb.environment()["HOME"] = context.cacheDir.absolutePath

        val process = pb.start()
        ffmpegProcess = process
        val timeRe = Regex("""(\d+):(\d{2}):(\d{2}(?:\.\d+)?)""")
        fun seconds(m: MatchResult) =
            m.groupValues[1].toDouble() * 3600 + m.groupValues[2].toDouble() * 60 + m.groupValues[3].toDouble()

        var duration = 0.0
        val tail = ArrayDeque<String>()
        val line = StringBuilder()
        process.inputStream.bufferedReader().use { reader ->
            while (true) {
                val c = reader.read()
                if (c == -1 || c == '\n'.code || c == '\r'.code) {
                    val l = line.toString().trim()
                    line.clear()
                    if (l.isNotEmpty()) {
                        tail.addLast(l); if (tail.size > 15) tail.removeFirst()
                        if (duration == 0.0 && l.startsWith("Duration:")) {
                            timeRe.find(l)?.let { duration = seconds(it) }
                        }
                        val t = Regex("""time=(\S+)""").find(l)?.groupValues?.get(1)?.let { timeRe.find(it) }
                        if (t != null && duration > 0) {
                            val pct = (seconds(t) / duration * 100).toInt().coerceIn(0, 100)
                            _state.update { it.copy(progress = pct, status = "Converting to MP3 $pct%") }
                        }
                    }
                    if (c == -1) break
                } else {
                    line.append(c.toChar())
                }
            }
        }
        val code = process.waitFor()
        if (code != 0) {
            _state.update { it.copy(log = tail.joinToString("\n")) }
            error("ffmpeg exited with code $code")
        }
    }

    private fun queryDisplayName(context: Context, uri: Uri): String? =
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)
            ?.use { c -> if (c.moveToFirst()) c.getString(0) else null }

    fun updateYtDlp(context: Context) {
        if (_state.value.busy) return
        val app = context.applicationContext
        _state.update { it.copy(busy = true, progress = -1, status = "Updating yt-dlp…") }
        scope.launch {
            try {
                val result = YoutubeDL.getInstance().updateYoutubeDL(app, YoutubeDL.UpdateChannel.STABLE)
                val ver = YoutubeDL.getInstance().version(app) ?: "unknown"
                val msg = if (result == YoutubeDL.UpdateStatus.ALREADY_UP_TO_DATE) "already up to date" else "updated"
                _state.update { it.copy(busy = false, progress = 0, status = "yt-dlp $msg ($ver)") }
            } catch (e: Exception) {
                Log.e(TAG, "update failed", e)
                _state.update { it.copy(busy = false, progress = 0, status = "Update failed: ${e.message}") }
            }
        }
    }

    private fun appendLog(log: String, line: String): String {
        if (line.isBlank()) return log
        val lines = (log.lines() + line).filter { it.isNotBlank() }
        return lines.takeLast(40).joinToString("\n")
    }

    /** Copies a finished file into the public Downloads/YTDownload folder. Returns its display name. */
    private fun saveToDownloads(context: Context, file: File): String {
        val ext = file.extension.lowercase()
        val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "application/octet-stream"

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, file.name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/$FOLDER")
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("Could not create file in Downloads")
            resolver.openOutputStream(uri)!!.use { out ->
                FileInputStream(file).use { it.copyTo(out) }
            }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
        } else {
            @Suppress("DEPRECATION")
            val dir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), FOLDER)
            dir.mkdirs()
            var target = File(dir, file.name)
            var n = 1
            while (target.exists()) {
                target = File(dir, "${file.nameWithoutExtension} (${n++}).${file.extension}")
            }
            file.copyTo(target)
            MediaScannerConnection.scanFile(context, arrayOf(target.absolutePath), arrayOf(mime), null)
            return target.name
        }
        return file.name
    }
}
