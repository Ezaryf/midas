import asyncio
import logging
import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas.contracts import (
    AnalysisBatchResponse,
    ErrorResponse,
    ExecutionResultResponse,
    HealthResponse,
    RiskCheckResponse,
)
from app.services.application import application_service
from app.services.forex_factory import ForexFactoryService
from app.services.news_service import NewsService
from app.services.runtime_state import runtime_state

logger = logging.getLogger(__name__)
router = APIRouter()

ff_service = ForexFactoryService()
news_service = NewsService()


class GenericStatusResponse(BaseModel):
    status: Literal["ok", "warning", "error"] = "ok"
    message: str | None = None
    data: dict = Field(default_factory=dict)


class ForceGenerateRequest(BaseModel):
    price: float | None = None
    trading_style: Literal["Scalper", "Intraday", "Swing"] = "Intraday"
    api_key: str | None = None
    ai_provider: str = "openai"


class ExecuteSignalRequest(BaseModel):
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    confidence: float = 0
    reasoning: str = ""
    trading_style: Literal["Scalper", "Intraday", "Swing"] = "Intraday"
    lot: float | None = None


class ValidateKeyRequest(BaseModel):
    api_key: str
    ai_provider: str = "openai"


class ValidateMT5Request(BaseModel):
    login: int
    password: str
    server: str
    symbol: str = "GOLD"


class SetTradingStyleRequest(BaseModel):
    trading_style: Literal["Scalper", "Intraday", "Swing"] = "Scalper"


class SetTargetSymbolRequest(BaseModel):
    target_symbol: str = "XAUUSD"


class UpdateSettingsRequest(BaseModel):
    max_concurrent_positions: int | None = None
    max_daily_trades: int | None = None
    max_risk_percent: float | None = None
    daily_loss_limit: float | None = None
    news_blackout_minutes: int | None = None
    auto_execute_confidence: float | None = None
    analysis_interval_seconds: int | None = None
    position_cooldown_seconds: int | None = None
    enable_kill_switch: bool | None = None
    min_lot_size: float | None = None
    max_lot_size: float | None = None
    min_stop_distance_points: float | None = None
    partial_close_enabled: bool | None = None
    partial_close_percent: float | None = None
    breakeven_enabled: bool | None = None
    breakeven_buffer_pips: float | None = None
    trailing_stop_enabled: bool | None = None
    trailing_stop_distance_pips: float | None = None
    trailing_stop_step_pips: float | None = None
    time_exit_enabled: bool | None = None
    exit_before_news_minutes: int | None = None
    exit_before_weekend_hours: int | None = None


class RiskCheckRequest(BaseModel):
    direction: Literal["BUY", "SELL"] = "BUY"
    symbol: str | None = None
    volume: float | None = None
    price: float | None = None


@router.post("/signals/force-generate", response_model=AnalysisBatchResponse)
async def force_generate_signal(req: ForceGenerateRequest = ForceGenerateRequest()):
    return await application_service.force_generate_signal(
        trading_style=req.trading_style,
        api_key=req.api_key,
        ai_provider=req.ai_provider,
    )


@router.post("/trading-style", response_model=GenericStatusResponse)
async def set_trading_style(req: SetTradingStyleRequest):
    data = application_service.set_trading_style(req.trading_style)
    logger.info(f"Trading style changed to: {req.trading_style}")
    return GenericStatusResponse(status="ok", message="Trading style updated", data=data)


@router.post("/target-symbol", response_model=GenericStatusResponse)
async def set_target_symbol(req: SetTargetSymbolRequest):
    data = application_service.set_target_symbol(req.target_symbol)
    logger.info(f"Target symbol changed to: {req.target_symbol}")
    return GenericStatusResponse(status="ok", message="Target symbol updated", data=data)


@router.post("/settings", response_model=GenericStatusResponse)
async def update_settings(req: UpdateSettingsRequest):
    from app.services.risk_manager import get_risk_manager
    from app.services.position_manager import get_position_manager
    from app.services.position_monitor import get_position_monitor
    from app.services.database import db
    import app.core.loop as trading_loop

    account_id = "default"
    current_settings = db.get_settings(account_id) if db and db.is_enabled() else {}
    updates = req.model_dump(exclude_unset=True)
    current_settings.update(updates)
    if db and db.is_enabled():
        db.update_settings(account_id, current_settings)

    # 1. Update services
    risk_manager = get_risk_manager()
    position_manager = get_position_manager()
    position_monitor = get_position_monitor()

    # 1. Update services
    if risk_manager:
        risk_manager.config.refresh_config()
    if position_manager:
        position_manager.config = position_manager.config.from_db()
    if position_monitor:
        position_monitor.config.refresh_config()
    
    # 2. Update loop interval if changed
    if req.analysis_interval_seconds is not None:
        trading_loop.ANALYSIS_INTERVAL = req.analysis_interval_seconds

    # 3. Inform MT5 bridge via Websockets
    try:
        from app.api.ws.mt5_handler import manager
        await manager.broadcast_json({"type": "CONFIG_UPDATE", "data": updates})
    except Exception as e:
        logger.error(f"Failed to broadcast config update to MT5 bridge: {e}")

    # 4. Collect changes for response
    changes = [f"{k}={v}" for k, v in updates.items()]


    logger.info(f"Settings updated: {', '.join(changes)}")

    return GenericStatusResponse(status="ok", message="Settings updated", data={"changes": changes})


@router.get("/settings", response_model=dict)
def get_settings():
    from app.services.risk_manager import get_risk_manager
    from app.services.position_manager import get_position_manager
    from app.services.position_monitor import get_position_monitor
    from app.services.database import db
    
    risk_manager = get_risk_manager()
    position_manager = get_position_manager()
    position_monitor = get_position_monitor()
    
    account_id = "default"
    db_settings = db.get_settings(account_id) if db and db.is_enabled() else {}
    
    def _get(key: str, env_key: str, default: any, type_func=float):
        if key in db_settings:
            return type_func(db_settings[key])
        return type_func(os.getenv(env_key, default))

    def _get_bool(key: str, env_key: str, default: bool):
        if key in db_settings:
            return bool(db_settings[key])
        return os.getenv(env_key, str(default).lower()) == "true"

    settings = {
        "confidence": {
            "auto_execute_confidence": _get("auto_execute_confidence", "AUTO_EXECUTE_MIN_CONFIDENCE", "60"),
            "force_execution_mode": os.getenv("FORCE_EXECUTION_MODE", "false") == "true",
        },
        "daily_limits": {
            "max_daily_trades": _get("max_daily_trades", "MAX_DAILY_TRADES", "50", int),
            "daily_loss_limit": _get("daily_loss_limit", "DAILY_LOSS_LIMIT", "500", float),
        },
        "risk_per_trade": {
            "max_risk_percent": risk_manager.config.max_risk_percent if risk_manager and "max_risk_percent" not in db_settings else _get("max_risk_percent", "MAX_RISK_PERCENT", "1.0", float),
            "min_lot_size": risk_manager.config.min_lot_size if risk_manager and "min_lot_size" not in db_settings else _get("min_lot_size", "MIN_LOT_SIZE", "0.01", float),
            "max_lot_size": risk_manager.config.max_lot_size if risk_manager and "max_lot_size" not in db_settings else _get("max_lot_size", "MAX_LOT_SIZE", "1.0", float),
            "min_stop_distance_points": _get("min_stop_distance_points", "MIN_STOP_DISTANCE_POINTS", "30", float),
        },
        "exposure": {
            "max_concurrent_positions": risk_manager.config.max_concurrent_positions if risk_manager and "max_concurrent_positions" not in db_settings else _get("max_concurrent_positions", "MAX_CONCURRENT_POSITIONS", "3", int),
            "max_drawdown_percent": risk_manager.config.max_drawdown_percent if risk_manager and "max_drawdown_percent" not in db_settings else _get("max_drawdown_percent", "MAX_DRAWDOWN_PERCENT", "20.0", float),
            "allow_hedging": risk_manager.config.allow_hedging if risk_manager and "allow_hedging" not in db_settings else _get_bool("allow_hedging", "ALLOW_HEDGING", False),
        },
        "position_management": {
            "partial_close_enabled": position_monitor.config.partial_close_enabled if position_monitor and "partial_close_enabled" not in db_settings else _get_bool("partial_close_enabled", "PARTIAL_CLOSE_ENABLED", True),
            "partial_close_percent": position_monitor.config.partial_close_percent if position_monitor and "partial_close_percent" not in db_settings else _get("partial_close_percent", "PARTIAL_CLOSE_PERCENT", "50", float),
            "breakeven_enabled": position_monitor.config.breakeven_enabled if position_monitor and "breakeven_enabled" not in db_settings else _get_bool("breakeven_enabled", "BREAKEVEN_ENABLED", True),
            "breakeven_buffer_pips": position_monitor.config.breakeven_buffer_pips if position_monitor and "breakeven_buffer_pips" not in db_settings else _get("breakeven_buffer_pips", "BREAKEVEN_BUFFER_PIPS", "5", float),
            "trailing_stop_enabled": position_monitor.config.trailing_stop_enabled if position_monitor and "trailing_stop_enabled" not in db_settings else _get_bool("trailing_stop_enabled", "TRAILING_STOP_ENABLED", True),
            "trailing_stop_distance_pips": position_monitor.config.trailing_stop_distance_pips if position_monitor and "trailing_stop_distance_pips" not in db_settings else _get("trailing_stop_distance_pips", "TRAILING_STOP_DISTANCE_PIPS", "50", float),
            "trailing_stop_step_pips": position_monitor.config.trailing_stop_step_pips if position_monitor and "trailing_stop_step_pips" not in db_settings else _get("trailing_stop_step_pips", "TRAILING_STOP_STEP_PIPS", "10", float),
            "time_exit_enabled": position_monitor.config.time_exit_enabled if position_monitor and "time_exit_enabled" not in db_settings else _get_bool("time_exit_enabled", "TIME_EXIT_ENABLED", True),
            "exit_before_news_minutes": position_monitor.config.exit_before_news_minutes if position_monitor and "exit_before_news_minutes" not in db_settings else _get("exit_before_news_minutes", "EXIT_BEFORE_NEWS_MINUTES", "15", int),
            "exit_before_weekend_hours": position_monitor.config.exit_before_weekend_hours if position_monitor and "exit_before_weekend_hours" not in db_settings else _get("exit_before_weekend_hours", "EXIT_BEFORE_WEEKEND_HOURS", "2", int),
        },

        "position_cooldown_seconds": position_manager.config.cooldown_seconds if position_manager and "position_cooldown_seconds" not in db_settings else _get("position_cooldown_seconds", "POSITION_COOLDOWN_SECONDS", "30", int),
        "analysis_interval_seconds": _get("analysis_interval_seconds", "ANALYSIS_INTERVAL_SECONDS", "5", int),
    }
    return settings


@router.post("/signals/execute", response_model=ExecutionResultResponse)
async def execute_signal(req: ExecuteSignalRequest):
    if req.stop_loss is None or req.take_profit_1 is None:
        return ExecutionResultResponse(status="error", message="Invalid signal: stop_loss and take_profit_1 are required")
    return await application_service.execute_signal(req.model_dump())


@router.get("/calendar", response_model=dict)
def get_calendar():
    return {"events": ff_service.get_weekly_events()}


@router.get("/news", response_model=dict)
async def get_news():
    return {"items": await news_service.get_gold_news()}


@router.post("/ai/validate", response_model=GenericStatusResponse | ErrorResponse)
async def validate_api_key(req: ValidateKeyRequest):
    from app.services.ai_engine import AITradingEngine

    try:
        engine = AITradingEngine(api_key=req.api_key, provider=req.ai_provider)
        response = await engine.client.chat.completions.create(
            model=engine.model,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
            max_tokens=5,
        )
        reply = response.choices[0].message.content or ""
        return GenericStatusResponse(status="ok", message="API key validated", data={"model": engine.model, "reply": reply.strip()})
    except Exception as exc:
        return ErrorResponse(message=str(exc))


@router.post("/mt5/validate", response_model=dict | ErrorResponse)
async def validate_mt5(req: ValidateMT5Request):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return ErrorResponse(message="MetaTrader5 not installed. Run: pip install MetaTrader5")

    def _test():
        if not mt5.initialize():
            err = mt5.last_error()
            if err[0] == -6:
                return {"status": "error", "message": "MT5 terminal is not open. Open MetaTrader 5 first."}
            return {"status": "error", "message": f"MT5 init failed: {err}"}

        ok = mt5.login(req.login, password=req.password, server=req.server)
        if not ok:
            err = mt5.last_error()
            mt5.shutdown()
            return {"status": "error", "message": f"Login failed: {err[1]}"}

        info = mt5.account_info()
        candidates = [req.symbol, "XAUUSD", "GOLD", "XAUUSDm"]
        resolved = None
        for candidate in candidates:
            mt5.symbol_select(candidate, True)
            if mt5.symbol_info(candidate):
                resolved = candidate
                break

        tick = mt5.symbol_info_tick(resolved) if resolved else None
        mt5.shutdown()
        return {
            "status": "ok",
            "name": info.name if info else "Unknown",
            "balance": info.balance if info else 0,
            "currency": info.currency if info else "USD",
            "leverage": info.leverage if info else 0,
            "server": info.server if info else req.server,
            "symbol": resolved,
            "bid": round(tick.bid, 2) if tick else None,
            "ask": round(tick.ask, 2) if tick else None,
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _test)


@router.get("/health", response_model=HealthResponse | ErrorResponse)
def health():
    try:
        return application_service.health()
    except Exception as exc:
        logger.error(f"Health check error: {exc}")
        return ErrorResponse(message=str(exc))


@router.get("/account", response_model=dict)
def get_account():
    return application_service.account()


@router.get("/history/signals", response_model=dict)
async def get_signal_history(limit: int = 50):
    return application_service.signal_history(limit=limit)


@router.get("/history/orders", response_model=dict)
async def get_order_history(status: str = "all", limit: int = 50):
    _ = limit
    return application_service.order_history(status=status)


@router.get("/analytics/performance", response_model=dict)
async def get_performance(period: str = "ALL_TIME"):
    return application_service.performance(period=period)


@router.get("/analytics/equity-curve", response_model=dict)
async def get_equity_curve(days: int = 30):
    return application_service.equity_curve(days=days)


@router.get("/risk/status", response_model=dict)
def get_risk_status():
    from app.services.risk_manager import get_risk_manager

    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available - MT5 bridge not running"}
    return risk_manager.get_risk_summary()


@router.post("/risk/check", response_model=RiskCheckResponse)
async def check_risk(req: RiskCheckRequest = RiskCheckRequest()):
    return application_service.risk_check(
        direction=req.direction,
        symbol=req.symbol,
        volume=req.volume,
        price=req.price,
    )


@router.post("/risk/force-close-all", response_model=dict)
async def force_close_all_positions():
    import MetaTrader5 as mt5
    from app.services.database import db
    from app.services.risk_manager import get_risk_manager

    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available"}

    positions = risk_manager.get_open_positions()
    if not positions:
        return {"message": "No open positions", "closed": 0}

    closed_count = 0
    for pos in positions:
        try:
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": pos.ticket,
                "magic": pos.magic,
                "comment": "Force close - Risk limit",
            }
            result = mt5.order_send(close_request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                logger.info(f"Force closed position #{pos.ticket}")
                if db.is_enabled():
                    db.log_risk_event(
                        event_type="FORCE_CLOSE",
                        description=f"Position #{pos.ticket} force closed",
                        action_taken="Manual force close",
                        metadata={"ticket": pos.ticket, "profit": pos.profit},
                    )
        except Exception as exc:
            logger.error(f"Failed to close position #{pos.ticket}: {exc}")

    return {"message": f"Closed {closed_count} positions", "closed": closed_count}


@router.get("/positions/monitor/status", response_model=dict)
def get_position_monitor_status():
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available - MT5 bridge not running"}
    return monitor.get_status()


@router.get("/positions/open", response_model=dict)
def get_open_positions():
    import MetaTrader5 as mt5
    from app.services.risk_manager import get_risk_manager

    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available"}

    positions = risk_manager.get_open_positions()
    payload = []
    for pos in positions:
        payload.append(
            {
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": pos.volume,
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "commission": getattr(pos, "commission", 0.0),
                "comment": pos.comment,
                "open_time": str(pos.time),
            }
        )
    return {"positions": payload}


@router.post("/positions/{ticket}/close", response_model=dict)
async def close_position_manual(ticket: int):
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    return monitor.close_position_manual(ticket)


@router.post("/positions/{ticket}/modify", response_model=dict)
async def modify_position_manual(ticket: int, sl: float, tp: float):
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    return monitor.modify_position_manual(ticket, sl, tp)


@router.get("/sse/stream")
async def sse_stream():
    """SSE endpoint for real-time updates (alternative to WebSocket)."""
    from fastapi.responses import StreamingResponse
    import json
    from app.api.ws.mt5_handler import manager

    async def sse_event_generator():
        """Generator that yields SSE events to connected clients."""
        heartbeat_count = 0
        try:
            logger.info("SSE: Client connected, starting event stream")
            while True:
                # Send heartbeat every 5 seconds so browser knows connection is alive
                heartbeat_count += 1
                if heartbeat_count % 10 == 0:  # Every ~5 seconds
                    event = f"data: {json.dumps({'type': 'HEARTBEAT', 'data': {'count': heartbeat_count}})}\n\n"
                    yield event

                # Get latest tick from runtime_state
                tick = runtime_state.get_tick()
                if tick:
                    tick["source"] = "sse"
                    event = f"data: {json.dumps({'type': 'TICK', 'data': tick})}\n\n"
                    yield event

                # Get active signal if any (from pending signals in manager)
                if manager._pending_signals:
                    for signal in list(manager._pending_signals)[-1:]:
                        event = f"data: {json.dumps({'type': 'SIGNAL', 'data': signal})}\n\n"
                        yield event

                await asyncio.sleep(0.5)  # Send every 500ms

        except GeneratorExit:
            logger.info("SSE: Client disconnected")
        except Exception as e:
            logger.error(f"SSE error: {e}", exc_info=True)

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
