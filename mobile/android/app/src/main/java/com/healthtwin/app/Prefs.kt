package com.healthtwin.app

import android.content.Context

/** Pairing details kept on the phone. The token is the only secret; the server stores just its hash. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("health_twin", Context.MODE_PRIVATE)

    var server: String?
        get() = sp.getString("server", null)
        set(value) = sp.edit().putString("server", value).apply()

    var token: String?
        get() = sp.getString("token", null)
        set(value) = sp.edit().putString("token", value).apply()

    var twinId: String?
        get() = sp.getString("twin_id", null)
        set(value) = sp.edit().putString("twin_id", value).apply()

    var twinName: String?
        get() = sp.getString("twin_name", null)
        set(value) = sp.edit().putString("twin_name", value).apply()

    /** End of the last window the server accepted (epoch ms); the next sync starts a little before it. */
    var lastSyncEnd: Long?
        get() = if (sp.contains("last_sync_end")) sp.getLong("last_sync_end", 0L) else null
        set(value) {
            if (value == null) sp.edit().remove("last_sync_end").apply()
            else sp.edit().putLong("last_sync_end", value).apply()
        }

    var lastResult: String?
        get() = sp.getString("last_result", null)
        set(value) = sp.edit().putString("last_result", value).apply()

    val isPaired: Boolean
        get() = !server.isNullOrBlank() && !token.isNullOrBlank()

    fun clearPairing() {
        sp.edit()
            .remove("token")
            .remove("twin_id")
            .remove("twin_name")
            .remove("last_sync_end")
            .remove("last_result")
            .apply()
    }
}
