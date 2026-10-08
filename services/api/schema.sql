-- ─────────────────────────────────────────────────────────────────────────────
-- Dhwani AI PostgreSQL Schema
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    full_name     TEXT        NOT NULL DEFAULT '',
    role          TEXT        NOT NULL DEFAULT 'user',  -- user | admin | enterprise
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Trusted Devices ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS devices (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name   TEXT        NOT NULL DEFAULT '',
    device_token  TEXT        NOT NULL UNIQUE,  -- secure random token stored in Android Keystore
    platform      TEXT        NOT NULL DEFAULT 'android',
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ
);

-- ─── Sessions ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state         TEXT        NOT NULL DEFAULT 'created',  -- created | active | ended | error
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,
    metadata      JSONB       NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Risk Snapshots ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    risk_score      SMALLINT    NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_state      TEXT        NOT NULL,  -- insufficient_evidence | low | suspicious | high | critical
    authenticity    FLOAT,
    identity        FLOAT,
    context         FLOAT,
    consequence     TEXT,
    reasons         JSONB       NOT NULL DEFAULT '[]',
    model_versions  JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Challenges ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS challenges (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    challenge_text  TEXT        NOT NULL,
    challenge_type  TEXT        NOT NULL DEFAULT 'phrase',  -- phrase | question | sequence
    state           TEXT        NOT NULL DEFAULT 'pending',  -- pending | passed | failed | timeout
    response_at     TIMESTAMPTZ,
    evidence        JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Verifications (OOB / Independent Trust Channel) ─────────────────────────
CREATE TABLE IF NOT EXISTS verifications (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    device_id       UUID        REFERENCES devices(id),
    method          TEXT        NOT NULL DEFAULT 'trusted_device',  -- trusted_device | callback | supervisor | mfa
    state           TEXT        NOT NULL DEFAULT 'requested',  -- requested | approved | rejected | timeout
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ NOT NULL,
    nonce           TEXT        NOT NULL DEFAULT gen_random_uuid()::text
);

-- ─── Incidents ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    final_state     TEXT        NOT NULL,      -- allowed | held | blocked | escalated
    peak_risk_score SMALLINT,
    peak_risk_state TEXT,
    action_taken    TEXT,
    verification_outcome TEXT,
    evidence_summary JSONB     NOT NULL DEFAULT '{}',
    policy_version  TEXT        NOT NULL DEFAULT 'v1',
    model_versions  JSONB       NOT NULL DEFAULT '{}',
    integrity_hash  TEXT        NOT NULL,      -- SHA-256 of evidence_summary
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Security Policies ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS policies (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    version         TEXT        NOT NULL UNIQUE,
    config          JSONB       NOT NULL,      -- thresholds, weights, challenge rules
    is_active       BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Insert default policy
INSERT INTO policies (version, config, is_active) VALUES (
    'v1',
    '{
        "thresholds": {
            "low": 20,
            "suspicious": 40,
            "high": 65,
            "critical": 85
        },
        "weights": {
            "authenticity": 0.50,
            "identity": 0.25,
            "context": 0.25
        },
        "consequence_multiplier": {
            "low": 1.0,
            "medium": 1.2,
            "high": 1.4,
            "critical": 1.6
        },
        "challenge_required_at": "suspicious",
        "oob_required_at": "high",
        "hold_required_at": "critical"
    }',
    TRUE
) ON CONFLICT (version) DO NOTHING;

-- ─── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_snapshots_session_id ON risk_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_challenges_session_id ON challenges(session_id);
CREATE INDEX IF NOT EXISTS idx_verifications_session_id ON verifications(session_id);
CREATE INDEX IF NOT EXISTS idx_incidents_user_id ON incidents(user_id);
CREATE INDEX IF NOT EXISTS idx_incidents_session_id ON incidents(session_id);
