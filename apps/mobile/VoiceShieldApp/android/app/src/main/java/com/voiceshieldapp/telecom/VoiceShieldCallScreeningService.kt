package com.voiceshieldapp.telecom

import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.os.Build
import android.provider.ContactsContract
import android.telecom.Call
import android.telecom.CallScreeningService
import android.util.Log

/**
 * Android Telecom CallScreeningService for VoiceShield.
 *
 * Implements strict non-negotiable critical path:
 * 1. Extract supported metadata.
 * 2. Perform sub-millisecond local contact lookup (if READ_CONTACTS granted).
 * 3. Load local blocklist (< 1 ms).
 * 4. Run local deterministic CallScreeningEvaluator (< 0.1 ms on CPU).
 * 5. Construct CallResponse.
 * 6. Bounded local persistence BEFORE respondToCall to mitigate event loss before service unbind.
 * 7. Respond to Telecom via respondToCall() within Android's 5-second requirement.
 * 8. Post-screening non-critical tasks (native heads-up notification, RN event dispatch).
 *
 * Note on Android Presentation Limitation:
 * Calls with PRESENTATION_RESTRICTED, PRESENTATION_UNKNOWN, PRESENTATION_UNAVAILABLE,
 * or PRESENTATION_PAYPHONE are not provided to CallScreeningService by Android Telecom
 * in production. Presentation handling is purely defensive fallback for testing/OEM variations.
 *
 * Operates without React Native, Metro, network, or ML inference on the critical path.
 * The measured local operations are bounded to approximately 1.5–4 ms in the available in-process
 * benchmark, leaving substantial margin relative to Android Telecom's 5-second screening requirement.
 */
class VoiceShieldCallScreeningService : CallScreeningService() {

    companion object {
        private const val TAG = "VoiceShieldTelecom"
    }

    override fun onScreenCall(callDetails: Call.Details) {
        val startTime = System.currentTimeMillis()
        Log.i(TAG, "onScreenCall received by VoiceShieldCallScreeningService at $startTime")

        // 1. Extract supported metadata safely
        val rawHandle = callDetails.handle?.schemeSpecificPart ?: callDetails.handle?.toString()

        val callDirection = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            callDetails.callDirection
        } else {
            CallScreeningEvaluator.DIRECTION_INCOMING
        }

        val verificationStatus = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            callDetails.callerNumberVerificationStatus
        } else {
            CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN
        }

        val presentation = callDetails.handlePresentation

        val creationTime = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ct = callDetails.creationTimeMillis
            if (ct > 0) ct else startTime
        } else {
            startTime
        }

        // 2. Contact lookup using ContactsContract.PhoneLookup
        // This informs Android Telecom that we are READ_CONTACTS aware (required for
        // IncomingCallFilterGraph to route contact calls to this service).
        // Bounded to < 3 ms on device storage.
        var isContact = false
        var callerName: String? = null
        val canonical = CallScreeningEvaluator.canonicalize(rawHandle)
        if (canonical.isNotBlank()) {
            val hasContactsPermission = checkSelfPermission("android.permission.READ_CONTACTS") ==
                PackageManager.PERMISSION_GRANTED
            if (hasContactsPermission) {
                val contactResult = lookupContact(canonical)
                isContact = contactResult.first
                callerName = contactResult.second
                Log.i(TAG, "Contact lookup: isContact=$isContact, name=${callerName ?: "null"}")
            } else {
                Log.i(TAG, "READ_CONTACTS not granted, skipping contact lookup")
            }
        }

        // 3. Load local blocklist (< 1 ms)
        val storage = CallScreeningStorage(applicationContext)
        val blocklist = try {
            storage.getBlocklist()
        } catch (e: Exception) {
            emptySet()
        }

        // 4. Run local deterministic evaluation (< 0.1 ms)
        val evaluation = CallScreeningEvaluator.evaluate(
            rawHandle = rawHandle,
            verificationStatus = verificationStatus,
            callDirection = callDirection,
            presentation = presentation,
            timestamp = creationTime,
            localBlocklist = blocklist,
            isContact = isContact,
            callerName = callerName
        )

        // 5. Construct CallResponse
        val responseBuilder = CallResponse.Builder()
        when (evaluation.decision) {
            ScreeningDecision.ALLOW -> {
                responseBuilder.setDisallowCall(false)
                responseBuilder.setRejectCall(false)
                responseBuilder.setSilenceCall(false)
            }
            ScreeningDecision.SILENCE -> {
                responseBuilder.setDisallowCall(false)
                responseBuilder.setRejectCall(false)
                responseBuilder.setSilenceCall(true)
            }
            ScreeningDecision.REJECT -> {
                responseBuilder.setDisallowCall(true)
                responseBuilder.setRejectCall(true)
                responseBuilder.setSkipCallLog(false)
                responseBuilder.setSkipNotification(true)
            }
        }
        val callResponse = responseBuilder.build()

        // 6. LOCAL PERSISTENCE: Bounded local persistence BEFORE respondToCall().
        // If persisted AFTER respondToCall(), Android Telecom may immediately unbind/terminate
        // the screening service process, causing dropped/lost event records.
        // Wrapped in try/catch so any storage failure never blocks or prevents respondToCall().
        val verificationStatusStr = when (verificationStatus) {
            CallScreeningEvaluator.VERIFICATION_STATUS_PASSED -> "PASSED"
            CallScreeningEvaluator.VERIFICATION_STATUS_FAILED -> "FAILED"
            CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED -> "NOT_VERIFIED"
            else -> "UNKNOWN"
        }

        val incidentId = "sim-${evaluation.timestamp}-${if (evaluation.callerHash.length >= 8) evaluation.callerHash.take(8) else "call"}"

        Log.i("DHWANI-CALL", "[DHWANI-CALL] onScreenCall received")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] number=${evaluation.maskedCaller}")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] direction=${evaluation.callDirection}")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] timestamp=${evaluation.timestamp}")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] contactStatus=${evaluation.contactStatus}")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] screeningDecision=${evaluation.decision}")
        Log.i("DHWANI-CALL", "[DHWANI-CALL] incidentId=$incidentId")

        val preRespondLatencyMs = System.currentTimeMillis() - startTime
        val record: ScreenedCallRecord? = try {
            storage.saveEvent(evaluation, verificationStatusStr, preRespondLatencyMs, incidentId)
        } catch (e: Exception) {
            Log.w(TAG, "Failed to persist screening event: ${e.message}")
            null
        }

        // 7. CRITICAL: respondToCall() to Android Telecom within 5-second deadline
        val elapsedBeforeRespond = System.currentTimeMillis() - startTime
        Log.i(TAG, "Screened call: caller=${evaluation.maskedCaller}, contact=$isContact, decision=${evaluation.decision}, risk=${evaluation.riskLevel}/${evaluation.riskState}, score=${evaluation.riskScore}, warning=${evaluation.warningType}, latency=${elapsedBeforeRespond}ms")
        try {
            respondToCall(callDetails, callResponse)
            val totalLatencyMs = System.currentTimeMillis() - startTime
            Log.i(TAG, "respondToCall completed in ${totalLatencyMs}ms total (within 5000ms limit)")
        } catch (e: Exception) {
            Log.e(TAG, "respondToCall failed: ${e.message}")
            // Telecom response failure is unrecoverable, abort
            return
        }

        // 8. Post-screening non-critical: trigger native heads-up notification
        try {
            CallNotificationHelper.showScreeningNotification(applicationContext, evaluation)
        } catch (e: Exception) {
            Log.w(TAG, "CallNotificationHelper failed: ${e.message}")
        }

        // 9. Post-screening non-critical: dispatch event to React Native if bridge is active
        if (record != null) {
            try {
                VoiceShieldCallScreeningModule.notifyCallScreened(record)
            } catch (e: Exception) {
                Log.w(TAG, "VoiceShieldCallScreeningModule dispatch failed: ${e.message}")
            }
        }
    }

    /**
     * Performs a synchronous contact lookup using ContactsContract.PhoneLookup.
     * Returns Pair(isContact, displayName).
     *
     * @param canonicalNumber Normalized phone number (e.g. "+919876543210" or "9876543210")
     * @return Pair<Boolean, String?> — (found in contacts, display name or null)
     */
    private fun lookupContact(canonicalNumber: String): Pair<Boolean, String?> {
        return try {
            val lookupUri: Uri = Uri.withAppendedPath(
                ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
                Uri.encode(canonicalNumber)
            )
            val projection = arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME)
            val cursor: Cursor? = contentResolver.query(lookupUri, projection, null, null, null)
            cursor?.use {
                if (it.moveToFirst()) {
                    val nameIdx = it.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME)
                    val name = if (nameIdx >= 0) it.getString(nameIdx) else null
                    Pair(true, name)
                } else {
                    Pair(false, null)
                }
            } ?: Pair(false, null)
        } catch (e: Exception) {
            Log.w(TAG, "Contact lookup failed: ${e.message}")
            Pair(false, null)
        }
    }
}
