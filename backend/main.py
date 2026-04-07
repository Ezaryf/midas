import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ws.mt5_handler import router as mt5_router
from app.api.routes import router as api_router
from app.core.loop import background_trading_loop
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background trading loop on startup
    loop_task = asyncio.create_task(background_trading_loop())
    logger.info("Background trading loop started.")
    yield
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    logger.info("Background trading loop stopped.")


app = FastAPI(
    title="Midas Trading Backend",
    description="Backend engine for MT5 connection and AI signal generation.",
    version="1.0.0",
    lifespan=lifespan,
)

<<<<<<< HEAD
# CORS: Use env-configured origins in production, wildcard only in development
_cors_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENV", "development") == "development" else ALLOWED_ORIGINS,
=======
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mt5_router, prefix="/ws")
app.include_router(api_router, prefix="/api")


<<<<<<< HEAD
# ── Health Check Endpoints (K8s-compatible) ──────────────────────────────────

@app.get("/health", tags=["health"])
async def health_liveness():
    """Liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_readiness():
    """Readiness probe — checks MT5, Supabase, and AI provider connectivity."""
    checks = {}

    # MT5 check
    try:
        import MetaTrader5 as mt5
        terminal = mt5.terminal_info()
        checks["mt5"] = {
            "status": "ok" if terminal else "unavailable",
            "connected": terminal is not None,
        }
    except Exception as e:
        checks["mt5"] = {"status": "error", "message": str(e)}

    # Supabase check
    try:
        from app.services.database import db
        checks["supabase"] = {
            "status": "ok" if db.is_enabled() else "unavailable",
            "connected": db.is_enabled(),
        }
    except Exception as e:
        checks["supabase"] = {"status": "error", "message": str(e)}

    # AI Provider check
    ai_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    ai_provider = os.getenv("AI_PROVIDER", "openai")
    checks["ai"] = {
        "status": "ok" if ai_key else "no_key",
        "provider": ai_provider,
        "key_configured": bool(ai_key),
    }

    all_ok = all(
        c.get("status") == "ok" for c in checks.values()
    )
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app"])

=======
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app"])
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
