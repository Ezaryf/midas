"""
Midas MT5 Bridge
================
Runs locally on the same Windows machine as MetaTrader 5.
- Streams live XAU/USD ticks to the Midas backend via WebSocket
- Listens for PLACE_ORDER commands and executes them via MT5 API

Requirements:
    pip install MetaTrader5 websockets python-dotenv

Usage:
    python mt5_bridge.py                  # signal display only
    python mt5_bridge.py --auto-trade     # enable order execution
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[MT5Bridge] Loaded config from {env_path}")
    else:
        print(f"[MT5Bridge] No .env found at {env_path} — using environment variables")
except ImportError:
    print("[MT5Bridge] python-dotenv not installed — using environment variables only")

import MetaTrader5 as mt5
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MT5Bridge")

# ── Config ────────────────────────────────────────────────────────────────────
WS_URL        = os.getenv("MIDAS_WS_URL", "ws://localhost:8000/ws/mt5")
MT5_LOGIN     = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD  = os.getenv("MT5_PASSWORD", "")
MT5_SERVER    = os.getenv("MT5_SERVER", "")
SYMBOL        = os.getenv("MT5_SYMBOL", "XAUUSD")
TICK_INTERVAL = float(os.getenv("TICK_INTERVAL", "1.0"))
DEFAULT_LOT   = float(os.getenv("DEFAULT_LOT", "0.01"))
MAGIC_NUMBER  = 20250101
CANDLE_PUSH_INTERVAL = float(os.getenv("CANDLE_PUSH_INTERVAL", "5.0"))
CANDLE_TIMEFRAMES = {
    "1m": mt5.TIMEFRAME_M1,
    "5m": mt5.TIMEFRAME_M5,
    "15m": mt5.TIMEFRAME_M15,
    "1h": mt5.TIMEFRAME_H1,
    "4h": mt5.TIMEFRAME_H4,
}
CANDLE_BARS = int(os.getenv("CANDLE_BARS", "300"))


# ── MT5 Initialisation ────────────────────────────────────────────────────────

def init_mt5() -> bool:
    logger.info("Initialising MetaTrader 5...")

    if not mt5.initialize():
        err = mt5.last_error()
        logger.error(f"mt5.initialize() failed: {err}")
        if err[0] == -6:
            logger.error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            logger.error("  FIX: Open MetaTrader 5 and log in FIRST, then re-run this script.")
            logger.error("  The bridge connects to a running MT5 terminal — it cannot start it.")
            logger.error("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return False

    terminal = mt5.terminal_info()
    logger.info(f"MT5 terminal: {terminal.name if terminal else 'unknown'}")

    if MT5_LOGIN and MT5_PASSWORD and MT5_SERVER:
        logger.info(f"Logging in as account {MT5_LOGIN} on {MT5_SERVER}...")
        ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if not ok:
            err = mt5.last_error()
            logger.error(f"Login failed: {err}")
            logger.error("Check: account number, password, and server name in .env")
            mt5.shutdown()
            return False

        info = mt5.account_info()
        if info:
            logger.info(f"✅ Logged in: {info.name} | {info.server}")
            logger.info(f"   Balance: {info.balance} {info.currency} | Leverage: 1:{info.leverage}")
    else:
        logger.info("No credentials — using currently open MT5 terminal session.")
        info = mt5.account_info()
        if info:
            logger.info(f"✅ Using open session: {info.name} | {info.server}")

    # Auto-detect symbol — prioritize standard XAUUSD naming
    candidates = ["XAUUSD", "GOLDUSD", "XAUUSDm", "XAUUSD.", "GOLD.", "GOLD"]
    resolved = None
    for sym in candidates:
        mt5.symbol_select(sym, True)
        info_sym = mt5.symbol_info(sym)
        if info_sym is not None:
            # Pre-flight check: ensure price is in the reasonable range for Gold (~1500-6500)
            # Higher limit set to accommodate 2026 market environment where Gold > 4800.
            tick = mt5.symbol_info_tick(sym)
            if tick and (1500 < tick.bid < 6500):
                resolved = sym
                break
            else:
                logger.warning(f"Symbol '{sym}' found but price {tick.bid if tick else 'N/A'} is outside normal Gold range. Skipping.")
    
    if resolved is None:
        # Fallback to whatever matches, but warn loudly
        for sym in candidates:
            if mt5.symbol_info(sym):
                resolved = sym
                logger.warning(f"⚠️ Using symbol '{resolved}' despite price anomaly. Chart spikes may occur.")
                break


    if resolved is None:
        logger.error(f"Could not find symbol. Tried: {candidates}")
        logger.error("Open MT5 → Market Watch, find the gold symbol name, set MT5_SYMBOL in .env")
        return False

    if resolved != SYMBOL:
        logger.warning(f"Symbol '{SYMBOL}' not found — using '{resolved}' instead.")
        # Patch the global so tick_sender uses the right name
        globals()["SYMBOL"] = resolved

    tick = mt5.symbol_info_tick(resolved)
    logger.info(f"✅ Symbol: {resolved} | Bid: {tick.bid if tick else 'N/A'} | Ask: {tick.ask if tick else 'N/A'}")
    return True


# ── Order Execution ───────────────────────────────────────────────────────────

def place_order(signal: dict, max_retries: int = 3, risk_manager=None) -> dict:
    direction = signal.get("direction", "").upper()
    trade_symbol = signal.get("symbol") or SYMBOL
    
    # Safely convert to float, handling None values
    try:
        sl  = float(signal.get("stop_loss") or 0)
        tp  = float(signal.get("take_profit_1") or 0)
        lot = float(signal.get("lot") or DEFAULT_LOT)
    except (ValueError, TypeError) as e:
        return {"status": "error", "reason": f"Invalid numeric value in signal: {e}"}

    if direction not in ("BUY", "SELL"):
        return {"status": "skipped", "reason": f"direction={direction}"}
    
    if sl == 0 or tp == 0:
        return {"status": "error", "reason": "Stop loss and take profit are required"}
    
    # ── RISK MANAGEMENT CHECKS ────────────────────────────────────────────────
    
    if risk_manager:
        # 1. Always calculate optimal lot size first
        entry_price = float(signal.get("entry_price", 0))
        if entry_price > 0:
            lot = risk_manager.calculate_lot_size(entry_price, sl)
            lot = risk_manager.calculate_lot_size_from_shadow_performance(
                setup_type=signal.get("setup_type"),
                base_lot_size=lot,
            )
        lot_multiplier = float(signal.get("lot_multiplier") or 1.0)
        if signal.get("position_action") == "scale_in" and "lot_multiplier" not in signal:
            lot_multiplier = float(os.getenv("SCALE_IN_LOT_FRACTION", "0.5"))
        lot = round(max(risk_manager.config.min_lot_size, lot * lot_multiplier), 2)
        
        # 2. Check if we can open a position with this desired lot
        can_trade, reason = risk_manager.can_open_position(
            direction=direction, 
            symbol=trade_symbol, 
            volume=lot, 
            price=entry_price
        )
        
        # 3. If margin is insufficient, attempt fallback to minimum viable lot size
        if not can_trade and "Insufficient free margin" in reason:
            min_lot = risk_manager.config.min_lot_size
            if lot > min_lot:
                logger.warning(f"⚠️ {reason} — Attempting fallback to minimum lot size ({min_lot})")
                can_trade_min, min_reason = risk_manager.can_open_position(
                    direction=direction, 
                    symbol=trade_symbol, 
                    volume=min_lot, 
                    price=entry_price
                )
                if can_trade_min:
                    lot = min_lot
                    can_trade = True
                    logger.info(f"✅ Adjusted to minimum viable lot size: {lot}")
                else:
                    reason = min_reason  # Update reason to the minimum lot failure
        
        # 4. Final check
        if not can_trade:
            logger.warning(f"⚠️ Risk check failed: {reason}")
            return {"status": "blocked", "reason": reason}
            
        logger.info(f"Risk-adjusted lot size approved: {lot}")
    
    # ── Position Query ────────────────────────────────────────────────────────

    def get_current_position(self, symbol: str) -> None:
        pass

    # ──────────────────────────────────────────────────────────────────────────

    # Retry loop for transient errors
    for attempt in range(1, max_retries + 1):
        tick = mt5.symbol_info_tick(trade_symbol)
        if tick is None:
            if attempt < max_retries:
                logger.warning(f"No tick for {trade_symbol}, retrying... ({attempt}/{max_retries})")
                import time; time.sleep(0.5)
                continue
            return {"status": "error", "reason": f"No tick for {trade_symbol} after {max_retries} attempts"}

        price      = tick.ask if direction == "BUY" else tick.bid
        spread     = round(float(tick.ask - tick.bid), 4)
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

        # Try filling modes in order — brokers differ (XM uses FOK or RETURN)
        filling_modes = [
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_RETURN,
        ]

        for filling in filling_modes:
            request = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       trade_symbol,
                "volume":       lot,
                "type":         order_type,
                "price":        price,
                "sl":           sl,
                "tp":           tp,
                "deviation":    30,
                "magic":        MAGIC_NUMBER,
                "comment":      "Midas AI Signal",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": filling,
            }

            result = mt5.order_send(request)

            if result is None:
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Order placed: {direction} {lot} {trade_symbol} @ {price} | SL {sl} | TP {tp} | #{result.order}")
                intended_entry = float(signal.get("entry_price") or price)
                slippage_points = (price - intended_entry) if direction == "BUY" else (intended_entry - price)
                return {
                    "status": "ok",
                    "ticket": result.order,
                    "price": price,
                    "lot_size": lot,
                    "spread": spread,
                    "slippage_points": slippage_points,
                }

            # Unsupported filling — try next
            if result.retcode in (10030, 10038):  # INVALID_FILL
                logger.debug(f"Filling mode {filling} rejected (retcode {result.retcode}), trying next...")
                continue

            # Requote or price changed — retry with fresh tick
            if result.retcode in (10004, 10013, 10014, 10015):  # REQUOTE, INVALID_PRICE, INVALID_STOPS, INVALID_VOLUME
                if attempt < max_retries:
                    logger.warning(f"Requote/price issue (retcode {result.retcode}), retrying with fresh tick... ({attempt}/{max_retries})")
                    import time; time.sleep(0.3)
                    break  # Break filling loop, retry with new tick
                else:
                    return {"status": "error", "retcode": result.retcode, "comment": result.comment}

            # Any other error — stop trying
            logger.error(f"Order failed: retcode {result.retcode} — {result.comment}")
            return {"status": "error", "retcode": result.retcode, "comment": result.comment}

    return {"status": "error", "reason": "All filling modes rejected by broker"}


def _update_position_decision_execution(signal_id: str | None, result: dict, db=None) -> None:
    if not signal_id or not db or not db.is_enabled():
        return

    def _do_update():
        try:
            status = str(result.get("status") or "").lower()
            execution_result = result.get("comment") or result.get("reason") or result.get("message") or status
            db.update_position_decision_execution(
                signal_id=signal_id,
                executed=status in {"ok", "closed"},
                execution_result=execution_result,
            )
        except Exception as exc:
            logger.error(f"Failed to update position decision execution: {exc}")

    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _do_update)
    except RuntimeError:
        _do_update()


def _close_single_position(pos, *, close_reason: str, db=None) -> dict:
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": pos.ticket,
        "magic": pos.magic,
        "comment": f"Position manager - {close_reason}",
    }

    result = mt5.order_send(close_request)
    if not result:
        return {"status": "error", "reason": f"Failed to close position #{pos.ticket}: no result"}

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "status": "error",
            "reason": f"Failed to close position #{pos.ticket}: {result.comment}",
            "retcode": result.retcode,
        }

    tick = mt5.symbol_info_tick(pos.symbol)
    close_price = float(getattr(result, "price", 0.0) or 0.0)
    if not close_price and tick:
        close_price = float(tick.bid) if pos.type == mt5.ORDER_TYPE_BUY else float(tick.ask)

    logger.info(
        f"✅ Position closed: #{pos.ticket} {pos.symbol} | Reason: {close_reason} | Profit: ${float(getattr(result, 'profit', 0.0) or 0.0):.2f}"
    )

    if db and db.is_enabled():
        try:
            db.update_order_close(
                ticket=int(pos.ticket),
                close_price=close_price,
                profit=float(getattr(result, "profit", getattr(pos, "profit", 0.0)) or 0.0),
                commission=float(getattr(result, "commission", 0.0) or 0.0),
                swap=float(getattr(pos, "swap", 0.0) or 0.0),
                close_reason=close_reason,
            )
            from app.services.signal_feedback import signal_feedback_store

            signal_feedback_store.record_outcome(int(pos.ticket))
        except Exception as exc:
            logger.error(f"Failed to persist close for #{pos.ticket}: {exc}")

    return {
        "status": "ok",
        "ticket": int(pos.ticket),
        "symbol": pos.symbol,
        "close_price": close_price,
        "profit": float(getattr(result, "profit", getattr(pos, "profit", 0.0)) or 0.0),
    }


def close_positions_for_symbol(symbol: str, *, close_reason: str, db=None) -> dict:
    target_symbol = symbol or SYMBOL
    positions = mt5.positions_get(magic=MAGIC_NUMBER) or []
    matching_positions = [
        pos for pos in positions if target_symbol.upper() in str(getattr(pos, "symbol", "")).upper()
    ]

    if not matching_positions:
        return {"status": "skipped", "reason": f"No open positions for {target_symbol}"}

    closed_tickets: list[int] = []
    failures: list[str] = []
    for pos in matching_positions:
        close_result = _close_single_position(pos, close_reason=close_reason, db=db)
        if close_result.get("status") == "ok":
            closed_tickets.append(int(close_result["ticket"]))
        else:
            failures.append(str(close_result.get("reason") or f"Failed to close #{pos.ticket}"))

    if failures:
        return {
            "status": "error",
            "reason": "; ".join(failures),
            "closed_tickets": closed_tickets,
        }

    return {
        "status": "closed",
        "closed_tickets": closed_tickets,
        "message": f"Closed {len(closed_tickets)} position(s) for {target_symbol}",
    }


def _fetch_candles(symbol: str, timeframe: str, count: int = CANDLE_BARS) -> list[dict]:
    tf = CANDLE_TIMEFRAMES.get(timeframe)
    if tf is None:
        return []

    try:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return []

        payload: list[dict] = []
        for row in rates:
            payload.append(
                {
                    "time": datetime.fromtimestamp(int(row["time"]), tz=timezone.utc).isoformat(),
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["tick_volume"] if "tick_volume" in row.dtype.names else row["real_volume"]),
                }
            )
        return payload
    except Exception as exc:
        logger.warning(f"Failed to fetch candles for {symbol} {timeframe}: {exc}")
        return []


# ── Trade Synchronizer ────────────────────────────────────────────────────────

class TradeSynchronizer:
    """Synchronizes MT5 ground truth (manual trades + history) with MySQL."""
    def __init__(self, db, target_symbol: str, magic_number: int):
        self.db = db
        self.symbol = target_symbol
        self.magic_number = magic_number
        self.last_sync_timestamp = 0

    def sync_all(self):
        """Perform a full synchronization of positions and recent history."""
        if not self.db or not self.db.is_enabled():
            return

        try:
            # 1. Open positions are always synced fresh (small dataset)
            self._sync_positions()

            # 2. History sync with Delta logic
            from_time = None
            if self.last_sync_timestamp == 0:
                # Initialization: Check DB for the last synced ticket
                last_ticket = self.db.get_last_sync_ticket()
                if last_ticket > 0:
                    deals = mt5.history_deals_get(ticket=last_ticket)
                    if deals:
                        # Start sync from the time of the last known deal
                        from_time = datetime.fromtimestamp(deals[0].time, tz=timezone.utc)
                        logger.info(f"🔄 Resuming history sync from ticket #{last_ticket} ({from_time})")
            
            # If still 0 or no ticket found, start from beginning of time
            if from_time is None:
                from_time = datetime(1970, 1, 1, tzinfo=timezone.utc)
                if self.last_sync_timestamp == 0:
                    logger.info("📡 Starting first-time ALL-TIME history sync...")

            # Sync from 'from_time' to now
            self._sync_history(from_time)
            
            # Update last sync timestamp to now (for the next loop)
            self.last_sync_timestamp = int(datetime.now(timezone.utc).timestamp())

        except Exception as e:
            logger.error(f"Trade sync failed: {e}")

    def _sync_positions(self):
        """Fetch all current open positions and mirror to DB."""
        positions = mt5.positions_get()
        if positions is None:
            return

        for pos in positions:
            data = {
                "ticket": pos.ticket,
                "direction": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                "symbol": pos.symbol,
                "entry_price": pos.price_open,
                "lot_size": pos.volume,
                "magic_number": pos.magic,
                "comment": pos.comment,
                "status": "OPEN",
                "created_at": datetime.fromtimestamp(pos.time, tz=timezone.utc),
                "stop_loss": pos.sl,
                "take_profit": pos.tp,
                "profit": pos.profit,
                "commission": getattr(pos, "commission", 0.0),
                "swap": pos.swap,
            }
            self.db.upsert_order_from_mt5(data)

    def _sync_history(self, from_date: datetime):
        """Fetch historical deals since from_date and sync to DB."""
        deals = mt5.history_deals_get(from_date, datetime.now(timezone.utc))
        if deals is None:
            return

        for deal in deals:
            # Only sync deals that are TRADE_ACTION_DEAL and Type BUY/SELL
            if deal.type not in (mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL):
                continue
            
            data = {
                "ticket": deal.ticket,
                "direction": "BUY" if deal.type == mt5.ORDER_TYPE_BUY else "SELL",
                "symbol": deal.symbol,
                "entry_price": deal.price,
                "lot_size": deal.volume,
                "magic_number": deal.magic,
                "comment": deal.comment,
                "status": "CLOSED" if deal.entry == mt5.DEAL_ENTRY_OUT else "ENTRY_SYNC",
                "created_at": datetime.fromtimestamp(deal.time, tz=timezone.utc),
                "closed_at": datetime.fromtimestamp(deal.time, tz=timezone.utc) if deal.entry == mt5.DEAL_ENTRY_OUT else None,
                "close_price": deal.price if deal.entry == mt5.DEAL_ENTRY_OUT else None,
                "profit": deal.profit,
                "commission": deal.commission,
                "swap": deal.swap,
                "close_reason": "mt5_history_sync"
            }
            self.db.upsert_order_from_mt5(data)

    async def sync_loop(self, interval: int = 30):
        """Periodic sync task."""
        while True:
            self.sync_all()
            await asyncio.sleep(interval)


# ── WebSocket Client ──────────────────────────────────────────────────────────

async def run(auto_trade: bool = False):
    logger.info(f"Connecting to Midas backend at {WS_URL}...")
    logger.info(f"Auto-trade: {'ENABLED ⚡' if auto_trade else 'DISABLED (display only)'}")

    # Start synchronizer and position monitor
    position_monitor = None
    synchronizer = None
    
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from app.services.database import db
        from app.services.position_monitor import get_position_monitor
        
        if db and db.is_enabled():
            synchronizer = TradeSynchronizer(db, SYMBOL, MAGIC_NUMBER)
            logger.info("📡 Trade Synchronizer created.")
            # Run one initial sync before entering loop
            synchronizer.sync_all()
            logger.info("✅ Initial MT5 history sync complete.")

        if auto_trade:
            position_monitor = get_position_monitor()
            if position_monitor:
                position_monitor.start()
    except Exception as e:
        logger.error(f"Failed to start bridge services: {e}")

    async for ws in websockets.connect(WS_URL, ping_interval=20, ping_timeout=10):
        try:
            logger.info("✅ Connected to Midas backend. Streaming ticks...")
            tasks = [
                tick_sender(ws),
                candle_sender(ws),
                command_receiver(ws, auto_trade),
                order_executor_worker(ws, auto_trade),
            ]
            if synchronizer:
                tasks.append(synchronizer.sync_loop(30))
                
            await asyncio.gather(*tasks)
        except websockets.ConnectionClosed:
            logger.warning("Connection closed — reconnecting in 5s...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error: {e} — reconnecting in 5s...")
            await asyncio.sleep(5)
        finally:
            # Stop position monitor on disconnect
            if position_monitor and position_monitor.running:
                await position_monitor.stop()


async def tick_sender(ws):
    last_price = None
    while True:
        tick = mt5.symbol_info_tick(SYMBOL)
        if tick and tick.bid > 0 and tick.ask > 0:
            price = round(tick.bid, 2)
            
            # Spike Guard: Ignore price <= 1.0 or massive jumps (> 1%)
            if price <= 1.0:
                logger.warning(f"⚠️ Ignoring invalid price tick: {price}")
            elif last_price is not None and abs(price - last_price) > (last_price * 0.01):
                logger.warning(f"⚠️ Spike Guard (Local): Ignoring potential bad tick {price} (last: {last_price})")
            else:
                last_price = price
                payload = {
                    "type": "TICK",
                    "data": {
                        "symbol": SYMBOL,
                        "bid":    price,
                        "ask":    round(tick.ask, 2),
                        "spread": round(tick.ask - tick.bid, 2),
                        "time":   datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
                    },
                }
                await ws.send(json.dumps(payload))
            await asyncio.sleep(TICK_INTERVAL)


execution_queue = asyncio.Queue()


async def order_executor_worker(ws, auto_trade: bool):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from app.services.database import db
        from app.services.risk_manager import get_risk_manager
        from app.services.trading_state import trading_state
        risk_manager = get_risk_manager()
    except ImportError:
        logger.warning("Database service not available in bridge")
        db = None
        risk_manager = None

    while True:
        task = await execution_queue.get()
        data = task["data"]
        action = task["action"]
        
        signal_id = data.get("signal_id", "unknown")
        direction = str(data.get("direction", "HOLD")).upper()
        effective_symbol = data.get("symbol") or SYMBOL
        position_action = str(data.get("position_action") or "open").lower()
        is_duplicate = bool(data.get("is_duplicate"))
        
        logger.info(f"⚡ Processing queued execution [{signal_id}]: {direction} ({position_action})")
        
        if is_duplicate or position_action == "ignore":
            result = {
                "status": "skipped",
                "reason": data.get("position_action_reason") or "Signal suppressed by position manager",
            }
        elif position_action == "close":
            result = close_positions_for_symbol(
                effective_symbol,
                close_reason="position_manager_close",
                db=db,
            )
        elif direction not in ("BUY", "SELL"):
            result = {"status": "skipped", "reason": "HOLD signal"}
        elif position_action == "reverse":
            close_result = close_positions_for_symbol(
                effective_symbol,
                close_reason="position_manager_reverse",
                db=db,
            )
            if close_result.get("status") == "error":
                result = {
                    "status": "error",
                    "reason": close_result.get("reason") or "Reverse failed during close step",
                    "closed_tickets": close_result.get("closed_tickets", []),
                }
            else:
                result = place_order(data, risk_manager=risk_manager)
                if close_result.get("closed_tickets"):
                    result["closed_tickets"] = close_result["closed_tickets"]
        else:
            result = place_order(data, risk_manager=risk_manager)

        logger.info(f"   Execution result: {result}")

        if result.get("status") == "blocked" and db and db.is_enabled():
            def _log_risk():
                try:
                    db.log_risk_event(
                        event_type="POSITION_BLOCKED",
                        description=result.get("reason", "Unknown"),
                        action_taken="Order rejected",
                        metadata={
                            "signal_id": signal_id,
                            "direction": direction,
                            "position_action": position_action,
                        },
                    )
                except Exception as e:
                    logger.error(f"Failed to log risk event: {e}")
            
            asyncio.get_running_loop().run_in_executor(None, _log_risk)

        if result.get("status") == "ok" and db and db.is_enabled():
            def _save_order():
                try:
                    signal_context = {
                        "analysis_batch_id": data.get("analysis_batch_id"),
                        "setup_type": data.get("setup_type"),
                        "trading_style": data.get("trading_style"),
                        "market_regime": data.get("market_regime"),
                        "regime_at_signal": data.get("market_regime"),
                        "regime_confidence_at_signal": (data.get("evidence") or {}).get("regime_alignment"),
                        "session_at_signal": data.get("session_label") or "off",
                        "volatility_bucket_at_signal": data.get("volatility_bucket"),
                        "spread_at_signal": result.get("spread"),
                        "actual_spread": result.get("spread"),
                        "slippage_points": result.get("slippage_points"),
                        "intended_entry_price": float(data.get("entry_price") or 0.0),
                        "intended_stop_loss": float(data.get("stop_loss") or 0.0),
                        "intended_take_profit_1": float(data.get("take_profit_1") or 0.0),
                        "data_source_at_signal": data.get("source"),
                        "compression_ratio_at_entry": (data.get("evidence") or {}).get("compression_ratio"),
                        "efficiency_ratio_at_entry": (data.get("evidence") or {}).get("efficiency_ratio"),
                        "close_location_at_entry": (data.get("evidence") or {}).get("close_location"),
                        "body_strength_at_entry": (data.get("evidence") or {}).get("body_strength"),
                        "position_action": position_action,
                        "position_action_reason": data.get("position_action_reason"),
                        "calibrated_confidence": data.get("calibrated_confidence"),
                        "confidence_source": data.get("confidence_source"),
                    }
                    db.save_order(
                        signal_id=signal_id,
                        ticket=result.get("ticket"),
                        direction=direction,
                        entry_price=result.get("price"),
                        stop_loss=float(data.get("stop_loss")),
                        take_profit=float(data.get("take_profit_1")),
                        lot_size=result.get("lot_size", float(data.get("lot", DEFAULT_LOT))),
                        magic_number=MAGIC_NUMBER,
                        comment=f"Midas AI Signal [{position_action}]",
                        symbol=effective_symbol,
                        analysis_batch_id=data.get("analysis_batch_id"),
                        setup_type=data.get("setup_type"),
                        signal_context=signal_context,
                        entry_spread=result.get("spread"),
                        slippage_points=result.get("slippage_points"),
                    )
                except Exception as e:
                    logger.error(f"Failed to save order to database: {e}")

            asyncio.get_running_loop().run_in_executor(None, _save_order)

        _update_position_decision_execution(signal_id, result, db=db)

        ack = {
            "type": "ACK",
            "signal_id": signal_id,
            "status": result.get("status"),
            "ticket": result.get("ticket"),
            "price": result.get("price") or result.get("close_price"),
            "message": result.get("comment") or result.get("reason") or result.get("message", ""),
        }
        await ws.send(json.dumps(ack))

        if result.get("status") == "ok":
            logger.info(f"   ✅ Order #{result.get('ticket')} placed @ {result.get('price')}")
            # Record entry in trading state to update the real-time counter
            try:
                trading_state.record_entry()
            except Exception as e:
                logger.error(f"Failed to record trade entry: {e}")
        elif result.get("status") == "closed":
            logger.info(f"   {ack.get('message')}")
        elif result.get("status") in {"blocked", "skipped"}:
            logger.warning(f"   🚫 {ack.get('message')}")
        else:
            logger.error(f"   ❌ Order failed: {result}")
            
        execution_queue.task_done()


async def command_receiver(ws, auto_trade: bool):
    async for raw in ws:
        try:
            payload = json.loads(raw)
            msg_type = payload.get("type")
            
            if msg_type == "CONFIG_UPDATE":
                try:
                    import sys
                    from pathlib import Path
                    if str(Path(__file__).parent) not in sys.path:
                        sys.path.insert(0, str(Path(__file__).parent))
                    from app.services.risk_manager import get_risk_manager
                    r_manager = get_risk_manager()
                    if r_manager:
                        data = payload.get("data", {})
                        if "max_concurrent_positions" in data and data["max_concurrent_positions"] is not None:
                            r_manager.config.max_concurrent_positions = int(data["max_concurrent_positions"])
                        if "min_lot_size" in data and data["min_lot_size"] is not None:
                            r_manager.config.min_lot_size = float(data["min_lot_size"])
                        if "max_daily_trades" in data and data["max_daily_trades"] is not None:
                            r_manager.config.max_daily_trades = int(data["max_daily_trades"])
                        if "max_risk_percent" in data and data["max_risk_percent"] is not None:
                            r_manager.config.max_risk_percent = float(data["max_risk_percent"])
                        if "daily_loss_limit" in data and data["daily_loss_limit"] is not None:
                            r_manager.config.daily_loss_limit = float(data["daily_loss_limit"])
                        logger.info(f"🔄 Bridge dynamically updated Risk limits: concurrent={r_manager.config.max_concurrent_positions}, trades={r_manager.config.max_daily_trades}")
                except Exception as e:
                    logger.error(f"Failed to process CONFIG_UPDATE: {e}")
                continue

            if msg_type != "SIGNAL":
                continue

            data = payload.get("data", {})
            signal_id = data.get("signal_id", "unknown")
            direction = str(data.get("direction", "HOLD")).upper()
            action = payload.get("action")

            logger.info(f"📡 Signal received [{signal_id}] ({action}): {direction} | confidence {data.get('confidence')}%")

            if action != "PLACE_ORDER":
                logger.debug("   Display-only signal; no MT5 order requested.")
                continue

            if not auto_trade:
                logger.warning("   Auto-trade is OFF - restart with --auto-trade to execute orders")
                await ws.send(json.dumps({
                    "type": "ACK",
                    "signal_id": signal_id,
                    "status": "skipped",
                    "message": "Auto-trade is disabled",
                }))
                continue
            
            await execution_queue.put({"action": action, "data": data})
        except Exception as e:
            logger.error(f"Error processing command: {e}")

async def candle_sender(ws):
    while True:
        for tf_name, tf_val in CANDLE_TIMEFRAMES.items():
            candles = _fetch_candles(SYMBOL, tf_name)
            if candles:
                payload = {
                    "type": "CANDLES",
                    "data": {
                        "symbol": SYMBOL,
                        "timeframe": tf_name,
                        "candles": candles,
                    },
                }
                await ws.send(json.dumps(payload))
        await asyncio.sleep(CANDLE_PUSH_INTERVAL)

if __name__ == "__main__":
    # Default: auto-trade ON if credentials are configured, OFF otherwise
    # Override with --auto-trade (force on) or --display-only (force off)
    has_credentials = bool(MT5_LOGIN and MT5_PASSWORD and MT5_SERVER)

    if "--display-only" in sys.argv:
        auto_trade = False
    elif "--auto-trade" in sys.argv:
        auto_trade = True
    else:
        # Auto-enable if credentials are set in .env
        auto_trade = has_credentials

    print("\n" + "="*55)
    print("  Midas MT5 Bridge")
    print("="*55)
    print(f"  Account : {MT5_LOGIN or '(from open terminal)'}")
    print(f"  Server  : {MT5_SERVER or '(from open terminal)'}")
    print(f"  Symbol  : {SYMBOL}")
    print(f"  Lot     : {DEFAULT_LOT}")
    print(f"  Backend : {WS_URL}")
    print(f"  Mode    : {'AUTO-TRADE ⚡' if auto_trade else 'Display only'}")
    print("="*55 + "\n")

    # Retry init until MT5 is open
    MAX_RETRIES = 10
    for attempt in range(1, MAX_RETRIES + 1):
        if init_mt5():
            break
        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in 10s... (attempt {attempt}/{MAX_RETRIES})")
            logger.info("→ Open MetaTrader 5 and log in, then the bridge will connect automatically.")
            import time; time.sleep(10)
    else:
        logger.error("Could not initialise MT5 after multiple attempts. Exiting.")
        sys.exit(1)

    try:
        asyncio.run(run(auto_trade=auto_trade))
    except asyncio.CancelledError:
        logger.info("Shutdown requested via task cancellation.")
        raise
    except Exception as e:
        logger.error(f"Bridge crashed: {e}")
    finally:
        mt5.shutdown()
