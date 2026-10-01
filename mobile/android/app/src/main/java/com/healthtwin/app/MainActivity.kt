package com.healthtwin.app

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.DateFormat
import java.time.Duration
import java.time.Instant
import java.util.Date
import java.util.TimeZone

/**
 * Health Twin companion app.
 *
 * 1. Pair with the website (scan its QR code, or type the server address and 6-digit code).
 * 2. Allow Health Connect read access.
 * 3. Sync: the last 7 days on the first sync, then only what is new. While the app
 *    is on screen it syncs every minute, so the twin on the website follows along.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private var healthClient: HealthConnectClient? = null
    private var sdkStatus = HealthConnectClient.SDK_UNAVAILABLE
    private var granted: Set<String> = emptySet()
    private var syncing = false

    private lateinit var statusText: TextView
    private lateinit var healthText: TextView
    private lateinit var resultText: TextView
    private lateinit var serverInput: EditText
    private lateinit var codeInput: EditText
    private lateinit var pairCard: LinearLayout
    private lateinit var syncCard: LinearLayout
    private lateinit var permissionButton: Button
    private lateinit var syncButton: Button

    private val healthPermissionLauncher =
        registerForActivityResult(PermissionController.createRequestPermissionResultContract()) { result ->
            granted = result
            refreshUi()
            if (HealthReader.HEART_RATE in result) syncNow(manual = true)
            else if (result.isNotEmpty()) toast("Heart rate is needed for the twin. Allow it in Health Connect.")
        }

    private val scanQr = registerForActivityResult(ScanContract()) { result ->
        val text = result.contents ?: return@registerForActivityResult
        val uri = Uri.parse(text)
        if (uri.scheme == "healthtwin") handlePairLink(uri) else toast("That QR code isn't a Health Twin pairing code.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        setContentView(buildLayout())
        setUpHealthConnect()
        refreshUi()
        intent?.data?.let { handlePairLink(it) }

        // Auto-sync every minute while the app is on screen.
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                refreshPermissions()
                while (true) {
                    if (prefs.isPaired && HealthReader.HEART_RATE in granted) syncNow(manual = false)
                    delay(60_000)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.data?.let { handlePairLink(it) }
    }

    // ------------------------------------------------------------ Health Connect
    private fun setUpHealthConnect() {
        sdkStatus = HealthConnectClient.getSdkStatus(this)
        healthClient = if (sdkStatus == HealthConnectClient.SDK_AVAILABLE) HealthConnectClient.getOrCreate(this) else null
    }

    private suspend fun refreshPermissions() {
        val client = healthClient ?: return
        granted = runCatching { HealthReader(client).grantedPermissions() }.getOrDefault(emptySet())
        refreshUi()
    }

    private fun askPermissions() {
        when {
            healthClient != null -> healthPermissionLauncher.launch(HealthReader.PERMISSIONS)
            sdkStatus == HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> openHealthConnectInStore()
            else -> toast("Health Connect isn't available on this phone (Android 8 or newer is needed).")
        }
    }

    private fun openHealthConnectInStore() {
        val pkg = "com.google.android.apps.healthdata"
        val uri = Uri.parse("market://details?id=$pkg&url=healthconnect%3A%2F%2Fonboarding")
        runCatching { startActivity(Intent(Intent.ACTION_VIEW, uri).setPackage("com.android.vending")) }
            .onFailure { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$pkg"))) }
    }

    private fun openHealthConnectSettings() {
        runCatching { startActivity(Intent(HealthConnectClient.ACTION_HEALTH_CONNECT_SETTINGS)) }
            .onFailure { toast("Open Health Connect from your phone's Settings.") }
    }

    // ------------------------------------------------------------------- pairing
    private fun handlePairLink(uri: Uri) {
        if (uri.scheme != "healthtwin" || uri.host != "pair") return
        val server = uri.getQueryParameter("server").orEmpty()
        val code = uri.getQueryParameter("code").orEmpty()
        serverInput.setText(server)
        codeInput.setText(code)
        if (server.isNotBlank() && code.length == 6) pair(server, code)
    }

    private fun normalizeServer(raw: String): String? {
        var s = raw.trim().trimEnd('/')
        if (s.isEmpty()) return null
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://$s"
        val uri = Uri.parse(s)
        if (uri.host.isNullOrBlank()) return null
        return if (uri.port == -1 && uri.scheme == "http") "${uri.scheme}://${uri.host}:8000" else "${uri.scheme}://${uri.host}:${uri.port}".replace(":-1", "")
    }

    private fun pair(rawServer: String, code: String) {
        val server = normalizeServer(rawServer)
        if (server == null || !Regex("\\d{6}").matches(code.trim())) {
            toast("Enter the server address and the 6-digit code shown on the website.")
            return
        }
        statusText.text = "Pairing with $server …"
        lifecycleScope.launch {
            try {
                val deviceName = "${Build.MANUFACTURER.replaceFirstChar { it.uppercase() }} ${Build.MODEL}"
                val r = withContext(Dispatchers.IO) { TwinApi.claim(server, code.trim(), deviceName) }
                prefs.server = server
                prefs.token = r.getString("token")
                prefs.twinId = r.getString("twin_id")
                prefs.twinName = r.optString("display_name")
                prefs.lastSyncEnd = null
                prefs.lastResult = null
                codeInput.setText("")
                toast("Paired with the twin server.")
                refreshUi()
                if (HealthReader.HEART_RATE in granted) syncNow(manual = true) else askPermissions()
            } catch (e: TwinApiException) {
                statusText.text = "Pairing failed: ${e.message}"
            } catch (e: Exception) {
                statusText.text = unreachable(server)
            }
        }
    }

    private fun unpair() {
        prefs.clearPairing()
        refreshUi()
        toast("Unpaired. The data already sent stays on the computer until you delete it there.")
    }

    // ---------------------------------------------------------------------- sync
    private fun utcOffsetHours(): Double = TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 3_600_000.0

    private fun syncNow(manual: Boolean) {
        val client = healthClient ?: return
        val server = prefs.server ?: return
        val token = prefs.token ?: return
        if (syncing) return
        syncing = true
        syncButton.isEnabled = false
        if (manual) resultText.text = "Reading Health Connect…"
        lifecycleScope.launch {
            try {
                val reader = HealthReader(client)
                granted = reader.grantedPermissions()
                if (HealthReader.HEART_RATE !in granted) {
                    resultText.text = "Allow heart-rate access in Health Connect first."
                    return@launch
                }
                val end = Instant.now()
                // First sync: the last 7 days (enough to learn a baseline). Later: from just before the last sync.
                val start = prefs.lastSyncEnd?.let { Instant.ofEpochMilli(it).minus(Duration.ofHours(2)) }
                    ?: end.minus(Duration.ofDays(7))
                val reading = reader.read(start, end, granted, utcOffsetHours())
                if (manual) resultText.text = "Sending to the twin…"
                val r = withContext(Dispatchers.IO) { TwinApi.sync(server, token, reading.body) }
                val status = r.optString("status")
                if (status == "synced" || status == "nothing_new") prefs.lastSyncEnd = end.toEpochMilli()
                prefs.lastResult = describe(r, reading)
            } catch (e: TwinApiException) {
                if (e.code == 401 || e.code == 410) {
                    prefs.clearPairing()
                    prefs.lastResult = "This phone was disconnected on the website (${e.message}). Pair again."
                } else {
                    prefs.lastResult = "Server error ${e.code}: ${e.message}"
                }
            } catch (e: SecurityException) {
                prefs.lastResult = "Health Connect permission was removed. Tap \"Allow Health Connect access\"."
            } catch (e: Exception) {
                prefs.lastResult = unreachable(server)
            } finally {
                syncing = false
                refreshUi()
            }
        }
    }

    private fun describe(r: org.json.JSONObject, reading: Reading): String {
        val time = DateFormat.getTimeInstance(DateFormat.SHORT).format(Date())
        val read = reading.counts.entries.joinToString(", ") { "${it.value} ${it.key}" }.ifEmpty { "nothing" }
        val metrics = r.optJSONArray("metrics")?.let { a -> (0 until a.length()).joinToString(", ") { a.getString(it).replace('_', ' ') } }
        val head = when (r.optString("status")) {
            "synced" -> "Synced at $time: ${r.optInt("readings_ingested")} new minutes added to your twin."
            "nothing_new" -> "Up to date at $time: no new readings since the last sync."
            "waiting_for_more_data" -> "Paired, but the twin needs more history to learn your normal (about a day of heart rate including rest). Wear your watch and sync again later."
            "no_heart_rate" -> "No heart-rate readings found in Health Connect. Make sure your watch app (Samsung Health, Fitbit, Google Fit…) shares heart rate with Health Connect."
            else -> "Server replied: ${r.optString("status")}"
        }
        return buildString {
            append(head)
            append("\n\nRead from Health Connect: ").append(read).append('.')
            if (!metrics.isNullOrEmpty()) append("\nVitals the twin is tracking: ").append(metrics).append('.')
        }
    }

    private fun unreachable(server: String) =
        "Can't reach the twin server at $server.\n• Phone and computer on the same Wi-Fi?\n• Server started with run.bat / run.sh?\n" +
            "• On Windows, allow Python through the firewall (Private networks)."

    // ------------------------------------------------------------------------ UI
    private fun refreshUi() {
        val paired = prefs.isPaired
        pairCard.visibility = if (paired) View.GONE else View.VISIBLE
        syncCard.visibility = if (paired) View.VISIBLE else View.GONE
        if (prefs.server != null && serverInput.text.isNullOrBlank()) serverInput.setText(prefs.server)

        statusText.text = if (paired) {
            "Paired with ${prefs.server}\nTwin: ${prefs.twinName ?: prefs.twinId}"
        } else {
            "Not paired. On the computer open the twin website → My data → Connect your Android phone."
        }

        healthText.text = when {
            healthClient == null && sdkStatus == HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED ->
                "Health Connect needs to be installed or updated. Tap the button below."
            healthClient == null -> "Health Connect isn't available on this phone."
            granted.isEmpty() -> "Health Connect: no access yet."
            else -> "Health Connect access: " + listOf(
                HealthReader.HEART_RATE to "heart rate",
                HealthReader.STEPS to "steps",
                HealthReader.SPO2 to "SpO₂",
                HealthReader.RESPIRATORY to "breathing rate",
                HealthReader.TEMPERATURE to "temperature",
                HealthReader.SLEEP to "sleep",
            ).joinToString(", ") { (perm, name) -> if (perm in granted) "✓ $name" else "✗ $name" }
        }
        permissionButton.text = if (granted.containsAll(HealthReader.PERMISSIONS)) "Manage Health Connect access" else "Allow Health Connect access"
        syncButton.isEnabled = paired && !syncing && HealthReader.HEART_RATE in granted
        if (!syncing) resultText.text = prefs.lastResult ?: if (paired) "Not synced yet." else ""
    }

    private fun buildLayout(): View {
        val pad = dp(20)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(18))
            background = rounded(Color.parseColor("#1D2B36"))
        }
        header.addView(text("Health Twin", 24f, bold = true, color = Color.WHITE))
        header.addView(text("Sends your phone's Health Connect data to your digital twin on the computer.", 14f, color = Color.parseColor("#D5DEE3")))
        root.addView(header)

        statusText = text("", 14f).also { root.addView(it, margins(top = 14)) }

        // Pairing
        pairCard = card()
        pairCard.addView(text("1  Pair with the website", 17f, bold = true))
        pairCard.addView(text("Scan the QR code shown on the computer, or type the address and code.", 13f, color = Color.parseColor("#5B6F7C")))
        pairCard.addView(button("Scan QR code", primary = true) {
            scanQr.launch(
                ScanOptions()
                    .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                    .setPrompt("Point at the QR code on the twin website")
                    .setBeepEnabled(false)
                    .setOrientationLocked(false)
            )
        }, margins(top = 10))
        serverInput = EditText(this).apply {
            hint = "Server, e.g. 192.168.1.20:8000"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
        }
        pairCard.addView(serverInput, margins(top = 8))
        codeInput = EditText(this).apply {
            hint = "6-digit code"
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine()
        }
        pairCard.addView(codeInput)
        pairCard.addView(button("Pair") { pair(serverInput.text.toString(), codeInput.text.toString()) })
        root.addView(pairCard, margins(top = 14))

        // Health Connect + sync
        syncCard = card()
        syncCard.addView(text("2  Share health data", 17f, bold = true))
        healthText = text("", 13f, color = Color.parseColor("#5B6F7C")).also { syncCard.addView(it, margins(top = 4)) }
        permissionButton = button("Allow Health Connect access") {
            if (granted.containsAll(HealthReader.PERMISSIONS)) openHealthConnectSettings() else askPermissions()
        }
        syncCard.addView(permissionButton, margins(top = 8))
        syncCard.addView(text("3  Sync", 17f, bold = true), margins(top = 14))
        syncButton = button("Sync now", primary = true) { syncNow(manual = true) }
        syncCard.addView(syncButton, margins(top = 6))
        resultText = text("", 14f).also { syncCard.addView(it, margins(top = 8)) }
        syncCard.addView(text("While this screen is open the app syncs every minute.", 12f, color = Color.parseColor("#5B6F7C")), margins(top = 8))
        syncCard.addView(button("Unpair this phone") { unpair() }, margins(top = 10))
        root.addView(syncCard, margins(top = 14))

        root.addView(
            text(
                "Wellness research prototype, not a medical device. Data goes only to the computer you paired with; " +
                    "only heart rate, steps, SpO₂, breathing rate, temperature and sleep are read.",
                12f,
                color = Color.parseColor("#5B6F7C"),
            ),
            margins(top = 16),
        )
        root.addView(button("Privacy details") { startActivity(Intent(this, PermissionsRationaleActivity::class.java)) })

        return ScrollView(this).apply { addView(root) }
    }

    // --------------------------------------------------------------- UI helpers
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun rounded(color: Int) = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(14).toFloat()
    }

    private fun card() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(16), dp(16), dp(16), dp(16))
        background = rounded(Color.WHITE)
    }

    private fun text(s: String, size: Float, bold: Boolean = false, color: Int = Color.parseColor("#1D2B36")) =
        TextView(this).apply {
            text = s
            textSize = size
            setTextColor(color)
            if (bold) typeface = Typeface.DEFAULT_BOLD
        }

    private fun button(label: String, primary: Boolean = false, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        gravity = Gravity.CENTER
        if (primary) {
            setTextColor(Color.WHITE)
            background = rounded(Color.parseColor("#0E7C7B"))
        }
        setOnClickListener { onClick() }
    }

    private fun margins(top: Int = 0) = LinearLayout.LayoutParams(
        LinearLayout.LayoutParams.MATCH_PARENT,
        LinearLayout.LayoutParams.WRAP_CONTENT,
    ).apply { topMargin = dp(top) }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()
}
