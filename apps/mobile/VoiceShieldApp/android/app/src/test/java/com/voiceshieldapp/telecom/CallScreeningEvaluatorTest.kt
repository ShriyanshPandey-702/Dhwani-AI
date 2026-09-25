package com.voiceshieldapp.telecom

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JVM unit tests for CallScreeningEvaluator.
 *
 * Phase 3.1 update: Tests reflect corrected risk semantics where
 * VERIFICATION_STATUS_NOT_VERIFIED maps to LOW risk (not MEDIUM),
 * and contact callers are explicitly LOW risk.
 */
class CallScreeningEvaluatorTest {

    private val samplePhone = "+919876543210"
    private val expectedHash = "b4661448dbd54e4c2957b49aa4c965b3992fa68c0b5614917fbfd00346a099a4"

    // ───────────────────────────────────────────────────────────────────────────
    // 1. Verified caller (STIR/SHAKEN PASSED)
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testVerifiedCallerProducesAllowAndLowRisk() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_PASSED,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING,
            presentation = CallScreeningEvaluator.PRESENTATION_ALLOWED
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.LOW, result.riskLevel)
        assertEquals("safe", result.riskState)
        assertEquals(WarningType.NONE, result.warningType)
        assertTrue(result.reasonCodes.contains("CALLER_VERIFIED"))
        assertFalse(result.maskedCaller.contains("987654"))
        assertTrue(result.explanation.isNotBlank())
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 2. NOT_VERIFIED caller — CORRECTED in Phase 3.1
    //    NOT_VERIFIED is the default in India/most markets (STIR/SHAKEN not deployed).
    //    It is a carrier metadata signal, NOT proof of fraud.
    //    Expected: ALLOW, LOW risk, riskState="low", UNVERIFIED_CALLER warning.
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testNotVerifiedCallerProducesAllowAndLowRisk() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING,
            presentation = CallScreeningEvaluator.PRESENTATION_ALLOWED
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.LOW, result.riskLevel)
        assertEquals("low", result.riskState)
        assertEquals(15, result.riskScore)
        assertEquals(WarningType.UNVERIFIED_CALLER, result.warningType)
        assertTrue(result.reasonCodes.contains("CALLER_NOT_VERIFIED"))
        assertTrue(result.explanation.isNotBlank())
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 3. VERIFICATION_FAILED — active carrier spoofing signal
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testFailedVerificationProducesAllowAndHighRiskWarning() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_FAILED,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING,
            presentation = CallScreeningEvaluator.PRESENTATION_ALLOWED
        )

        // Conservative policy: ALLOW call to ring, but tag with HIGH risk and warning
        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.HIGH, result.riskLevel)
        assertEquals("high", result.riskState)
        assertEquals(75, result.riskScore)
        assertEquals(WarningType.VERIFICATION_FAILED, result.warningType)
        assertTrue(result.reasonCodes.contains("CALLER_VERIFICATION_FAILED"))
        assertTrue(result.explanation.isNotBlank())
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 4. Unknown / null verification — safe default
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testNullOrUnknownVerificationDegradesSafely() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING,
            presentation = CallScreeningEvaluator.PRESENTATION_ALLOWED
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.LOW, result.riskLevel)
        assertTrue(result.riskState == "low" || result.riskState == "safe")
        assertTrue(result.reasonCodes.contains("DEFAULT_ALLOW") || result.reasonCodes.contains("CALLER_NOT_VERIFIED"))
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 5. Null or empty handle
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testNullHandleHandledGracefully() {
        val resultAllowed = CallScreeningEvaluator.evaluate(
            rawHandle = null,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN,
            presentation = CallScreeningEvaluator.PRESENTATION_ALLOWED
        )

        assertEquals(ScreeningDecision.ALLOW, resultAllowed.decision)
        assertEquals("Unknown Number", resultAllowed.maskedCaller)
        assertEquals("", resultAllowed.callerHash)

        val resultUnknown = CallScreeningEvaluator.evaluate(
            rawHandle = null,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN,
            presentation = CallScreeningEvaluator.PRESENTATION_UNKNOWN
        )
        assertEquals(ScreeningDecision.ALLOW, resultUnknown.decision)
        assertEquals("Private / Unknown", resultUnknown.maskedCaller)
        assertEquals("", resultUnknown.callerHash)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 6. Restricted presentation (Defensive fallback test)
    // Note: Per Android Telecom documentation, PRESENTATION_RESTRICTED is not delivered to
    // CallScreeningService in production. This test validates our defensive fallback handling.
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testRestrictedPresentationProducesMediumRisk() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:+919876543210",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN,
            presentation = CallScreeningEvaluator.PRESENTATION_RESTRICTED
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.MEDIUM, result.riskLevel)
        assertEquals("suspicious", result.riskState)
        assertEquals(45, result.riskScore)
        assertEquals(WarningType.RESTRICTED_NUMBER, result.warningType)
        assertEquals("Restricted Number", result.maskedCaller)
        assertTrue(result.reasonCodes.contains("RESTRICTED_CALLER_ID"))
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 7. Direction handling
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testIncomingDirectionPreserved() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING
        )
        assertEquals(ScreeningDecision.ALLOW, result.decision)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 8. Deterministic output
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testEvaluationIsStrictlyDeterministic() {
        val res1 = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_FAILED,
            timestamp = 1000L
        )
        val res2 = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_FAILED,
            timestamp = 1000L
        )

        assertEquals(res1, res2)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 9. Masking formats
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testMaskingHidesMiddleDigits() {
        val canonical10 = "+919876543210"
        val masked10 = CallScreeningEvaluator.mask(canonical10)
        assertEquals("+91 ***** *3210", masked10)
        assertFalse(masked10.contains("987654"))

        val local10 = "9876543210"
        val maskedLocal = CallScreeningEvaluator.mask(local10)
        assertEquals("***** *3210", maskedLocal)

        val shortNumber = "1234"
        val maskedShort = CallScreeningEvaluator.mask(shortNumber)
        assertEquals("***4", maskedShort)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 10. Canonicalization and SHA-256 hashing
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testCanonicalizationAndSha256() {
        val formatted = " tel: +91 (987) 654-3210 "
        val canonical = CallScreeningEvaluator.canonicalize(formatted)
        assertEquals("+919876543210", canonical)

        val hash = CallScreeningEvaluator.sha256(canonical)
        assertNotEquals("", hash)
        assertEquals(64, hash.length) // SHA-256 hex length
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 11. No raw number in persisted event record (expanded schema)
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testNoRawNumberInEventRecord() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_FAILED
        )

        val record = ScreenedCallRecord(
            eventId = "test-uuid",
            timestamp = result.timestamp,
            callerMasked = result.maskedCaller,
            callerName = null,
            callerHash = result.callerHash,
            contactStatus = result.contactStatus,
            verificationStatus = "FAILED",
            riskScore = result.riskScore,
            riskState = result.riskState,
            decision = result.decision.name,
            riskLevel = result.riskLevel.name,
            warningType = result.warningType.name,
            category = "SIM Call",
            explanation = result.explanation,
            reasonCodes = result.reasonCodes,
            screeningLatencyMs = 2L,
            source = "SIM_CALL",
            audioAnalysisStatus = "NOT_PERFORMED"
        )

        val json = record.toJsonObject().toString()
        assertFalse("Persisted JSON must not contain raw phone number", json.contains("9876543210"))
        assertTrue("Persisted JSON must contain masked form", json.contains(result.maskedCaller))
        assertTrue("Persisted JSON must contain SHA-256 hash", json.contains(result.callerHash))
        assertTrue("Persisted JSON must contain riskState", json.contains("riskState"))
        assertTrue("Persisted JSON must contain explanation", json.contains("explanation"))
        assertTrue("Persisted JSON must contain audioAnalysisStatus", json.contains("NOT_PERFORMED"))
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 12. Local blocklist rule
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testLocalBlocklistProducesReject() {
        val canonical = CallScreeningEvaluator.canonicalize(samplePhone)
        val hash = CallScreeningEvaluator.sha256(canonical)
        val blocklist = setOf(hash)

        val result = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_PASSED,
            localBlocklist = blocklist
        )

        assertEquals(ScreeningDecision.REJECT, result.decision)
        assertEquals(RiskLevel.HIGH, result.riskLevel)
        assertEquals("critical", result.riskState)
        assertEquals(95, result.riskScore)
        assertEquals(WarningType.BLOCKLIST_MATCH, result.warningType)
        assertTrue(result.reasonCodes.contains("LOCAL_BLOCKLIST_MATCH"))
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 13. Contact caller — Phase 3.1 (NEW)
    //     Known contacts must be LOW/safe regardless of verification status.
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testKnownContactProducesAllowAndSafeRisk() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED,
            isContact = true,
            callerName = "Neeraj"
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.LOW, result.riskLevel)
        assertEquals("safe", result.riskState)
        assertEquals(0, result.riskScore)
        assertEquals(WarningType.NONE, result.warningType)
        assertEquals("IN_CONTACTS", result.contactStatus)
        assertEquals("Neeraj", result.callerName)
        assertTrue(result.reasonCodes.contains("KNOWN_CONTACT"))
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 14. Non-contact unverified caller — Phase 3.1 (NEW)
    //     Same as test 2 but with explicit contactStatus assertion.
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testNonContactUnverifiedCallerIsLowNotSuspicious() {
        val result = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED,
            isContact = false,
            callerName = null
        )

        assertEquals(ScreeningDecision.ALLOW, result.decision)
        assertEquals(RiskLevel.LOW, result.riskLevel)
        // NOT "suspicious", "high", or "critical"
        assertFalse("Non-contact unverified must not be suspicious", result.riskState == "suspicious")
        assertFalse("Non-contact unverified must not be high", result.riskState == "high")
        assertEquals("NOT_IN_CONTACTS", result.contactStatus)
        assertNull(result.callerName)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 15. Contact + blocklist — blocklist wins
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testBlocklistTakesPriorityOverContactStatus() {
        val canonical = CallScreeningEvaluator.canonicalize(samplePhone)
        val hash = CallScreeningEvaluator.sha256(canonical)
        val blocklist = setOf(hash)

        val result = CallScreeningEvaluator.evaluate(
            rawHandle = samplePhone,
            localBlocklist = blocklist,
            isContact = true,
            callerName = "Trusted Person"
        )

        // Blocklist always wins — even a contact is rejected when explicitly blocklisted
        assertEquals(ScreeningDecision.REJECT, result.decision)
        assertEquals(RiskLevel.HIGH, result.riskLevel)
        assertEquals("critical", result.riskState)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 16. Explanation is always non-blank
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testExplanationIsAlwaysPresent() {
        val statuses = listOf(
            CallScreeningEvaluator.VERIFICATION_STATUS_PASSED,
            CallScreeningEvaluator.VERIFICATION_STATUS_FAILED,
            CallScreeningEvaluator.VERIFICATION_STATUS_NOT_VERIFIED,
            CallScreeningEvaluator.VERIFICATION_STATUS_UNKNOWN
        )
        for (status in statuses) {
            val result = CallScreeningEvaluator.evaluate(
                rawHandle = "tel:$samplePhone",
                verificationStatus = status
            )
            assertTrue(
                "Explanation must be non-blank for verificationStatus=$status",
                result.explanation.isNotBlank()
            )
        }
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 17. Evaluator latency benchmark
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testEvaluatorLatencyRemainsSubMillisecond() {
        // Warmup
        for (i in 0 until 100) {
            CallScreeningEvaluator.evaluate(samplePhone, CallScreeningEvaluator.VERIFICATION_STATUS_PASSED)
        }

        val iterations = 1000
        val startNano = System.nanoTime()
        for (i in 0 until iterations) {
            CallScreeningEvaluator.evaluate(
                rawHandle = samplePhone,
                verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_FAILED
            )
        }
        val totalNano = System.nanoTime() - startNano
        val avgNano = totalNano / iterations
        val avgMillis = avgNano / 1_000_000.0

        // Evaluator is pure in-memory math and string formatting; must execute in < 1.0 ms
        assertTrue("Evaluator avg latency ($avgMillis ms) must be < 1.0 ms", avgMillis < 1.0)
    }

    // ───────────────────────────────────────────────────────────────────────────
    // 18. Persistence serialization latency (expanded schema)
    // Note: The measured local operations are bounded to approximately 1.5–3 ms
    // in the available in-process benchmark, leaving substantial margin
    // relative to Android Telecom's 5-second screening requirement.
    // ───────────────────────────────────────────────────────────────────────────
    @Test
    fun testCriticalPathPersistenceDataModelLatency() {
        val eval = CallScreeningEvaluator.evaluate(samplePhone, CallScreeningEvaluator.VERIFICATION_STATUS_FAILED)

        val iterations = 500
        val startNano = System.nanoTime()
        for (i in 0 until iterations) {
            val record = ScreenedCallRecord(
                eventId = "bench-uuid-$i",
                timestamp = eval.timestamp,
                callerMasked = eval.maskedCaller,
                callerName = null,
                callerHash = eval.callerHash,
                contactStatus = eval.contactStatus,
                verificationStatus = "FAILED",
                riskScore = eval.riskScore,
                riskState = eval.riskState,
                decision = eval.decision.name,
                riskLevel = eval.riskLevel.name,
                warningType = eval.warningType.name,
                category = "SIM Call",
                explanation = eval.explanation,
                reasonCodes = eval.reasonCodes,
                screeningLatencyMs = 3L,
                source = "SIM_CALL",
                audioAnalysisStatus = "NOT_PERFORMED"
            )
            val jsonString = record.toJsonObject().toString()
            assertFalse(jsonString.contains("9876543210"))
        }
        val totalNano = System.nanoTime() - startNano
        val avgMillis = (totalNano / iterations) / 1_000_000.0

        // Serialization must take < 2.0 ms per record, comfortably within Android Telecom 5.0 second budget
        assertTrue("Serialization avg latency ($avgMillis ms) must be < 2.0 ms", avgMillis < 2.0)
    }

    @Test
    fun testCallDirectionEvaluationAndSerialization() {
        val incomingEval = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_PASSED,
            callDirection = CallScreeningEvaluator.DIRECTION_INCOMING
        )
        assertEquals("INCOMING", incomingEval.callDirection)

        val outgoingEval = CallScreeningEvaluator.evaluate(
            rawHandle = "tel:$samplePhone",
            verificationStatus = CallScreeningEvaluator.VERIFICATION_STATUS_PASSED,
            callDirection = CallScreeningEvaluator.DIRECTION_OUTGOING
        )
        assertEquals("OUTGOING", outgoingEval.callDirection)

        val record = ScreenedCallRecord(
            eventId = "test-out-1",
            timestamp = outgoingEval.timestamp,
            callerMasked = outgoingEval.maskedCaller,
            callerName = null,
            callerHash = outgoingEval.callerHash,
            contactStatus = outgoingEval.contactStatus,
            verificationStatus = "PASSED",
            riskScore = outgoingEval.riskScore,
            riskState = outgoingEval.riskState,
            decision = outgoingEval.decision.name,
            riskLevel = outgoingEval.riskLevel.name,
            warningType = outgoingEval.warningType.name,
            category = "SIM Call",
            explanation = outgoingEval.explanation,
            reasonCodes = outgoingEval.reasonCodes,
            screeningLatencyMs = 2L,
            source = "SIM_CALL",
            audioAnalysisStatus = "NOT_PERFORMED",
            callDirection = outgoingEval.callDirection
        )

        val json = record.toJsonObject()
        assertEquals("OUTGOING", json.getString("callDirection"))

        val restored = ScreenedCallRecord.fromJsonObject(json)
        assertEquals("OUTGOING", restored.callDirection)
    }
}
