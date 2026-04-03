import os
import logging
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from app.schemas.signal import TradeSignal
from app.api.ws.mt5_handler import manager
from app.services.forex_factory import ForexFactoryService
from app.services.news_service import NewsService

logger = logging.getLogger(__name__)
router = APIRouter()

ff_service   = ForexFactoryService()
news_service = NewsService()


# ── Request models ────────────────────────────────────────────────────────────

class ForceGenerateRequest(BaseModel):
    price:         float | None = None
    trading_style: str          = "Intraday"
    api_key:       str | None   = None
    ai_provider:   str          = "openai"


class ExecuteSignalRequest(BaseModel):
    direction:     str
    entry_price:   float
    stop_loss:     float
    take_profit_1: float
    take_profit_2: float
    confidence:    float       = 0
    reasoning:     str         = ""
    trading_style: str         = "Intraday"
    lot:           float | None = None


class ValidateKeyRequest(BaseModel):
    api_key:     str
    ai_provider: str = "openai"


class ValidateMT5Request(BaseModel):
    login:    int
    password: str
    server:   str
    symbol:   str = "GOLD"


# ── Signal Generation ─────────────────────────────────────────────────────────

@router.post("/signals/force-generate")
async def force_generate_signal(req: ForceGenerateRequest = ForceGenerateRequest()):
    """Runs the full analysis cycle with the requested trading style."""
    from app.core.loop import run_analysis_cycle

    # Override AI credentials if provided
    if req.api_key:
        os.environ["AI_API_KEY"] = req.api_key
    if req.ai_provider:
        os.environ["AI_PROVIDER"] = req.ai_provider

    # Pass trading_style directly — no env mutation needed
    await run_analysis_cycle(trading_style=req.trading_style)

    return {"status": "success", "trading_style": req.trading_style}


# ── Trading Style ─────────────────────────────────────────────────────────────

class SetTradingStyleRequest(BaseModel):
    trading_style: str = "Scalper"

@router.post("/trading-style")
async def set_trading_style(req: SetTradingStyleRequest):
    """Updates the runtime trading style for the analysis loop."""
    valid = ["Scalper", "Intraday", "Swing"]
    if req.trading_style not in valid:
        return {"status": "error", "message": f"Invalid style. Must be one of: {valid}"}
    manager.trading_style = req.trading_style
    logger.info(f"Trading style changed to: {req.trading_style}")
    return {"status": "ok", "trading_style": req.trading_style}


# ── Signal Execution ──────────────────────────────────────────────────────────

@router.post("/signals/execute")
async def execute_signal(req: ExecuteSignalRequest):
    """Broadcasts a PLACE_ORDER to all connected WebSocket clients (mt5_bridge)."""
    connections = len(manager.active_connections)
    if connections == 0:
        return {
            "status":  "warning",
            "message": "No MT5 bridge connected. Run: python backend/mt5_bridge.py",
            "connections": 0,
        }

    # Validate required fields are not None
    if req.stop_loss is None or req.take_profit_1 is None:
        return {
            "status": "error",
            "message": "Invalid signal: stop_loss and take_profit_1 are required",
        }

    # Generate unique signal ID for tracking
    import uuid
    signal_id = str(uuid.uuid4())[:8]
    
    signal_data = req.model_dump()
    signal_data["signal_id"] = signal_id

    await manager.broadcast_json({
        "type": "SIGNAL", 
        "action": "PLACE_ORDER", 
        "data": signal_data,
    })
    
    # Wait up to 5 seconds for acknowledgment
    for _ in range(50):  # 50 * 0.1s = 5s
        await asyncio.sleep(0.1)
        ack = manager.get_ack(signal_id)
        if ack:
            if ack.get("status") == "ok":
                return {
                    "status": "ok",
                    "message": f"✅ Order #{ack.get('ticket')} placed @ {ack.get('price')}",
                    "ticket": ack.get("ticket"),
                    "price": ack.get("price"),
                }
            else:
                return {
                    "status": "error",
                    "message": f"❌ {ack.get('message', 'Order failed')}",
                    "details": ack,
                }
    
    # Timeout — signal sent but no response
    return {
        "status": "warning",
        "message": f"Signal sent to {connections} bridge(s) but no confirmation received",
        "connections": connections,
    }


# ── Economic Calendar ─────────────────────────────────────────────────────────

@router.get("/calendar")
def get_calendar():
    events = ff_service.get_weekly_events()
    return {"events": events}


# ── News ──────────────────────────────────────────────────────────────────────

@router.get("/news")
async def get_news():
    items = await news_service.get_gold_news()
    return {"items": items}


# ── AI Key Validation ─────────────────────────────────────────────────────────

@router.post("/ai/validate")
async def validate_api_key(req: ValidateKeyRequest):
    from app.services.ai_engine import AITradingEngine
    try:
        engine   = AITradingEngine(api_key=req.api_key, provider=req.ai_provider)
        response = await engine.client.chat.completions.create(
            model=engine.model,
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
            max_tokens=5,
        )
        reply = response.choices[0].message.content or ""
        return {"status": "ok", "model": engine.model, "reply": reply.strip()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── MT5 Credential Validation ─────────────────────────────────────────────────

@router.post("/mt5/validate")
async def validate_mt5(req: ValidateMT5Request):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"status": "error", "message": "MetaTrader5 not installed. Run: pip install MetaTrader5"}

    import asyncio

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
        for s in candidates:
            mt5.symbol_select(s, True)
            if mt5.symbol_info(s):
                resolved = s
                break

        tick = mt5.symbol_info_tick(resolved) if resolved else None
        mt5.shutdown()

        return {
            "status":   "ok",
            "name":     info.name     if info else "Unknown",
            "balance":  info.balance  if info else 0,
            "currency": info.currency if info else "USD",
            "leverage": info.leverage if info else 0,
            "server":   info.server   if info else req.server,
            "symbol":   resolved,
            "bid":      round(tick.bid, 2) if tick else None,
            "ask":      round(tick.ask, 2) if tick else None,
        }

    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _test)
    return result


# ── Health & Account ──────────────────────────────────────────────────────────

@router.get("/health")
def health():
    try:
        from app.services.database import db
        bridge_connected = len(manager.active_connections) > 0
        latest_price = None
        if manager.latest_tick and isinstance(manager.latest_tick, dict):
            latest_price = manager.latest_tick.get("bid")
        
        return {
            "status":        "ok",
            "mt5_connected": bridge_connected,
            "bridge_count":  len(manager.active_connections),
            "latest_price":  latest_price,
            "pending_signals": len(manager._pending_signals),
            "database_enabled": db.is_enabled(),
            "message": "✅ Bridge connected" if bridge_connected else "⚠️ No bridge — run: python backend/mt5_bridge.py --auto-trade",
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@router.get("/account")
def get_account():
    tick = manager.latest_tick
    if not tick:
        return {"connected": False}
    return {"connected": True, **tick}


# ── Trade History & Analytics ─────────────────────────────────────────────────

@router.get("/history/signals")
async def get_signal_history(limit: int = 50):
    """Get recent AI-generated signals"""
    from app.services.database import db
    signals = await db.get_recent_signals(limit=limit)
    return {"signals": signals}


@router.get("/history/orders")
async def get_order_history(status: str = "all", limit: int = 50):
    """Get order history. Status: all, open, closed"""
    from app.services.database import db
    
    if status == "open":
        orders = await db.get_open_orders()
    else:
        # TODO: Add get_closed_orders method
        orders = []
    
    return {"orders": orders}


@router.get("/analytics/performance")
async def get_performance(period: str = "ALL_TIME"):
    """Get performance metrics. Period: DAILY, WEEKLY, MONTHLY, ALL_TIME"""
    from app.services.database import db
    
    # Calculate fresh metrics
    await db.calculate_performance_metrics(period=period)
    
    # Fetch cached metrics
    metrics = await db.get_performance_metrics(period=period)
    
    return {"metrics": metrics}


@router.get("/analytics/equity-curve")
async def get_equity_curve(days: int = 30):
    """Get equity curve data for charting"""
    from app.services.database import db
    data = await db.get_equity_curve(days=days)
    return {"data": data}


# ── Risk Management ───────────────────────────────────────────────────────────

@router.get("/risk/status")
def get_risk_status():
    """Get current risk management status"""
    from app.services.risk_manager import get_risk_manager
    
    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available — MT5 bridge not running"}
    
    summary = risk_manager.get_risk_summary()
    return summary


@router.post("/risk/check")
async def check_risk(direction: str = "BUY"):
    """Check if a new position can be opened"""
    from app.services.risk_manager import get_risk_manager
    
    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"allowed": False, "reason": "Risk manager not available"}
    
    can_trade, reason = risk_manager.can_open_position(direction)
    return {"allowed": can_trade, "reason": reason}


@router.post("/risk/force-close-all")
async def force_close_all_positions():
    """Emergency: Close all open positions"""
    import MetaTrader5 as mt5
    from app.services.risk_manager import get_risk_manager
    from app.services.database import db
    
    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available"}
    
    positions = risk_manager.get_open_positions()
    if not positions:
        return {"message": "No open positions", "closed": 0}
    
    closed_count = 0
    for pos in positions:
        try:
            # Close position
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
                
                # Log risk event
                if db.is_enabled():
                    await db.log_risk_event(
                        event_type="FORCE_CLOSE",
                        description=f"Position #{pos.ticket} force closed",
                        action_taken="Manual force close",
                        metadata={"ticket": pos.ticket, "profit": pos.profit},
                    )
        except Exception as e:
            logger.error(f"Failed to close position #{pos.ticket}: {e}")
    
    return {"message": f"Closed {closed_count} positions", "closed": closed_count}


# ── Position Management ───────────────────────────────────────────────────────

@router.get("/positions/monitor/status")
def get_position_monitor_status():
    """Get position monitor status"""
    from app.services.position_monitor import get_position_monitor
    
    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available — MT5 bridge not running"}
    
    return monitor.get_status()


@router.get("/positions/open")
def get_open_positions():
    """Get all currently open positions"""
    import MetaTrader5 as mt5
    from app.services.risk_manager import get_risk_manager
    
    risk_manager = get_risk_manager()
    if not risk_manager:
        return {"error": "Risk manager not available"}
    
    positions = risk_manager.get_open_positions()
    
    # Convert to dict for JSON serialization
    positions_data = []
    for pos in positions:
        positions_data.append({
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
        })
    
    return {"positions": positions_data}


@router.post("/positions/{ticket}/close")
async def close_position_manual(ticket: int):
    """Manually close a specific position"""
    from app.services.position_monitor import get_position_monitor
    
    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    
    result = await monitor.close_position_manual(ticket)
    return result


@router.post("/positions/{ticket}/modify")
async def modify_position_manual(ticket: int, sl: float, tp: float):
    """Manually modify position SL/TP"""
    from app.services.position_monitor import get_position_monitor
    
    monitor = get_position_monitor()
    if not monitor:
        return {"error": "Position monitor not available"}
    
    result = await monitor.modify_position_manual(ticket, sl, tp)
    return result
