package com.voiceshieldapp.telecom

import android.os.Build
import android.telecom.Call
import android.telecom.CallScreeningService

/**
 * Android Telecom CallScreeningService for VoiceShield.
 *
 * Implements strict non-negotiable critical path:
 * 1. Extract supported metadata.
 * 2. Load local blocklist (< 1 ms).
 * 3. Run local deterministic CallScreeningEvaluator (< 0.1 ms on CPU).
 * 4. Construct CallResponse.
 * 5. Bounded local persistence BEFORE respondToCall to mitigate event loss before service unbind.
 * 6. Respond to Telecom via respondToCall() within Android's 5-second requirement.
 * 7. Post-screening non-critical tasks (native heads-up notification, RN event dispatch).
 *
 * Note on Android Presentation Limitation:
 * Calls with PRESENTATION_RESTRICTED, PRESENTATION_UNKNOWN, PRESENTATION_UNAVAILABLE,
 * or PRESENTATION_PAYPHONE are not provided to CallScreeningService by Android Telecom
 * in production. Presentation handling is purely defensive fallback for testing/OEM variations.
 *
 * Operates without React Native, Metro, network, or ML inference on the critical path.
 * The measured local operations are bounded to approximately 1.5–3 ms in the available in-process
 * benchmark, leaving substantial margin relative to Android Telecom's 5-second screening requirement.
 * End-to-end Telecom framework latency has not yet been measured on physical hardware.
 */
class VoiceShieldCallScreeningService : CallScreeningService() {

    override fun onScreenCall(callDetails: Call.Details) {
        val startTime = System.currentTimeMillis()

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

        // 2. Load local blocklist (< 1 ms)
        val storage = CallScreeningStorage(applicationContext)
        val blocklist = try {
            storage.getBlocklist()
        } catch (e: Exception) {
            emptySet()
        }

        // 3. Run local deterministic evaluation (< 0.1 ms)
        val evaluation = CallScreeningEvaluator.evaluate(
            rawHandle = rawHandle,
            verificationStatus = verificationStatus,
            callDirection = callDirection,
            presentation = presentation,
            timestamp = creationTime,
            localBlocklist = blocklist
        )

        // 4. Construct CallResponse
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

        // 5. LOCAL PERSISTENCE: Bounded local persistence BEFORE respondToCall().
        // If persisted AFTER respondToCall(), Android Telecom may immediately unbind/terminate
        // the screening service process, causing dropped/lost event records.
        // The measured local operations are bounded to approximately 1.5–3 ms
        // in the available in-process benchmark, leaving substantial margin
        // relative to Android Telecom's 5-second screening requirement.
        // End-to-end Telecom framework latency has not yet been measured on
        // physical hardware.
        // Wrapped in try/catch so any storage failure never blocks or prevents respondToCall().
        val verificationStatusStr = when (verificationStatus) {
            CallScreeningEvaluator.VERIFICATION_STATUS_PASSED -> "PASSED"
            CallScreeningEvaluator.VERIFICATION_STATUS_FAILED -> "FAILED"
            CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED -> "NOT_VERIFIED"
            else -> "UNKNOWN"
        }

        val record: ScreenedCallRecord? = try {
            storage.saveEvent(evaluation, verificationStatusStr)
        } catch (e: Exception) {
            null
        }

        // 6. CRITICAL: respondToCall() to Android Telecom within 5-second deadline
        try {
            respondToCall(callDetails, callResponse)
        } catch (e: Exception) {
            // Telecom response failure is unrecoverable, abort
            return
        }

        // 7. Post-screening non-critical: trigger native heads-up notification
        try {
            CallNotificationHelper.showScreeningNotification(applicationContext, evaluation)
        } catch (e: Exception) {
            // Non-critical
        }

        // 8. Post-screening non-critical: dispatch event to React Native if bridge is active
        if (record != null) {
            try {
                VoiceShieldCallScreeningModule.notifyCallScreened(record)
            } catch (e: Exception) {
                // Bridge inactive or in background, safe to ignore
            }
        }
    }
}
