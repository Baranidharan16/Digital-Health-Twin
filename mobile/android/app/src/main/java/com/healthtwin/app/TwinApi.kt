package com.healthtwin.app

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class TwinApiException(val code: Int, message: String) : IOException(message)

/** Tiny HTTP client for the twin server (plain HttpURLConnection, no extra libraries). Call off the main thread. */
object TwinApi {

    fun claim(server: String, code: String, deviceName: String): JSONObject =
        post(
            "$server/api/devices/claim",
            JSONObject().put("code", code).put("device_name", deviceName.take(80)),
            token = null,
        )

    fun sync(server: String, token: String, body: JSONObject): JSONObject =
        post("$server/api/devices/sync", body, token)

    private fun post(url: String, body: JSONObject, token: String?): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 10_000
            conn.readTimeout = 180_000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.setRequestProperty("Accept", "application/json")
            if (token != null) conn.setRequestProperty("Authorization", "Bearer $token")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }

            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (code !in 200..299) {
                val detail = runCatching { JSONObject(text).opt("detail")?.toString() }.getOrNull()
                throw TwinApiException(code, detail ?: "HTTP $code")
            }
            return JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }
}
