package com.healthtwin.app

import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/** Privacy explanation. Health Connect opens this from its permission screen. */
class PermissionsRationaleActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (20 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        root.addView(TextView(this).apply {
            text = "How Health Twin uses your data"
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(Color.parseColor("#1D2B36"))
        })
        root.addView(TextView(this).apply {
            textSize = 15f
            setTextColor(Color.parseColor("#1D2B36"))
            setPadding(0, pad / 2, 0, pad / 2)
            text = """
                What is read (read-only): heart rate, steps, blood-oxygen saturation (SpO₂), respiratory rate, body temperature and sleep sessions from Health Connect. The app never writes to Health Connect.

                Where it goes: only to the Health Twin server you paired with by scanning its code, normally your own computer on the same Wi-Fi. Nothing is sent to the app's developers or any third party, and there are no ads or analytics.

                What it is for: building a personal "digital twin" that learns your usual ranges and shows changes and what-if scenarios. It is a wellness research prototype, not a medical device, and it does not diagnose or treat anything.

                How much: the first sync sends the last 7 days; later syncs send only new readings. Heart rate, SpO₂, breathing and temperature are averaged per minute on the phone.

                Your control: remove access any time in Health Connect, tap "Unpair this phone" in the app, or press "Disconnect" / "Delete data" on the website to erase everything stored on the computer.
            """.trimIndent()
        })
        root.addView(Button(this).apply {
            text = "Close"
            isAllCaps = false
            setOnClickListener { finish() }
        })
        setContentView(ScrollView(this).apply { addView(root) })
    }
}
