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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mt5_router, prefix="/ws")
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app"])
