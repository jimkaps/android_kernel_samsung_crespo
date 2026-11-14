package app.stepsadder

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.metadata.DataOrigin
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

/**
 * Adds manual steps (e.g. for a bike ride) to Health Connect, which
 * Samsung Health can then read when it syncs with Health Connect.
 */
class MainActivity : ComponentActivity() {

    private val permissions = setOf(
        HealthPermission.getWritePermission(StepsRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class),
    )

    private var client: HealthConnectClient? = null

    private var day: LocalDate = LocalDate.now()
    private var startTime: LocalTime = LocalTime.now().minusHours(1).withSecond(0).withNano(0)
    private var endTime: LocalTime = LocalTime.now().withSecond(0).withNano(0)

    private lateinit var status: TextView
    private lateinit var grantButton: Button
    private lateinit var stepsInput: EditText
    private lateinit var dateButton: Button
    private lateinit var startButton: Button
    private lateinit var endButton: Button
    private lateinit var addButton: Button
    private lateinit var removeButton: Button
    private lateinit var totals: TextView

    private val timeFmt = DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
    private val dateFmt = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)

    private val requestPermissions =
        registerForActivityResult(PermissionController.createRequestPermissionResultContract()) {
            checkPermissions()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        status = findViewById(R.id.status)
        grantButton = findViewById(R.id.grantButton)
        stepsInput = findViewById(R.id.stepsInput)
        dateButton = findViewById(R.id.dateButton)
        startButton = findViewById(R.id.startButton)
        endButton = findViewById(R.id.endButton)
        addButton = findViewById(R.id.addButton)
        removeButton = findViewById(R.id.removeButton)
        totals = findViewById(R.id.totals)

        // If "now" is just after midnight, start-1h would wrap to yesterday evening.
        if (startTime.isAfter(endTime)) startTime = LocalTime.MIDNIGHT

        grantButton.setOnClickListener { requestPermissions.launch(permissions) }
        dateButton.setOnClickListener { pickDate() }
        startButton.setOnClickListener { pickTime(startTime) { startTime = it; refreshLabels() } }
        endButton.setOnClickListener { pickTime(endTime) { endTime = it; refreshLabels() } }
        addButton.setOnClickListener { addSteps() }
        removeButton.setOnClickListener { removeMySteps() }
        findViewById<Button>(R.id.openHcButton).setOnClickListener {
            startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS))
        }

        refreshLabels()
        setUpHealthConnect()
    }

    override fun onResume() {
        super.onResume()
        if (client != null) checkPermissions()
    }

    private fun setUpHealthConnect() {
        when (HealthConnectClient.getSdkStatus(this)) {
            HealthConnectClient.SDK_AVAILABLE -> {
                client = HealthConnectClient.getOrCreate(this)
                checkPermissions()
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                setEnabled(false)
                status.text = "Health Connect needs to be installed or updated. Tap the button below."
                grantButton.text = "Get Health Connect"
                grantButton.visibility = View.VISIBLE
                grantButton.setOnClickListener {
                    val uri = Uri.parse(
                        "market://details?id=com.google.android.apps.healthdata&url=healthconnect%3A%2F%2Fonboarding"
                    )
                    startActivity(Intent(Intent.ACTION_VIEW, uri).setPackage("com.android.vending"))
                }
            }
            else -> {
                setEnabled(false)
                status.text = "Health Connect is not available on this phone."
            }
        }
    }

    private fun checkPermissions() {
        val c = client ?: return
        lifecycleScope.launch {
            val granted = c.permissionController.getGrantedPermissions()
            if (granted.containsAll(permissions)) {
                grantButton.visibility = View.GONE
                status.text = "Connected to Health Connect."
                setEnabled(true)
                refreshTotals()
            } else {
                grantButton.visibility = View.VISIBLE
                status.text = "This app needs permission to read and write steps in Health Connect."
                setEnabled(false)
            }
        }
    }

    private fun setEnabled(enabled: Boolean) {
        addButton.isEnabled = enabled
        removeButton.isEnabled = enabled
    }

    private fun refreshLabels() {
        dateButton.text = day.format(dateFmt) + if (day == LocalDate.now()) " (today)" else ""
        startButton.text = startTime.format(timeFmt)
        endButton.text = endTime.format(timeFmt)
    }

    private fun pickDate() {
        val dlg = DatePickerDialog(
            this,
            { _, y, m, d ->
                day = LocalDate.of(y, m + 1, d)
                refreshLabels()
                refreshTotals()
            },
            day.year, day.monthValue - 1, day.dayOfMonth,
        )
        dlg.datePicker.maxDate = System.currentTimeMillis()
        dlg.show()
    }

    private fun pickTime(initial: LocalTime, onPicked: (LocalTime) -> Unit) {
        TimePickerDialog(
            this,
            { _, h, min -> onPicked(LocalTime.of(h, min)) },
            initial.hour, initial.minute,
            android.text.format.DateFormat.is24HourFormat(this),
        ).show()
    }

    private fun zoned(time: LocalTime): ZonedDateTime = day.atTime(time).atZone(ZoneId.systemDefault())

    private fun dayRange(): TimeRangeFilter {
        val zone = ZoneId.systemDefault()
        val start = day.atStartOfDay(zone).toInstant()
        val end = day.plusDays(1).atStartOfDay(zone).toInstant()
        return TimeRangeFilter.between(start, end)
    }

    private fun addSteps() {
        val c = client ?: return
        val count = stepsInput.text.toString().toLongOrNull()
        if (count == null || count <= 0) {
            toast("Enter a number of steps")
            return
        }
        if (count > 100_000) {
            toast("That's a lot of steps - enter 100,000 or less")
            return
        }
        val start = zoned(startTime)
        val end = zoned(endTime)
        if (!end.isAfter(start)) {
            toast("The end time must be after the start time")
            return
        }
        if (end.toInstant().isAfter(Instant.now())) {
            toast("The end time can't be in the future")
            return
        }

        val record = StepsRecord(
            startTime = start.toInstant(),
            startZoneOffset = start.offset,
            endTime = end.toInstant(),
            endZoneOffset = end.offset,
            count = count,
            metadata = Metadata.manualEntry(),
        )

        lifecycleScope.launch {
            try {
                c.insertRecords(listOf(record))
                stepsInput.text.clear()
                toast("Added $count steps")
                refreshTotals()
            } catch (e: Exception) {
                toast("Could not add steps: ${e.message}")
            }
        }
    }

    private fun removeMySteps() {
        val c = client ?: return
        lifecycleScope.launch {
            try {
                val mine = c.readRecords(
                    ReadRecordsRequest(
                        recordType = StepsRecord::class,
                        timeRangeFilter = dayRange(),
                        dataOriginFilter = setOf(DataOrigin(packageName)),
                    )
                ).records
                if (mine.isEmpty()) {
                    toast("Nothing added by this app on that day")
                    return@launch
                }
                c.deleteRecords(
                    StepsRecord::class,
                    recordIdsList = mine.map { it.metadata.id },
                    clientRecordIdsList = emptyList(),
                )
                toast("Removed ${mine.sumOf { it.count }} steps")
                refreshTotals()
            } catch (e: Exception) {
                toast("Could not remove steps: ${e.message}")
            }
        }
    }

    private fun refreshTotals() {
        val c = client ?: return
        lifecycleScope.launch {
            try {
                val all = c.aggregate(
                    AggregateRequest(
                        metrics = setOf(StepsRecord.COUNT_TOTAL),
                        timeRangeFilter = dayRange(),
                    )
                )[StepsRecord.COUNT_TOTAL] ?: 0L
                val mine = c.aggregate(
                    AggregateRequest(
                        metrics = setOf(StepsRecord.COUNT_TOTAL),
                        timeRangeFilter = dayRange(),
                        dataOriginFilter = setOf(DataOrigin(packageName)),
                    )
                )[StepsRecord.COUNT_TOTAL] ?: 0L
                totals.text = "On ${day.format(dateFmt)}:\n" +
                    "• Added by this app: $mine steps\n" +
                    "• Health Connect total (all apps): $all steps\n\n" +
                    "Now open Samsung Health and check whether its step count went up."
            } catch (e: Exception) {
                totals.text = "Could not read totals: ${e.message}"
            }
        }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
