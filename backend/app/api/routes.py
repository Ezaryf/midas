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
    import app.core.loop as trading_loop

    changes = []
    risk_manager = get_risk_manager()
    position_manager = get_position_manager()

    if req.max_concurrent_positions is not None:
        os.environ["MAX_CONCURRENT_POSITIONS"] = str(req.max_concurrent_positions)
        if risk_manager:
            risk_manager.config.max_concurrent_positions = req.max_concurrent_positions
        changes.append(f"max_concurrent_positions={req.max_concurrent_positions}")

    if req.max_daily_trades is not None:
        os.environ["MAX_DAILY_TRADES"] = str(req.max_daily_trades)
        if risk_manager:
            risk_manager.config.max_daily_trades = req.max_daily_trades
        changes.append(f"max_daily_trades={req.max_daily_trades}")

    if req.max_risk_percent is not None:
        os.environ["MAX_RISK_PERCENT"] = str(req.max_risk_percent)
        if risk_manager:
            risk_manager.config.max_risk_percent = req.max_risk_percent
        changes.append(f"max_risk_percent={req.max_risk_percent}")

    if req.daily_loss_limit is not None:
        os.environ["DAILY_LOSS_LIMIT"] = str(req.daily_loss_limit)
        if risk_manager:
            risk_manager.config.daily_loss_limit = req.daily_loss_limit
        changes.append(f"daily_loss_limit={req.daily_loss_limit}")

    if req.news_blackout_minutes is not None:
        os.environ["NEWS_BLACKOUT_MINUTES"] = str(req.news_blackout_minutes)
        if risk_manager:
            risk_manager.config.news_blackout_minutes = req.news_blackout_minutes
        changes.append(f"news_blackout_minutes={req.news_blackout_minutes}")

    if req.auto_execute_confidence is not None:
        os.environ["AUTO_EXECUTE_MIN_CONFIDENCE"] = str(req.auto_execute_confidence)
        changes.append(f"auto_execute_confidence={req.auto_execute_confidence}")

    if req.analysis_interval_seconds is not None:
        os.environ["ANALYSIS_INTERVAL_SECONDS"] = str(req.analysis_interval_seconds)
        trading_loop.ANALYSIS_INTERVAL = req.analysis_interval_seconds
        changes.append(f"analysis_interval_seconds={req.analysis_interval_seconds}")

    if req.position_cooldown_seconds is not None:
        os.environ["POSITION_COOLDOWN_SECONDS"] = str(req.position_cooldown_seconds)
        position_manager.config.cooldown_seconds = req.position_cooldown_seconds
        changes.append(f"position_cooldown_seconds={req.position_cooldown_seconds}")

    if req.enable_kill_switch is not None:
        os.environ["ENABLE_KILL_SWITCH"] = str(req.enable_kill_switch).lower()
        changes.append(f"enable_kill_switch={req.enable_kill_switch}")

    logger.info(f"Settings updated: {', '.join(changes)}")
    return GenericStatusResponse(status="ok", message="Settings updated", data={"changes": changes})


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
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "comment": pos.comment,
                "time": pos.time,
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
