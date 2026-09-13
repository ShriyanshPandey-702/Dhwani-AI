"""
VoiceShield FastAPI Backend — Main Entry Point
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.api import auth, users, devices, sessions, risk, incidents, challenge, verification
from app.websocket.gateway import router as ws_router, shutdown_ml_pool

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("voiceshield.startup", env=settings.APP_ENV)
    # Create tables on startup (dev convenience — use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Phase 1.6: clean shutdown of the ML inference thread pool.
    shutdown_ml_pool()
    log.info("voiceshield.shutdown")


app = FastAPI(
    title="VoiceShield API",
    description="Real-time voice security backend — DETECT → SCORE → CHALLENGE → VERIFY → PROTECT",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(auth.router,         prefix="/auth",          tags=["Auth"])
app.include_router(users.router,        prefix="/users",         tags=["Users"])
app.include_router(devices.router,      prefix="/devices",       tags=["Devices"])
app.include_router(sessions.router,     prefix="/sessions",      tags=["Sessions"])
app.include_router(risk.router,         prefix="/risk",          tags=["Risk"])
app.include_router(incidents.router,    prefix="/incidents",     tags=["Incidents"])
app.include_router(challenge.router,    prefix="/challenge",     tags=["Challenge"])
app.include_router(verification.router, prefix="/verification",  tags=["Verification"])
app.include_router(ws_router,                                    tags=["WebSocket"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "voiceshield-api"}
