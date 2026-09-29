"""Application settings — loaded from environment / .env file."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "Dhwani AI"
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8081"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://voiceshield:voiceshield@localhost:5432/voiceshield"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ─── ML pipeline ──────────────────────────────────────────────────────
    # "mock"    — deterministic demo: heuristic DSP, scripted transcript,
    #             spectral identity. This is what the SIH demonstration uses.
    # "real_ml" — load real checkpoints (AASIST / ECAPA-TDNN / faster-whisper).
    #             Each stream falls back independently and says so if its
    #             checkpoint is missing; a fallback is never labelled real.
    PIPELINE_MODE: str = "mock"

    # Directory holding downloaded checkpoints (see scripts/fetch_models.py).
    MODEL_DIR: str = "models"

    # Authenticity: "AASIST-L" (85k params) or "AASIST" (298k params).
    AASIST_VARIANT: str = "AASIST-L"
    # Escalate from AASIST-L to AASIST when the light model is undecided.
    AASIST_CASCADE: bool = True
    # Band around 0.5 treated as undecided by the cascade's first tier.
    AASIST_CASCADE_MARGIN: float = 0.25

    # Streaming analysis window. AASIST was trained on 64600 samples @ 16 kHz.
    ANALYSIS_WINDOW_MS: int = 4038
    ANALYSIS_HOP_MS: int = 1000
    # Below this the window is not scored at all.
    MIN_ANALYSIS_MS: int = 400

    # Identity: ECAPA cosine thresholds. These are the model card's typical
    # operating region, NOT a calibration against our audio conditions.
    ECAPA_VERIFIED_AT: float = 0.60
    ECAPA_MISMATCH_BELOW: float = 0.35

    # STT: faster-whisper. "tiny" keeps a 4 s window well inside real time on
    # CPU; "base"/"small" are more accurate and slower. Empty language = detect.
    WHISPER_MODEL_SIZE: str = "tiny"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "en"
    WHISPER_BEAM_SIZE: int = 1

    # Authenticity score calibration. The raw model score is ALWAYS kept; a
    # calibrator only adds `calibrated_spoof_probability` alongside it.
    # Empty disables calibration entirely.
    AUTHENTICITY_CALIBRATOR: str = "models/calibration/authenticity_isotonic_asvspoof2019la.json"
    # Whether the Risk Engine fuses the calibrated value instead of the raw one.
    # Default False: the shipped calibrator was fitted on ASVspoof 2019 LA only,
    # and measurement shows the underlying score is near-chance out of domain,
    # so a calibrated probability there would look trustworthy without being so.
    USE_CALIBRATED_SCORE_FOR_FUSION: bool = False

    # Torch device: "cpu", "mps", "cuda", or "auto".
    ML_DEVICE: str = "auto"

    # Phase 1.6: number of threads in the ML inference pool (AASIST + ECAPA).
    # Both models release the GIL during compute, so extra workers give real
    # concurrency across simultaneous sessions.  2 is conservative for the M4
    # dev machine; raise to 4 for multi-session load testing.
    ML_POOL_WORKERS: int = 2

    # Phase 1.6: Ingress backpressure configuration.
    # Maximum number of pending audio processing tasks allowed per session.
    # At nominal 4 chunks/s, 1 chunk processes ML while at most 1 chunk queues,
    # requiring <= 2 pending tasks. Setting to 4 gives 1.0 s of jitter buffer
    # without dropping nominal audio, while strictly bounding burst/flood backpressure.
    MAX_PENDING_AUDIO_CHUNKS: int = 4

    # Push (stubbed)
    FCM_PROJECT_ID: str = ""


settings = Settings()
