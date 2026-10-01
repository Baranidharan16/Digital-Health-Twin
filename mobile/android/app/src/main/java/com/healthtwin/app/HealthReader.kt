package com.healthtwin.app

import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.BodyTemperatureRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.reflect.KClass

/** What one read produced: the JSON body for POST /api/devices/sync and per-type counts for the screen. */
class Reading(val body: JSONObject, val counts: Map<String, Int>)

/**
 * Reads Health Connect and shapes it for the twin server.
 *
 * Heart rate, SpO2, breathing rate and temperature are averaged per minute on
 * the phone (watches can write one heart-rate sample per second during a
 * workout); steps and sleep are sent as the intervals Health Connect stores.
 * Types the user did not allow are skipped, and nothing is ever made up.
 */
class HealthReader(private val client: HealthConnectClient) {

    companion object {
        val HEART_RATE = HealthPermission.getReadPermission(HeartRateRecord::class)
        val STEPS = HealthPermission.getReadPermission(StepsRecord::class)
        val SPO2 = HealthPermission.getReadPermission(OxygenSaturationRecord::class)
        val RESPIRATORY = HealthPermission.getReadPermission(RespiratoryRateRecord::class)
        val TEMPERATURE = HealthPermission.getReadPermission(BodyTemperatureRecord::class)
        val SLEEP = HealthPermission.getReadPermission(SleepSessionRecord::class)

        val PERMISSIONS: Set<String> = setOf(HEART_RATE, STEPS, SPO2, RESPIRATORY, TEMPERATURE, SLEEP)

        private const val MAX_RECORDS_PER_TYPE = 400_000
    }

    suspend fun grantedPermissions(): Set<String> = client.permissionController.getGrantedPermissions()

    suspend fun read(start: Instant, end: Instant, granted: Set<String>, utcOffsetHours: Double): Reading {
        val counts = linkedMapOf<String, Int>()

        val heart = MinuteAverage()
        if (HEART_RATE in granted) {
            val records = readAll(HeartRateRecord::class, start, end)
            for (r in records) for (s in r.samples) {
                val bpm = s.beatsPerMinute.toDouble()
                if (bpm in 20.0..250.0 && !s.time.isBefore(start) && s.time.isBefore(end)) heart.add(s.time, bpm)
            }
            counts["heart rate"] = records.sumOf { it.samples.size }
        }

        val steps = JSONArray()
        if (STEPS in granted) {
            val records = readAll(StepsRecord::class, start, end)
            for (r in records) {
                if (!r.endTime.isAfter(r.startTime)) continue
                steps.put(
                    JSONObject()
                        .put("start", r.startTime.toString())
                        .put("end", r.endTime.toString())
                        .put("count", r.count.coerceIn(0L, 100_000L))
                )
            }
            counts["steps"] = records.sumOf { it.count }.toInt()
        }

        val spo2 = MinuteAverage()
        if (SPO2 in granted) {
            val records = readAll(OxygenSaturationRecord::class, start, end)
            for (r in records) {
                val pct = r.percentage.value
                if (pct in 50.0..100.0) spo2.add(r.time, pct)
            }
            counts["SpO₂"] = records.size
        }

        val breathing = MinuteAverage()
        if (RESPIRATORY in granted) {
            val records = readAll(RespiratoryRateRecord::class, start, end)
            for (r in records) if (r.rate in 3.0..70.0) breathing.add(r.time, r.rate)
            counts["breathing rate"] = records.size
        }

        val temperature = MinuteAverage()
        if (TEMPERATURE in granted) {
            val records = readAll(BodyTemperatureRecord::class, start, end)
            for (r in records) {
                val c = r.temperature.inCelsius
                if (c in 30.0..43.0) temperature.add(r.time, c)
            }
            counts["temperature"] = records.size
        }

        val sleep = JSONArray()
        if (SLEEP in granted) {
            val records = readAll(SleepSessionRecord::class, start, end)
            for (r in records) {
                if (!r.endTime.isAfter(r.startTime)) continue
                sleep.put(JSONObject().put("start", r.startTime.toString()).put("end", r.endTime.toString()))
            }
            counts["sleep sessions"] = records.size
        }

        val body = JSONObject()
            .put("utc_offset_hours", utcOffsetHours)
            .put("window_start", start.toString())
            .put("window_end", end.toString())
            .put("heart_rate", heart.toJson("bpm"))
            .put("steps", steps)
            .put("spo2", spo2.toJson("pct"))
            .put("respiratory_rate", breathing.toJson("rate"))
            .put("temperature", temperature.toJson("celsius"))
            .put("sleep", sleep)
        return Reading(body, counts)
    }

    /** Reads every record of one type in the window, following Health Connect's page tokens. */
    private suspend fun <T : Record> readAll(type: KClass<T>, start: Instant, end: Instant): List<T> {
        val out = ArrayList<T>()
        var pageToken: String? = null
        do {
            val response = client.readRecords(
                ReadRecordsRequest(
                    recordType = type,
                    timeRangeFilter = TimeRangeFilter.between(start, end),
                    pageSize = 5000,
                    pageToken = pageToken,
                )
            )
            out.addAll(response.records)
            pageToken = response.pageToken
        } while (pageToken != null && out.size < MAX_RECORDS_PER_TYPE)
        return out
    }
}

/** Per-minute mean of a vital, keyed by the UTC minute. */
private class MinuteAverage {
    private val sum = HashMap<Long, Double>()
    private val n = HashMap<Long, Int>()

    fun add(t: Instant, value: Double) {
        val minute = Math.floorDiv(t.epochSecond, 60L)
        sum[minute] = (sum[minute] ?: 0.0) + value
        n[minute] = (n[minute] ?: 0) + 1
    }

    fun toJson(field: String): JSONArray {
        val out = JSONArray()
        for (minute in sum.keys.sorted()) {
            val mean = sum.getValue(minute) / n.getValue(minute)
            out.put(
                JSONObject()
                    .put("t", Instant.ofEpochSecond(minute * 60L).toString())
                    .put(field, Math.round(mean * 10.0) / 10.0)
            )
        }
        return out
    }
}
