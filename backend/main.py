import os
import logging

# Load .env before anything else reads os.getenv()
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on system env vars
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.ws.mt5_handler import router as mt5_router, frontend_router
from app.api.routes import router as api_router
from app.core.loop import background_trading_loop
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize runtime_state with AI preferences from env
    from app.services.runtime_state import runtime_state
    ai_provider = os.getenv("AI_PROVIDER", "openai")
    ai_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if ai_key:
        runtime_state.set_ai_preferences(provider=ai_provider, api_key=ai_key)
        # Also ensure os.environ has the key for fallback lookups
        os.environ.setdefault("AI_API_KEY", ai_key)
        os.environ.setdefault("OPENAI_API_KEY", ai_key)
        logger.info(f"AI provider initialized: {ai_provider} (key configured)")
    else:
        logger.warning("No AI_API_KEY or OPENAI_API_KEY found in environment")

    # Start AllTick gold stream (secondary price source)
    from app.services.gold_stream import start_gold_stream
    if os.getenv("ALLTICK_ENABLED", "false").lower() == "true":
        start_gold_stream()
        logger.info("AllTick gold stream started")
    else:
        logger.info("AllTick gold stream disabled")

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

# CORS: Use env-configured origins in production, wildcard only in development
_cors_env = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if os.getenv("ENV", "development") == "development" else ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mt5_router, prefix="/ws")
app.include_router(frontend_router, prefix="/ws")
app.include_router(api_router, prefix="/api")


# ── Health Check Endpoints (K8s-compatible) ──────────────────────────────────

@app.get("/health", tags=["health"])
async def health_liveness():
    """Liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_readiness():
    """Readiness probe — checks MT5, Supabase, and AI provider connectivity."""
    checks = {}

    # Bridge-owned MT5 check
    try:
        from app.services.runtime_state import runtime_state
        from app.api.ws.mt5_handler import manager

        latest_candles = runtime_state.snapshot().get("latest_candles", {})
        bridge_connected = len(manager.active_connections) > 0
        tick_source = runtime_state.get_tick_source()
        checks["mt5"] = {
            "status": "ok" if bridge_connected and latest_candles else "degraded" if bridge_connected else "unavailable",
            "connected": bridge_connected,
            "live_candles": bool(latest_candles),
            "tick_source": tick_source,
        }
    except Exception as e:
        checks["mt5"] = {"status": "error", "message": str(e)}

    # Database check
    try:
        from app.services.database import db
        checks["database"] = {
            "status": "ok" if db.is_enabled() else "unavailable",
            "connected": db.is_enabled(),
        }
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}

    # AI Provider check
    ai_key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
    ai_provider = os.getenv("AI_PROVIDER", "openai")
    checks["ai"] = {
        "status": "ok" if ai_key else "no_key",
        "provider": ai_provider,
        "key_configured": bool(ai_key),
    }

    # AllTick stream check
    alltick_enabled = os.getenv("ALLTICK_ENABLED", "false").lower() == "true"
    checks["alltick"] = {
        "status": "enabled" if alltick_enabled else "disabled",
        "enabled": alltick_enabled,
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
    reload_enabled = os.getenv("BACKEND_RELOAD", "false").lower() == "true"
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload_enabled,
        reload_dirs=["app"] if reload_enabled else None,
    )

