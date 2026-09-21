package com.voiceshieldapp.telecom

import java.security.MessageDigest

/**
 * Supported screening decisions for Android Telecom CallScreeningService.
 */
enum class ScreeningDecision {
    ALLOW,
    SILENCE,
    REJECT
}

/**
 * Caller security risk level determined solely from signaling/call metadata.
 * Note: Metadata risk is NOT voice-cloning detection.
 */
enum class RiskLevel {
    LOW,
    MEDIUM,
    HIGH
}

/**
 * Warning categories presented to the user via notification and dashboard.
 */
enum class WarningType {
    NONE,
    UNVERIFIED_CALLER,
    VERIFICATION_FAILED,
    RESTRICTED_NUMBER,
    BLOCKLIST_MATCH
}

/**
 * Evaluated screening result returned by CallScreeningEvaluator.
 * Contains no raw phone numbers.
 *
 * Fields:
 *  - decision: What to do with the call (ALLOW / SILENCE / REJECT)
 *  - riskLevel: Categorical severity (LOW / MEDIUM / HIGH)
 *  - riskState: UI-facing display state ("safe" / "low" / "suspicious" / "high" / "critical")
 *  - riskScore: Numeric 0–100 score for dashboard display
 *  - warningType: Specific warning category driving the risk level
 *  - maskedCaller: Privacy-masked display number (e.g. "+91 ***** *3210")
 *  - callerHash: SHA-256 of canonical number for idempotency
 *  - callerName: Display name from device contacts, null if not in contacts
 *  - contactStatus: "IN_CONTACTS" | "NOT_IN_CONTACTS" | "UNKNOWN"
 *  - reasonCodes: Machine-readable list of reason strings
 *  - explanation: Human-readable explanation of the evaluation outcome
 *  - timestamp: Epoch ms of the evaluation
 *  - screeningLatencyMs: Measured ms from onScreenCall to respondToCall
 */
data class EvaluationResult(
    val decision: ScreeningDecision,
    val riskLevel: RiskLevel,
    val riskState: String,         // "safe" | "low" | "suspicious" | "high" | "critical"
    val riskScore: Int,            // 0-100
    val warningType: WarningType,
    val maskedCaller: String,
    val callerHash: String,
    val callerName: String? = null,
    val contactStatus: String = "UNKNOWN",  // IN_CONTACTS | NOT_IN_CONTACTS | UNKNOWN
    val reasonCodes: List<String>,
    val explanation: String,
    val timestamp: Long,
    val screeningLatencyMs: Long = 0L
)

/**
 * Pure Kotlin deterministic metadata-only evaluator for incoming call screening.
 *
 * Implements strict privacy controls:
 * - Never logs or persists raw phone numbers.
 * - Masks phone numbers preserving country code and last 4 digits (e.g. +91 ***** *3210).
 * - Computes SHA-256 hash over canonical digits.
 * - Evaluator execution latency is < 0.1 ms on modern CPU without network or ML dependencies.
 *
 * Risk Classification Policy (Phase 3.1):
 *  - An unverified carrier STIR/SHAKEN status is a metadata signal, NOT proof of fraud.
 *  - Normal Indian cellular calls report NOT_VERIFIED because STIR/SHAKEN is not deployed.
 *  - A call from an unknown/unverified-carrier number with no other negative signals is LOW.
 *  - Only VERIFICATION_FAILED (active spoofing signal), BLOCKLIST_MATCH, or RESTRICTED
 *    presentation elevate risk above LOW for metadata-only Phase 3 screening.
 *
 * Note on Android Presentation Limitation:
 * Android CallScreeningService documentation states that calls with:
 * - PRESENTATION_RESTRICTED
 * - PRESENTATION_UNKNOWN
 * - PRESENTATION_UNAVAILABLE
 * - PRESENTATION_PAYPHONE
 * are NOT provided to CallScreeningService by Android Telecom in production.
 * The presentation handling in this evaluator is kept strictly as a defensive fallback
 * for testing, synthetic harnesses, and potential OEM-specific variations.
 * These presentation types are NOT claimed as production screening inputs.
 */
object CallScreeningEvaluator {

    // Telecom verification status constants (mirrors Call.Details on API 30+)
    const val VERIFICATION_STATUS_NOT_VERIFIED = 0
    const val VERIFICATION_STATUS_PASSED = 1
    const val VERIFICATION_STATUS_FAILED = 2
    const val VERIFICATION_STATUS_UNKNOWN = -1

    // Telecom presentation constants (mirrors Call.Details)
    const val PRESENTATION_ALLOWED = 1
    const val PRESENTATION_RESTRICTED = 2
    const val PRESENTATION_UNKNOWN = 3
    const val PRESENTATION_PAYPHONE = 4

    // Telecom direction constants
    const val DIRECTION_INCOMING = 0
    const val DIRECTION_OUTGOING = 1
    const val DIRECTION_UNKNOWN = -1

    /**
     * Normalizes raw handle URI or number string.
     * Strips "tel:", spaces, dashes, parentheses.
     * Retains leading '+' if present followed by digits.
     */
    fun canonicalize(rawHandle: String?): String {
        if (rawHandle.isNullOrBlank()) return ""
        var cleaned = rawHandle.trim()
        if (cleaned.startsWith("tel:", ignoreCase = true)) {
            cleaned = cleaned.substring(4).trim()
        }
        val hasPlus = cleaned.startsWith("+")
        val digitsOnly = cleaned.filter { it.isDigit() }
        return if (hasPlus) "+$digitsOnly" else digitsOnly
    }

    /**
     * Masks phone number to ensure no raw PII is logged or displayed.
     * Example: "+919876543210" -> "+91 ***** *3210"
     * Example: "9876543210" -> "***** *3210"
     */
    fun mask(canonicalNumber: String): String {
        if (canonicalNumber.isBlank()) return "Unknown Number"

        val hasPlus = canonicalNumber.startsWith("+")
        val digits = if (hasPlus) canonicalNumber.drop(1) else canonicalNumber

        return when {
            digits.length >= 10 -> {
                // If prefixed with country code (e.g. +91 10 digits)
                val countryCodeLen = if (hasPlus && digits.length > 10) digits.length - 10 else 0
                val countryCode = if (countryCodeLen > 0) "+${digits.take(countryCodeLen)} " else if (hasPlus) "+" else ""
                val nationalDigits = digits.drop(countryCodeLen)
                val last4 = nationalDigits.takeLast(4)
                "$countryCode***** *$last4"
            }
            digits.length in 5..9 -> {
                val last3 = digits.takeLast(3)
                "***$last3"
            }
            digits.length in 1..4 -> {
                val last1 = digits.takeLast(1)
                "***$last1"
            }
            else -> "Unknown Number"
        }
    }

    /**
     * Computes hex-encoded SHA-256 of canonical phone number.
     * Returns empty string if canonicalNumber is blank.
     */
    fun sha256(canonicalNumber: String): String {
        if (canonicalNumber.isBlank()) return ""
        val bytes = MessageDigest.getInstance("SHA-256").digest(canonicalNumber.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }

    /**
     * Evaluates incoming call metadata deterministically.
     *
     * @param rawHandle The raw caller handle string (e.g. "tel:+919876543210")
     * @param verificationStatus STIR/SHAKEN status (0=NOT_VERIFIED, 1=PASSED, 2=FAILED, -1=UNKNOWN)
     * @param callDirection Direction (0=INCOMING, 1=OUTGOING, -1=UNKNOWN)
     * @param presentation Caller ID presentation (1=ALLOWED, 2=RESTRICTED, 3=UNKNOWN, etc.)
     * @param timestamp Event epoch timestamp in milliseconds
     * @param localBlocklist Set of blocked SHA-256 hashes or canonical numbers
     * @param isContact Whether the caller is found in device contacts (requires READ_CONTACTS)
     * @param callerName Display name from contacts, null if not in contacts or permission absent
     */
    fun evaluate(
        rawHandle: String?,
        verificationStatus: Int = VERIFICATION_STATUS_UNKNOWN,
        callDirection: Int = DIRECTION_INCOMING,
        presentation: Int = PRESENTATION_ALLOWED,
        timestamp: Long = System.currentTimeMillis(),
        localBlocklist: Set<String> = emptySet(),
        isContact: Boolean = false,
        callerName: String? = null
    ): EvaluationResult {
        val canonical = canonicalize(rawHandle)
        val hash = sha256(canonical)
        val masked = when {
            presentation == PRESENTATION_RESTRICTED -> "Restricted Number"
            presentation == PRESENTATION_UNKNOWN && canonical.isBlank() -> "Private / Unknown"
            presentation == PRESENTATION_PAYPHONE -> "Payphone"
            canonical.isBlank() -> "Unknown Number"
            else -> mask(canonical)
        }

        val contactStatus = when {
            isContact -> "IN_CONTACTS"
            else -> if (canonical.isNotBlank()) "NOT_IN_CONTACTS" else "UNKNOWN"
        }

        val reasons = mutableListOf<String>()

        // 1. Check local explicit blocklist (highest priority)
        if (canonical.isNotEmpty() && (localBlocklist.contains(canonical) || (hash.isNotEmpty() && localBlocklist.contains(hash)))) {
            reasons.add("LOCAL_BLOCKLIST_MATCH")
            return EvaluationResult(
                decision = ScreeningDecision.REJECT,
                riskLevel = RiskLevel.HIGH,
                riskState = "critical",
                riskScore = 95,
                warningType = WarningType.BLOCKLIST_MATCH,
                maskedCaller = masked,
                callerHash = hash,
                callerName = callerName,
                contactStatus = contactStatus,
                reasonCodes = reasons,
                explanation = "Caller matches local security blocklist. Incoming call rejected.",
                timestamp = timestamp
            )
        }

        // 2. Known contact — LOW risk regardless of carrier verification status.
        //    Carrier STIR/SHAKEN does not sign personal calls in most markets.
        if (isContact) {
            reasons.add("KNOWN_CONTACT")
            return EvaluationResult(
                decision = ScreeningDecision.ALLOW,
                riskLevel = RiskLevel.LOW,
                riskState = "safe",
                riskScore = 0,
                warningType = WarningType.NONE,
                maskedCaller = masked,
                callerHash = hash,
                callerName = callerName,
                contactStatus = contactStatus,
                reasonCodes = reasons,
                explanation = "Known contact. Number is saved in device contacts. Low risk — no adverse caller-screening indicators were detected.",
                timestamp = timestamp
            )
        }

        // 3. Caller verification status (STIR/SHAKEN)
        when (verificationStatus) {
            VERIFICATION_STATUS_FAILED -> {
                // FAILED = active carrier spoofing signal. HIGH risk.
                reasons.add("CALLER_VERIFICATION_FAILED")
                return EvaluationResult(
                    decision = ScreeningDecision.ALLOW,
                    riskLevel = RiskLevel.HIGH,
                    riskState = "high",
                    riskScore = 75,
                    warningType = WarningType.VERIFICATION_FAILED,
                    maskedCaller = masked,
                    callerHash = hash,
                    callerName = callerName,
                    contactStatus = contactStatus,
                    reasonCodes = reasons,
                    explanation = "Carrier verification failed (possible number spoofing). Review caller before sharing sensitive information.",
                    timestamp = timestamp
                )
            }
            VERIFICATION_STATUS_PASSED -> {
                // Carrier-verified. LOW risk.
                reasons.add("CALLER_VERIFIED")
                return EvaluationResult(
                    decision = ScreeningDecision.ALLOW,
                    riskLevel = RiskLevel.LOW,
                    riskState = "safe",
                    riskScore = 0,
                    warningType = WarningType.NONE,
                    maskedCaller = masked,
                    callerHash = hash,
                    callerName = callerName,
                    contactStatus = contactStatus,
                    reasonCodes = reasons,
                    explanation = "Carrier verified caller identity (STIR/SHAKEN passed). Low risk — no adverse caller-screening indicators were detected.",
                    timestamp = timestamp
                )
            }
            VERIFICATION_STATUS_NOT_VERIFIED, VERIFICATION_STATUS_UNKNOWN -> {
                // NOT_VERIFIED is the default in India and most global markets where
                // STIR/SHAKEN is not deployed. It is a carrier metadata signal, NOT proof of fraud.
                // Restricted presentation is a separate, elevated signal.
                if (presentation == PRESENTATION_RESTRICTED) {
                    reasons.add("RESTRICTED_CALLER_ID")
                    return EvaluationResult(
                        decision = ScreeningDecision.ALLOW,
                        riskLevel = RiskLevel.MEDIUM,
                        riskState = "suspicious",
                        riskScore = 45,
                        warningType = WarningType.RESTRICTED_NUMBER,
                        maskedCaller = masked,
                        callerHash = hash,
                        callerName = callerName,
                        contactStatus = contactStatus,
                        reasonCodes = reasons,
                        explanation = "Incoming call from a private or restricted number. Caller intentionally hid their number.",
                        timestamp = timestamp
                    )
                }
                // Plain unverified caller: carrier doesn't sign calls in this market.
                // LOW risk — no negative indicators detected.
                reasons.add("CALLER_NOT_VERIFIED")
                return EvaluationResult(
                    decision = ScreeningDecision.ALLOW,
                    riskLevel = RiskLevel.LOW,
                    riskState = "low",
                    riskScore = 15,
                    warningType = WarningType.UNVERIFIED_CALLER,
                    maskedCaller = masked,
                    callerHash = hash,
                    callerName = callerName,
                    contactStatus = contactStatus,
                    reasonCodes = reasons,
                    explanation = "Caller identity could not be verified by carrier. Low risk — no adverse caller-screening indicators were detected. This is normal in markets where STIR/SHAKEN is not deployed.",
                    timestamp = timestamp
                )
            }
            else -> {
                // Unknown/null: default safe-allow
                reasons.add("DEFAULT_ALLOW")
                return EvaluationResult(
                    decision = ScreeningDecision.ALLOW,
                    riskLevel = RiskLevel.LOW,
                    riskState = "low",
                    riskScore = 10,
                    warningType = WarningType.NONE,
                    maskedCaller = masked,
                    callerHash = hash,
                    callerName = callerName,
                    contactStatus = contactStatus,
                    reasonCodes = reasons,
                    explanation = "No adverse caller-screening indicators were detected. Low risk.",
                    timestamp = timestamp
                )
            }
        }
    }
}
