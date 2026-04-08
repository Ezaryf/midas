import asyncio
import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.ws.mt5_handler import manager
from app.services.forex_factory import ForexFactoryService
from app.services.news_service import NewsService

logger = logging.getLogger(__name__)
router = APIRouter()

ff_service = ForexFactoryService()
news_service = NewsService()


class ForceGenerateRequest(BaseModel):
    price: float | None = None
    trading_style: str = "Intraday"
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
    trading_style: str = "Intraday"
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
    trading_style: str = "Scalper"


class SetTargetSymbolRequest(BaseModel):
    target_symbol: str = "XAUUSD"


@router.post("/signals/force-generate")
async def force_generate_signal(req: ForceGenerateRequest = ForceGenerateRequest()):
    from app.core.loop import run_analysis_cycle
    from app.services.trading_state import trading_state

    if req.api_key:
        os.environ["AI_API_KEY"] = req.api_key
    if req.ai_provider:
        os.environ["AI_PROVIDER"] = req.ai_provider

    trading_state.set_trading_style(req.trading_style)
    manager.trading_style = req.trading_style
    batch = await run_analysis_cycle(
        trading_style=req.trading_style,
        symbol=trading_state.target_symbol,
    )
    return batch.model_dump(mode="json")


@router.post("/trading-style")
async def set_trading_style(req: SetTradingStyleRequest):
    from app.services.trading_state import trading_state

    valid = ["Scalper", "Intraday", "Swing"]
    if req.trading_style not in valid:
        return {"status": "error", "message": f"Invalid style. Must be one of: {valid}"}
    manager.trading_style = req.trading_style
    trading_state.set_trading_style(req.trading_style)
    logger.info(f"Trading style changed to: {req.trading_style}")
    return {"status": "ok", "trading_style": req.trading_style}


@router.post("/target-symbol")
async def set_target_symbol(req: SetTargetSymbolRequest):
    from app.services.trading_state import trading_state

    trading_state.set_target_symbol(req.target_symbol)
    logger.info(f"Target symbol changed to: {req.target_symbol}")
    return {"status": "ok", "target_symbol": req.target_symbol}


@router.post("/signals/execute")
async def execute_signal(req: ExecuteSignalRequest):
    connections = len(manager.active_connections)
    if connections == 0:
        return {
            "status": "warning",
            "message": "No MT5 bridge connected. Run: python backend/mt5_bridge.py",
            "connections": 0,
        }

    if req.stop_loss is None or req.take_profit_1 is None:
        return {
            "status": "error",
            "message": "Invalid signal: stop_loss and take_profit_1 are required",
        }

    import uuid

    signal_id = str(uuid.uuid4())[:8]
    signal_data = req.model_dump()
    signal_data["signal_id"] = signal_id

    await manager.broadcast_json({"type": "SIGNAL", "action": "PLACE_ORDER", "data": signal_data})

    for _ in range(50):
        await asyncio.sleep(0.1)
        ack = manager.get_ack(signal_id)
        if ack:
            if ack.get("status") == "ok":
                return {
                    "status": "ok",
                    "message": f"Order #{ack.get('ticket')} placed @ {ack.get('price')}",
                    "ticket": ack.get("ticket"),
                    "price": ack.get("price"),
                }
            return {
                "status": "error",
                "message": ack.get("message", "Order failed"),
                "details": ack,
            }

    return {
        "status": "warning",
        "message": f"Signal sent to {connections} bridge(s) but no confirmation received",
        "connections": connections,
    }


@router.get("/calendar")
def get_calendar():
    return {"events": ff_service.get_weekly_events()}


@router.get("/news")
async def get_news():
    return {"items": await news_service.get_gold_news()}


@router.post("/ai/validate")
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
        return {"status": "ok", "model": engine.model, "reply": reply.strip()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/mt5/validate")
async def validate_mt5(req: ValidateMT5Request):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"status": "error", "message": "MetaTrader5 not installed. Run: pip install MetaTrader5"}

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


@router.get("/health")
def health():
    try:
        from app.services.database import db

        bridge_connected = len(manager.active_connections) > 0
        latest_price = manager.latest_tick.get("bid") if isinstance(manager.latest_tick, dict) else None
        return {
            "status": "ok",
            "mt5_connected": bridge_connected,
            "bridge_count": len(manager.active_connections),
            "latest_price": latest_price,
            "pending_signals": len(manager._pending_signals),
            "database_enabled": db.is_enabled(),
            "message": "Bridge connected" if bridge_connected else "No bridge - run: python backend/mt5_bridge.py --auto-trade",
        }
    except Exception as exc:
        logger.error(f"Health check error: {exc}")
        return {"status": "error", "message": str(exc)}


@router.get("/account")
def get_account():
    tick = manager.latest_tick
    if not tick:
        return {"connected": False}
    return {"connected": True, **tick}


@router.get("/history/signals")
async def get_signal_history(limit: int = 50):
    from app.services.database import db

    return {"signals": db.get_recent_signals(limit=limit)}


@router.get("/history/orders")
async def get_order_history(status: str = "all", limit: int = 50):
    from app.services.database import db

    if status == "open":
        return {"orders": db.get_open_orders()}
    return {"orders": []}


@router.get("/analytics/performance")
async def get_performance(period: str = "ALL_TIME"):
    from app.services.database import db

    db.calculate_performance_metrics(period=period)
    return {"metrics": db.get_performance_metrics(period=period)}


@router.get("/analytics/equity-curve")
async def get_equity_curve(days: int = 30):
    from app.services.database import db

    return {"data": db.get_equity_curve(days=days)}


@router.get("/risk/status")
def get_risk_status():
    from app.services.risk_manager import get_risk_manager

    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available - MT5 bridge not running"}
    return risk_manager.get_risk_summary()


@router.post("/risk/check")
async def check_risk(direction: str = "BUY"):
    from app.services.risk_manager import get_risk_manager

    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"allowed": False, "reason": "Risk manager not available"}

    can_trade, reason = risk_manager.can_open_position(direction)
    return {"allowed": can_trade, "reason": reason}


@router.post("/risk/force-close-all")
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


@router.get("/positions/monitor/status")
def get_position_monitor_status():
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available - MT5 bridge not running"}
    return monitor.get_status()


@router.get("/positions/open")
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


@router.post("/positions/{ticket}/close")
async def close_position_manual(ticket: int):
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    return monitor.close_position_manual(ticket)


@router.post("/positions/{ticket}/modify")
async def modify_position_manual(ticket: int, sl: float, tp: float):
    from app.services.position_monitor import get_position_monitor

    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    return monitor.modify_position_manual(ticket, sl, tp)
