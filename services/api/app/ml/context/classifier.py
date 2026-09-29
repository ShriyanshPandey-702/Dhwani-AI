"""
Conversation Context Classifier — back half of EVIDENCE STREAM 3.

╔══════════════════════════════════════════════════════════════════════════╗
║  STATUS: REAL but RULE-BASED. The lexical rules below are deterministic  ║
║  and unit-tested. What is stubbed is the *transcript source* (see        ║
║  transcriber.py) and the transformer model that would replace these      ║
║  rules.                                                                  ║
║                                                                          ║
║  PLANNED (Phase 3): a fine-tuned transformer (HuggingFace) for           ║
║  social-engineering intent classification, with these rules retained as  ║
║  a high-precision fallback.                                              ║
╚══════════════════════════════════════════════════════════════════════════╝

CRITICAL INVARIANT: context evidence must never alter the authenticity score.
"An OTP was requested" says nothing about whether the voice is synthetic. The
two are fused only in the Risk Engine, and the dashboard renders them in
separate panels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional

# ── Lexicons ──────────────────────────────────────────────────────────────────
# Each maps a signal name to the phrases that evidence it.

URGENCY = [
    "urgent", "urgently", "immediately", "right now", "right away", "asap",
    "time sensitive", "before the cut-off", "cut off", "hurry", "quickly",
    "no time", "stay on the line", "don't hang up",
    # Hindi / Hinglish urgency indicators
    "turant", "abhi ke abhi", "jaldi karo", "phone mat katna", "call mat kaatna",
]

FINANCIAL = [
    "transfer", "payment", "pay ", "wire", "remit", "lakh", "crore",
    "rupees", "amount", "invoice", "account number", "beneficiary",
    "send money", "fund", "deposit", "settle",
    "lottery", "prize", "reward", "cashback", "refund", "won ", "winner",
    "bank", "credit card", "debit card", "kyc",
    # Hindi / Hinglish financial scam vocabulary
    "paise", "paisa", "rupaye", "rupiya", "bhejo", "khata block", "khate",
    "inaam", "jeet gaye", "lucky draw",
]

OTP = [
    "otp", "one time password", "one-time password", "verification code",
    "security code", "read it back", "code i sent", "sms code", "6 digit",
    "six digit",
    # Hindi / Hinglish OTP extraction requests
    "otp batao", "otp share", "otp bhejo", "code batao", "pin batao",
]

CREDENTIAL = [
    "password", "pin", "cvv", "card number", "username", "login",
    "credentials", "net banking", "netbanking", "mpin", "passcode",
    # Hindi / Hinglish credential extraction requests
    "password batao", "mpin batao", "cvv batao",
]

SENSITIVE = [
    "aadhaar", "aadhar", "pan number", "confidential", "do not discuss",
    "don't tell", "keep this between", "private document", "internal report",
    "share the file", "send the document",
    # Hindi / Hinglish identity document extraction
    "aadhaar card", "aadhar card", "pan card",
]

AUTHORITY = [
    "director", "ceo", "cfo", "manager", "head of", "board", "compliance",
    "audit", "police", "income tax", "bank official", "corporate finance",
    "i'm your", "this is your",
    # Hindi / Hinglish authority impersonation and digital arrest scams
    "digital arrest", "cyber crime", "cybercrime", "cbi", "customs officer",
    "police thana", "police station", "court order", "arrest warrant",
]

SECRECY = [
    "do not discuss", "don't tell", "keep this between", "confidential",
    "no one else", "don't inform",
]


@dataclass
class ContextResult:
    # 0–100 aggregate contextual risk
    score: int
    confidence: float
    urgency: bool
    financial_request: bool
    otp_request: bool
    credential_request: bool
    sensitive_information_request: bool
    social_engineering: bool
    authority_claim: bool
    consequence: str                  # low | medium | high | critical
    transcript: str
    detected_phrases: List[str] = field(default_factory=list)
    model_version: str = "rules-v0.2"
    is_mock: bool = False
    # Transcript provenance. The rules below are the same either way; what
    # changes is where the text came from, which is recorded, not hidden.
    transcript_is_mock: bool = True
    transcript_model: str = "scripted-stt"
    transcript_pipeline_mode: str = "heuristic_demo"
    transcript_language: str = ""
    transcript_confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# Weight each signal contributes to the aggregate context risk.
_SIGNAL_WEIGHTS = {
    "otp_request": 0.30,
    "credential_request": 0.30,
    "financial_request": 0.22,
    "sensitive_information_request": 0.18,
    "urgency": 0.12,
    "authority_claim": 0.10,
    "secrecy": 0.12,
}


class ContextClassifier:
    """Rule-based social-engineering signal extraction over a transcript."""

    MODEL_VERSION = "rules-v0.2"

    def __init__(self):
        # session_id → signals seen so far (context accumulates over a call)
        self._sticky: Dict[str, Dict[str, bool]] = {}
        self._transcript: Dict[str, List[str]] = {}

    def classify(
        self,
        session_id: str,
        text: Optional[str],
        transcript_is_mock: bool = True,
        transcript_model: str = "scripted-stt",
        transcript_pipeline_mode: str = "heuristic_demo",
        transcript_language: str = "",
        transcript_confidence: float = 0.0,
    ) -> Optional[ContextResult]:
        """
        Extract contextual risk signals from one transcript segment.

        Signals are sticky for the lifetime of the session: once a caller has
        asked for an OTP, that fact does not disappear from the risk picture
        when the next sentence is innocuous.
        """
        if not text or not text.strip():
            return None

        lowered = text.lower()
        matched: List[str] = []

        def hit(lexicon: List[str]) -> bool:
            found = False
            for phrase in lexicon:
                if phrase in lowered:
                    matched.append(phrase.strip())
                    found = True
            return found

        window = {
            "urgency": hit(URGENCY),
            "financial_request": hit(FINANCIAL),
            "otp_request": hit(OTP),
            "credential_request": hit(CREDENTIAL),
            "sensitive_information_request": hit(SENSITIVE),
            "authority_claim": hit(AUTHORITY),
            "secrecy": hit(SECRECY),
        }

        sticky = self._sticky.setdefault(session_id, {k: False for k in window})
        for k, v in window.items():
            sticky[k] = sticky.get(k, False) or v

        history = self._transcript.setdefault(session_id, [])
        history.append(text)
        del history[:-30]

        raw = sum(_SIGNAL_WEIGHTS[k] for k, v in sticky.items() if v)
        score = int(round(min(1.0, raw) * 100))

        # Social engineering = pressure + a request for something valuable.
        pressure = sticky["urgency"] or sticky["authority_claim"] or sticky["secrecy"]
        ask = (
            sticky["otp_request"]
            or sticky["credential_request"]
            or sticky["financial_request"]
            or sticky["sensitive_information_request"]
        )
        social_engineering = bool(pressure and ask)

        consequence = self._consequence(sticky)

        # Confidence rises as more of the conversation is observed.
        confidence = round(min(0.85, 0.35 + 0.06 * len(history)), 3)

        return ContextResult(
            score=score,
            confidence=confidence,
            urgency=sticky["urgency"],
            financial_request=sticky["financial_request"],
            otp_request=sticky["otp_request"],
            credential_request=sticky["credential_request"],
            sensitive_information_request=sticky["sensitive_information_request"],
            social_engineering=social_engineering,
            authority_claim=sticky["authority_claim"],
            consequence=consequence,
            transcript=text,
            detected_phrases=sorted(set(matched)),
            model_version=self.MODEL_VERSION,
            is_mock=False,
            transcript_is_mock=transcript_is_mock,
            transcript_model=transcript_model,
            transcript_pipeline_mode=transcript_pipeline_mode,
            transcript_language=transcript_language,
            transcript_confidence=transcript_confidence,
        )

    def reset(self, session_id: str) -> None:
        self._sticky.pop(session_id, None)
        self._transcript.pop(session_id, None)

    @staticmethod
    def _consequence(sticky: Dict[str, bool]) -> str:
        if sticky["otp_request"] or sticky["credential_request"]:
            return "critical"
        if sticky["financial_request"]:
            return "high"
        if sticky["sensitive_information_request"]:
            return "high"
        if sticky["urgency"] or sticky["authority_claim"]:
            return "medium"
        return "low"
