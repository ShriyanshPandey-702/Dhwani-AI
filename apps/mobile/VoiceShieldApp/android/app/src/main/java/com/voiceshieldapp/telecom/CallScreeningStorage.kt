package com.voiceshieldapp.telecom

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

/**
 * Persisted record of a screened call event.
 * Contains strictly masked and hashed caller data, no raw phone numbers.
 *
 * Expanded in Phase 3.1 to include: riskScore, riskState, callerName, contactStatus,
 * screeningLatencyMs, explanation, category, source, audioAnalysisStatus.
 * Backwards-compatible deserialization: older records without new fields get safe defaults.
 */
data class ScreenedCallRecord(
    val eventId: String,
    val timestamp: Long,
    val callerMasked: String,
    val callerName: String? = null,
    val callerHash: String,
    val contactStatus: String = "NOT_IN_CONTACTS",   // IN_CONTACTS | NOT_IN_CONTACTS | UNKNOWN
    val verificationStatus: String,
    val riskScore: Int = 0,
    val riskState: String = "low",                   // safe | low | suspicious | high | critical
    val decision: String,                             // ALLOW | SILENCE | REJECT
    val riskLevel: String,                            // LOW | MEDIUM | HIGH
    val warningType: String,                          // NONE | UNVERIFIED_CALLER | ...
    val category: String = "SIM Call",
    val explanation: String = "",
    val reasonCodes: List<String>,
    val screeningLatencyMs: Long = 0L,
    val source: String = "SIM_CALL",
    val audioAnalysisStatus: String = "NOT_PERFORMED",
    val callDirection: String = "INCOMING"            // INCOMING | OUTGOING
) {
    fun toJsonObject(): JSONObject {
        return JSONObject().apply {
            put("eventId", eventId)
            put("timestamp", timestamp)
            put("callerMasked", callerMasked)
            if (callerName != null) put("callerName", callerName) else put("callerName", JSONObject.NULL)
            put("callerHash", callerHash)
            put("contactStatus", contactStatus)
            put("verificationStatus", verificationStatus)
            put("riskScore", riskScore)
            put("riskState", riskState)
            put("decision", decision)
            put("riskLevel", riskLevel)
            put("warningType", warningType)
            put("category", category)
            put("explanation", explanation)
            val reasonsArray = JSONArray()
            reasonCodes.forEach { reasonsArray.put(it) }
            put("reasonCodes", reasonsArray)
            put("screeningLatencyMs", screeningLatencyMs)
            put("source", source)
            put("audioAnalysisStatus", audioAnalysisStatus)
            put("callDirection", callDirection)
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
            // callerName is stored as JSONObject.NULL when absent; handle both null and absent
            val callerNameRaw = json.opt("callerName")
            val callerName = if (callerNameRaw != null && callerNameRaw != JSONObject.NULL) {
                callerNameRaw.toString()
            } else null

            return ScreenedCallRecord(
                eventId = json.optString("eventId", UUID.randomUUID().toString()),
                timestamp = json.optLong("timestamp", System.currentTimeMillis()),
                callerMasked = json.optString("callerMasked", "Unknown Number"),
                callerName = callerName,
                callerHash = json.optString("callerHash", ""),
                contactStatus = json.optString("contactStatus", "NOT_IN_CONTACTS"),
                verificationStatus = json.optString("verificationStatus", "UNKNOWN"),
                riskScore = json.optInt("riskScore", 0),
                riskState = json.optString("riskState", "low"),
                decision = json.optString("decision", "ALLOW"),
                riskLevel = json.optString("riskLevel", "LOW"),
                warningType = json.optString("warningType", "NONE"),
                category = json.optString("category", "SIM Call"),
                explanation = json.optString("explanation", ""),
                reasonCodes = reasonsList,
                screeningLatencyMs = json.optLong("screeningLatencyMs", 0L),
                source = json.optString("source", "SIM_CALL"),
                audioAnalysisStatus = json.optString("audioAnalysisStatus", "NOT_PERFORMED"),
                callDirection = json.optString("callDirection", "INCOMING")
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
     *
     * Must be called BEFORE respondToCall() to avoid event loss on service unbind.
     */
    @Synchronized
    fun saveEvent(
        evaluation: EvaluationResult,
        verificationStatusString: String,
        screeningLatencyMs: Long = 0L
    ): ScreenedCallRecord {
        val record = ScreenedCallRecord(
            eventId = UUID.randomUUID().toString(),
            timestamp = evaluation.timestamp,
            callerMasked = evaluation.maskedCaller,
            callerName = evaluation.callerName,
            callerHash = evaluation.callerHash,
            contactStatus = evaluation.contactStatus,
            verificationStatus = verificationStatusString,
            riskScore = evaluation.riskScore,
            riskState = evaluation.riskState,
            decision = evaluation.decision.name,
            riskLevel = evaluation.riskLevel.name,
            warningType = evaluation.warningType.name,
            category = "SIM Call",
            explanation = evaluation.explanation,
            reasonCodes = evaluation.reasonCodes,
            screeningLatencyMs = screeningLatencyMs,
            source = "SIM_CALL",
            audioAnalysisStatus = "NOT_PERFORMED",
            callDirection = evaluation.callDirection
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
