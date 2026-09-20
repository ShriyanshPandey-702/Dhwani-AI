package com.voiceshieldapp.telecom

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Persisted record of a screened call event.
 * Contains strictly masked and hashed caller data, no raw phone numbers.
 */
data class ScreenedCallRecord(
    val eventId: String,
    val timestamp: Long,
    val callerMasked: String,
    val callerHash: String,
    val verificationStatus: String,
    val decision: String,
    val riskLevel: String,
    val warningType: String,
    val reasonCodes: List<String>
) {
    fun toJsonObject(): JSONObject {
        return JSONObject().apply {
            put("eventId", eventId)
            put("timestamp", timestamp)
            put("callerMasked", callerMasked)
            put("callerHash", callerHash)
            put("verificationStatus", verificationStatus)
            put("decision", decision)
            put("riskLevel", riskLevel)
            put("warningType", warningType)
            val reasonsArray = JSONArray()
            reasonCodes.forEach { reasonsArray.put(it) }
            put("reasonCodes", reasonsArray)
        }
    }

    companion object {
        fun fromJsonObject(json: JSONObject): ScreenedCallRecord {
            val reasonsList = mutableListOf<String>()
            val reasonsArray = json.optJSONArray("reasonCodes")
            if (reasonsArray != null) {
                for (i in 0 until reasonsArray.length()) {
                    reasonsList.add(reasonsArray.getString(i))
                }
            }
            return ScreenedCallRecord(
                eventId = json.optString("eventId", UUID.randomUUID().toString()),
                timestamp = json.optLong("timestamp", System.currentTimeMillis()),
                callerMasked = json.optString("callerMasked", "Unknown Number"),
                callerHash = json.optString("callerHash", ""),
                verificationStatus = json.optString("verificationStatus", "UNKNOWN"),
                decision = json.optString("decision", "ALLOW"),
                riskLevel = json.optString("riskLevel", "LOW"),
                warningType = json.optString("warningType", "NONE"),
                reasonCodes = reasonsList
            )
        }
    }
}

/**
 * Lightweight native SharedPreferences storage for call screening events and settings.
 *
 * Keeps history bounded to a maximum of 50 recent events to prevent unbounded growth.
 */
class CallScreeningStorage(context: Context) {

    companion object {
        private const val PREFS_NAME = "voiceshield_call_screening_prefs"
        private const val KEY_RECENT_EVENTS = "recent_screened_calls"
        private const val KEY_BLOCKLIST = "local_call_blocklist"
        private const val MAX_HISTORY_EVENTS = 50
    }

    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /**
     * Persists an evaluated screening event to local storage.
     * Inserts at the head of the list and trims to MAX_HISTORY_EVENTS.
     */
    @Synchronized
    fun saveEvent(evaluation: EvaluationResult, verificationStatusString: String): ScreenedCallRecord {
        val record = ScreenedCallRecord(
            eventId = UUID.randomUUID().toString(),
            timestamp = evaluation.timestamp,
            callerMasked = evaluation.maskedCaller,
            callerHash = evaluation.callerHash,
            verificationStatus = verificationStatusString,
            decision = evaluation.decision.name,
            riskLevel = evaluation.riskLevel.name,
            warningType = evaluation.warningType.name,
            reasonCodes = evaluation.reasonCodes
        )

        val existing = getRecentEvents().toMutableList()
        existing.add(0, record)
        if (existing.size > MAX_HISTORY_EVENTS) {
            existing.subList(MAX_HISTORY_EVENTS, existing.size).clear()
        }

        val jsonArray = JSONArray()
        existing.forEach { jsonArray.put(it.toJsonObject()) }

        // Use commit() for synchronous write to flash storage
        // to mitigate event loss before respondToCall() triggers service unbind.
        prefs.edit().putString(KEY_RECENT_EVENTS, jsonArray.toString()).commit()
        return record
    }

    /**
     * Retrieves all saved screening events in reverse chronological order.
     */
    @Synchronized
    fun getRecentEvents(): List<ScreenedCallRecord> {
        val jsonStr = prefs.getString(KEY_RECENT_EVENTS, null) ?: return emptyList()
        val results = mutableListOf<ScreenedCallRecord>()
        try {
            val jsonArray = JSONArray(jsonStr)
            for (i in 0 until jsonArray.length()) {
                val obj = jsonArray.getJSONObject(i)
                results.add(ScreenedCallRecord.fromJsonObject(obj))
            }
        } catch (e: Exception) {
            // Ignore parse errors, return current collected
        }
        return results
    }

    /**
     * Clears all persisted screening history.
     */
    @Synchronized
    fun clearEvents() {
        prefs.edit().remove(KEY_RECENT_EVENTS).apply()
    }

    /**
     * Gets the configured local blocklist (hashes or canonical numbers).
     */
    @Synchronized
    fun getBlocklist(): Set<String> {
        return prefs.getStringSet(KEY_BLOCKLIST, emptySet()) ?: emptySet()
    }

    /**
     * Adds a phone hash or canonical number to local blocklist.
     */
    @Synchronized
    fun addToBlocklist(identifier: String) {
        val current = getBlocklist().toMutableSet()
        current.add(identifier)
        prefs.edit().putStringSet(KEY_BLOCKLIST, current).apply()
    }

    /**
     * Removes an identifier from local blocklist.
     */
    @Synchronized
    fun removeFromBlocklist(identifier: String) {
        val current = getBlocklist().toMutableSet()
        current.remove(identifier)
        prefs.edit().putStringSet(KEY_BLOCKLIST, current).apply()
    }
}
